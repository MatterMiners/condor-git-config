#!/usr/bin/python3
import sys
import os
import argparse
import logging
import subprocess
import time
import json
import functools
import re
import random
import filelock
import zlib


try:
    display_columns = os.get_terminal_size().columns
except OSError:
    display_columns = 80
else:
    # fix argparse help output -- https://bugs.python.org/issue13041
    os.environ.setdefault('COLUMNS', str(display_columns))


CLI = argparse.ArgumentParser(
    description='Dynamic Condor Configuration Hook',
    fromfile_prefix_chars='@',
    formatter_class=functools.partial(
        argparse.ArgumentDefaultsHelpFormatter,
        max_help_position=max(24, int(0.3 * display_columns))
    ),
)
CLI_SOURCE = CLI.add_argument_group('source of configuration files')
CLI_SOURCE.add_argument(
    dest='git_uri',
    metavar='GIT-URI',
    help='git repository URI to fetch files from',
)
CLI_SOURCE.add_argument(
    '-b', '--branch',
    help='branch to fetch files from',
    default='master',
)
CLI_CACHE = CLI.add_argument_group('local configuration cache')
CLI_CACHE.add_argument(
    '--cache-path',
    help='path to cache configuration file sources',
    default='/etc/condor/config.git/',
)
CLI_CACHE.add_argument(
    '--max-age',
    help='seconds before a new update is pulled',
    default=300 + random.randint(-10, 10),
    type=int,
)
CLI_SELECTION = CLI.add_argument_group('configuration selection')
CLI_SELECTION.add_argument(
    '--pattern',
    help='regular expression(s) for configuration files',
    nargs='*',
    default=[r'^[^.].*\.cfg$'],
)
CLI_SELECTION.add_argument(
    '--blacklist',
    help='regular expression(s) for ignoring configuration files',
    nargs='*',
    default=[],
)
CLI_SELECTION.add_argument(
    '--whitelist',
    help='regular expression(s) for including ignored files',
    nargs='*',
    default=[],
)
CLI_SELECTION.add_argument(
    '--recurse',
    help='provide files beyond the top-level',
    action='store_true',
)
CLI_INTEGRATION = CLI.add_argument_group('configuration integration')
CLI_INTEGRATION.add_argument(
    '--path-key',
    help='config key exposing the cache path',
    default='GIT_CONFIG_CACHE_PATH',
)

LOGGER = logging.getLogger()


class ConfigCache(object):
    """
    Cache for configuration files from git
    """
    def __init__(self, git_uri, branch, cache_path, max_age):
        self.git_uri = git_uri
        self.branch = branch
        self.cache_path = cache_path
        self.max_age = max_age
        self._work_path = os.path.abspath(os.path.join(cache_path, branch))
        self._meta_file = self.abspath('cache.json')
        self._cache_lock = filelock.FileLock(
            os.path.join('/tmp', '.cache.%s.lock' % zlib.adler32(os.path.basename(__file__).encode()))
        )
        os.makedirs(self._work_path, exist_ok=True, mode=0o755)

    def abspath(self, *rel_paths):
        return os.path.abspath(os.path.join(self._work_path, *rel_paths))

    def repo_path(self, *rel_paths):
        return self.abspath('repo', *rel_paths)

    def __enter__(self):
        self._cache_lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cache_lock.release()
        return False

    def __iter__(self):
        # avoid duplicates from links
        seen = set()
        repo_path = self.repo_path()
        for dir_path, dir_names, file_names in os.walk(repo_path):
            if '.git' in dir_names:
                dir_names.remove('.git')
            dir_names[:] = sorted(dir_names)
            for file_name in sorted(file_names):
                rel_path = os.path.normpath(os.path.relpath(os.path.join(dir_path, file_name), repo_path))
                if rel_path in seen:
                    continue
                seen.add(rel_path)
                yield rel_path

    @property
    def outdated(self):
        try:
            with open(self._meta_file, 'r') as raw_meta:
                meta_data = json.load(raw_meta)
        except FileNotFoundError:
            return True
        else:
            if meta_data['git_uri'] != self.git_uri or meta_data['branch'] != self.branch:
                LOGGER.critical('cache %r corrupted by other hook: %r', self, meta_data)
                raise RuntimeError('config cache %r used for conflicting hooks' % self.cache_path)
            else:
                return meta_data['timestamp'] + self.max_age <= time.time()

    def _update_metadata(self):
        with open(self._meta_file, 'w') as raw_meta:
            json.dump({'git_uri': self.git_uri, 'branch': self.branch, 'timestamp': time.time()}, raw_meta)

    def refresh(self):
        if not self.outdated:
            return
        repo_path = self.repo_path()
        if not os.path.exists(os.path.join(repo_path, '.git')):
            subprocess.check_output(
                ['git', 'clone', '--quiet', '--branch', str(self.branch), str(self.git_uri), repo_path],
                timeout=30,
                universal_newlines=True,
            )
        else:
            subprocess.check_output(
                ['git', 'pull'],
                timeout=30,
                cwd=repo_path,
                universal_newlines=True
            )
        self._update_metadata()


class ConfigSelector(object):
    def __init__(self, pattern, blacklist, whitelist, recurse):
        self.pattern = self._prepare_re(pattern)
        self.blacklist = self._prepare_re(blacklist, '(?!)')
        self.whitelist = self._prepare_re(whitelist)
        self.recurse = recurse

    @staticmethod
    def _prepare_re(pieces, default='.*'):
        if not pieces:
            return re.compile(default)
        if len(pieces) == 1:
            return re.compile(pieces[0])
        else:
            return re.compile('|'.join('(?:%s)' % piece for piece in pieces))

    def get_paths(self, config_cache):
        for rel_path in config_cache:
            if not self.recurse and os.path.dirname(rel_path):
                continue
            if self.pattern.search(rel_path):
                if not self.blacklist.search(rel_path) or self.whitelist.search(rel_path):
                    yield config_cache.repo_path(rel_path)


def include_configs(path_key, config_cache, config_selector, destination=sys.stdout):
    with config_cache:
        config_cache.refresh()
        print('%s = %s' % (path_key, config_cache.repo_path()), file=destination)
        for config_path in config_selector.get_paths(config_cache):
            print('include : %s' % config_path, file=destination)


def main():
    options = CLI.parse_args()
    config_cache = ConfigCache(
        git_uri=options.git_uri, branch=options.branch, cache_path=options.cache_path, max_age=options.max_age
    )
    config_selector = ConfigSelector(
        pattern=options.pattern, blacklist=options.blacklist, whitelist=options.whitelist, recurse=options.recurse
    )
    include_configs(options.path_key, config_cache, config_selector)

if __name__ == '__main__':
    main()

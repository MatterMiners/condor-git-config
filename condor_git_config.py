#!/usr/bin/python3
"""dynamically configure an HTCondor node from a git repository"""
from typing import Union, List, Iterator, Optional, Dict, Any

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
from pathlib import Path

__version__ = "0.1.3"


try:
    display_columns = os.get_terminal_size().columns
except OSError:
    display_columns = 80
else:
    # fix argparse help output -- https://bugs.python.org/issue13041
    os.environ.setdefault("COLUMNS", str(display_columns))


CLI = argparse.ArgumentParser(
    description="Dynamic Condor Configuration Hook",
    fromfile_prefix_chars="@",
    formatter_class=functools.partial(
        argparse.ArgumentDefaultsHelpFormatter,
        max_help_position=max(24, int(0.3 * display_columns)),
    ),
)
CLI_SOURCE = CLI.add_argument_group("source of configuration files")
CLI_SOURCE.add_argument(
    dest="git_uri",
    metavar="GIT-URI",
    help="git repository URI to fetch files from",
)
CLI_SOURCE.add_argument(
    "-b",
    "--branch",
    help="branch to fetch files from",
    default="master",
)
CLI_CACHE = CLI.add_argument_group("local configuration cache")
CLI_CACHE.add_argument(
    "--cache-path",
    help="path to cache configuration file sources",
    default=Path("/etc/condor/config.git/"),
    type=Path,
)
CLI_CACHE.add_argument(
    "--max-age",
    help="seconds before a new update is pulled; use inf to disable updates",
    default=300 + random.randint(-10, 10),
    type=float,
)
CLI_SELECTION = CLI.add_argument_group("configuration selection")
CLI_SELECTION.add_argument(
    "--pattern",
    help="regular expression(s) for configuration files",
    nargs="*",
    default=[r"^[^.].*\.cfg$"],
)
CLI_SELECTION.add_argument(
    "--blacklist",
    help="regular expression(s) for ignoring configuration files",
    nargs="*",
    default=[],
)
CLI_SELECTION.add_argument(
    "--whitelist",
    help="regular expression(s) for including ignored files",
    nargs="*",
    default=[],
)
CLI_SELECTION.add_argument(
    "--recurse",
    help="provide files beyond the top-level",
    action="store_true",
)
CLI_INTEGRATION = CLI.add_argument_group("configuration integration")
CLI_INTEGRATION.add_argument(
    "--path-key",
    help="config key exposing the cache path",
    default="GIT_CONFIG_CACHE_PATH",
)

LOGGER = logging.getLogger()


class ConfigCache(object):
    """
    Cache for configuration files from git
    """

    def __init__(self, git_uri: str, branch: str, cache_path: Path, max_age: float):
        self.git_uri = git_uri
        self.branch = branch
        self.cache_path = cache_path
        self.max_age = max_age
        self._work_path = cache_path.resolve() / branch
        self._work_path.mkdir(mode=0o755, parents=True, exist_ok=True)
        self._meta_file = self.abspath("cache.json")
        self._cache_lock = filelock.FileLock(str(self.abspath(f"cache.{branch}.lock")))
        self._config_meta: Optional[Dict[str, Any]] = None

    @property
    def stats(self):
        """Statistics of the cache"""
        meta = self._config_meta if self._config_meta is not None else self._read_meta()
        age = time.time() - meta["timestamp"]
        return {"age": age, "pulls": meta["pulls"], "reads": meta["reads"]}

    def _read_meta(self):
        try:
            with open(self._meta_file, "r") as meta_stream:
                meta_data = json.load(meta_stream)
        except FileNotFoundError:
            return {
                "git_uri": self.git_uri,
                "branch": self.branch,
                "timestamp": 0.0,
                "pulls": 0,
                "reads": 0,
            }
        else:
            if meta_data["git_uri"] != self.git_uri:
                LOGGER.critical("cache %r corrupted by other hook: %r", self, meta_data)
                raise RuntimeError(
                    f"config cache {self.cache_path!r} used for conflicting hooks"
                )
            return meta_data

    def _write_meta(self):
        if self._config_meta is None:
            return
        with open(self._meta_file, "w") as meta_stream:
            json.dump(self._config_meta, meta_stream)

    def abspath(self, *rel_paths: Union[str, Path]) -> Path:
        return self._work_path.joinpath(*rel_paths)

    def repo_path(self, *rel_paths: Union[str, Path]) -> Path:
        return self.abspath("repo", *rel_paths)

    def __enter__(self):
        self._cache_lock.acquire()
        self._config_meta = self._read_meta()
        self._refresh()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._write_meta()
        self._config_meta = None
        self._cache_lock.release()
        return False

    def __iter__(self) -> Iterator[Path]:
        assert self._config_meta is not None
        # avoid duplicates from links
        repo_path = self.repo_path()
        for base_dir, dir_names, file_names in os.walk(repo_path):
            try:
                dir_names.remove(".git")
            except ValueError:
                pass
            dir_names.sort()
            dir_path = Path(base_dir)
            for file_name in sorted(file_names):
                rel_path = (dir_path / file_name).relative_to(repo_path)
                yield rel_path

    def _refresh(self):
        assert self._config_meta is not None
        self._config_meta["reads"] += 1
        if self._config_meta["timestamp"] + self.max_age > time.time():
            return  # early exit as ConfigCache is still valid
        repo_path = self.repo_path()
        self._config_meta["pulls"] += 1
        if not self.repo_path(".git").exists():
            branch = [] if not self.branch else ["--branch", self.branch]
            subprocess.check_output(
                ["git", "clone", "--quiet", *branch, self.git_uri, str(repo_path)],
                timeout=30,
                universal_newlines=True,
            )
            self._config_meta["timestamp"] = time.time()
        else:
            try:
                subprocess.check_output(
                    ["git", "pull"], timeout=30, cwd=repo_path, universal_newlines=True
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass
            else:
                self._config_meta["timestamp"] = time.time()


class ConfigSelector(object):
    """
    Selector for a configuration file iterator
    """

    def __init__(
        self,
        pattern: List[str],
        blacklist: List[str],
        whitelist: List[str],
        recurse: bool,
    ):
        self.pattern = self._prepare_re(pattern)
        self.blacklist = self._prepare_re(blacklist, default="(?!)")
        self.whitelist = self._prepare_re(whitelist)
        self.recurse = recurse

    @staticmethod
    def _prepare_re(pieces, default=".*") -> "re.Pattern":
        if not pieces:
            return re.compile(default)
        if len(pieces) == 1:
            return re.compile(pieces[0])
        else:
            return re.compile("|".join(f"(?:{piece})" for piece in pieces))

    def get_paths(self, config_cache: ConfigCache) -> Iterator[Path]:
        pattern, blacklist, whitelist = self.pattern, self.blacklist, self.whitelist
        for rel_path in config_cache:
            if not self.recurse and rel_path.parent != Path("."):
                continue
            str_path = str(rel_path)
            if pattern.search(str_path):
                if not blacklist.search(str_path) or whitelist.search(str_path):
                    yield config_cache.repo_path(rel_path)


def include_configs(
    path_key: str,
    config_cache: ConfigCache,
    config_selector: ConfigSelector,
    destination=sys.stdout,
):
    with config_cache:
        print("#", json.dumps(config_cache.stats), file=destination)
        print(f"{path_key} = {config_cache.repo_path()}", file=destination)
        for config_path in config_selector.get_paths(config_cache):
            print(f"include : {config_path}", file=destination)


def main():
    options = CLI.parse_args()
    config_cache = ConfigCache(
        git_uri=options.git_uri,
        branch=options.branch,
        cache_path=options.cache_path,
        max_age=options.max_age,
    )
    config_selector = ConfigSelector(
        pattern=options.pattern,
        blacklist=options.blacklist,
        whitelist=options.whitelist,
        recurse=options.recurse,
    )
    include_configs(options.path_key, config_cache, config_selector)


if __name__ == "__main__":
    main()

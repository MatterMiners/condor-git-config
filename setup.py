#!/usr/bin/python3
import os
from setuptools import setup, find_packages

repo_base_dir = os.path.abspath(os.path.dirname(__file__))
# pull in the packages metadata
package_about = {
    '__title__': 'condor_git_config',
    '__version__': '0.1.2',
    '__summary__': 'dynamically configure an HTCondor node from a git repository',
    '__author__': 'Max Fischer',
    '__email__': 'maxfischer2781@gmail.com',
    '__url__': 'https://github.com/maxfischer2781/condor-git-config',
}

with open(os.path.join(repo_base_dir, 'README.rst'), 'r') as README:
    long_description = README.read()

if __name__ == '__main__':
    setup(
        name=package_about['__title__'],
        version=package_about['__version__'],
        description=package_about['__summary__'],
        long_description=long_description.strip(),
        author=package_about['__author__'],
        author_email=package_about['__email__'],
        url=package_about['__url__'],
        py_modules=['condor_git_config'],
        # packages=find_packages(),
        entry_points={
            'console_scripts': [
                'condor-git-config = condor_git_config:main',
            ],
        },
        # dependencies
        install_requires=['filelock'],
        # metadata for package search
        license='MIT',
        # https://pypi.python.org/pypi?%3Aaction=list_classifiers
        classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Developers',
            'Intended Audience :: System Administrators',
            'Topic :: System :: Monitoring',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.3',
            'Programming Language :: Python :: 3.4',
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6',
        ],
        keywords='htcondor condor configuration',
        # unit tests
        # test_suite='test_condor_git_config',
        # use unittest backport to have subTest etc.
        # tests_require=['unittest2'] if sys.version_info < (3, 4) else [],
    )

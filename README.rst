##################
condor-config-hook
##################

Hook to dynamically configure an HTCondor node from a ``git`` repository.

Hook Overview
#############

The hook is integrated into a Condor config file to perform the following workflow:

* Fetch a *git repository* to a *local cache*
* Use patterns to *select configuration files*
* Dynamically *include configuration* in condor

To integrate the hook, use the ``include command`` syntax in any HTCondor config file:

.. code::

    include command : condor-git-config https://git.mydomain.com/condor-repos/condor-configs.git

.. note::  Any arguments in ``include command`` are passed directly to the program, without evoking a shell.
           This means that escapes and quotes required for passing arguments on the shell must **not**
           be used in the configuration.

Usage Notes
###########

The hook requires at least Python 3.3 to run. A list of options is available by passing ``-h`` or ``--help`` to the executable.

Installation
------------

Installation provides the ``condor-git-config`` executable.
All other dependencies are installed automatically.

Stable release version

.. code:: bash

    pip3 install condor_git_config

Current development version

.. code:: bash

    git clone https://github.com/maxfischer2781/condor-git-config.git
    ./condor-git-config/setup.py install

Argument Files
--------------

The ``condor-git-config`` executable can use the ``@``
`prefix character <https://docs.python.org/3/library/argparse.html#fromfile-prefix-chars>`_
to read arguments from files.
This allows you to prepare options externally

.. code:: bash

    echo $(hostname -d) >> /etc/mycloud/domain

and have them used dynamically to adjust configuration

.. code::

    include command : condor-git-config --branch @/etc/mycloud/domain -- https://git.mydomain.com/condor-repos/condor-configs.git

Configuration Recursion
-----------------------

By default, ``condor-git-config`` will not recurse into sub-directories.
This allows you to have additional configuration, which is conditionally integrated.
For example, consider the following git repository tree:

.. code::

    |- commong.cfg
    |- security.cfg
    |- aaaron-cloud.cfg
    |- aaaron-cloud/
    |  |- overwrites.cfg
    |  |- proxy.cfg
    |- beebee-cloud.cfg

The ``aaaron-cloud`` folder will be ignored by default.
You can conditionally include the ``*-cloud.cfg`` files like this:

.. code:: bash

    --blacklist '.-cloud\.cfg' --whitelist @/etc/mycloud/flavour

This allows you to further include the files in ``aaaron-cloud`` by using ``include`` in ``aaaron-cloud.cfg``:

.. code::

    # aaaron-cloud.cfg
    include : $(GIT_CONFIG_CACHE_PATH)/overwrites.cfg
    include : $(GIT_CONFIG_CACHE_PATH)/proxy.cfg

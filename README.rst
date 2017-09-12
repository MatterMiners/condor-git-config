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

Usage Notes
###########

Installation
------------




from invoke import Argument, Program


class PyDeployProgram(Program):

    ARG_PYDEPLOY_CONFIG_PATH_LONG = "pydeploy-config-dir"
    ARG_CONFIG_PATH_LONG = "config-path"
    ARG_CONFIG_PATH_SHORT = "c"
    ARG_HOSTS = "hosts"
    ARG_HOSTS_CONNECTION_USER_LONG = "hosts-connection-user"
    ARG_HOSTS_CONNECTION_USER_SHORT = "u"
    ARG_REQUESTS_DISABLE_WARNINGS_LONG = "requests-disable-warnings"
    ARG_REQUESTS_DISABLE_WARNINGS_SHORT = "r"
    ARG_SSH_PORT = "ssh-port"
    ARG_SSH_IDENTITY_FILE = "ssh-identity-file"

    def __init__(
        self,
        version=None,
        namespace=None,
        name=None,
        binary=None,
        loader_class=None,
        executor_class=None,
        config_class=None,
        binary_names=None,
    ):
        super().__init__(
            version=version,
            namespace=namespace,
            name=name,
            binary=binary,
            loader_class=loader_class,
            executor_class=executor_class,
            config_class=config_class,
            binary_names=binary_names,
        )

    def core_args(self):
        core_args = super(PyDeployProgram, self).core_args()
        extra_args = [
            Argument(
                name=PyDeployProgram.ARG_PYDEPLOY_CONFIG_PATH_LONG,
                help="Fully qualified path to the PyDeploy base config directory. You should clone this directory prior to running these tasks.",
                optional=False,
            ),
            Argument(
                names=(
                    PyDeployProgram.ARG_CONFIG_PATH_LONG,
                    PyDeployProgram.ARG_CONFIG_PATH_SHORT,
                ),
                help="Fully qualified path to the PyDeploy config yaml file",
                optional=False,
            ),
            Argument(
                name=PyDeployProgram.ARG_HOSTS,
                help="CSV of host names against which to run the specified task",
                kind=str,
                optional=True,
            ),
            Argument(
                names=(
                    PyDeployProgram.ARG_HOSTS_CONNECTION_USER_LONG,
                    PyDeployProgram.ARG_HOSTS_CONNECTION_USER_SHORT,
                ),
                help="The username for the fabric/ssh connections for the hosts on which we will run the tasks, default=root",
                kind=str,
                optional=True,
                default="root",
            ),
            Argument(
                names=(
                    PyDeployProgram.ARG_REQUESTS_DISABLE_WARNINGS_LONG,
                    PyDeployProgram.ARG_REQUESTS_DISABLE_WARNINGS_SHORT,
                ),
                help="Configure the requests lib such that it will disable SSL warnings, default=False",
                kind=bool,
                default=False,
                optional=True,
            ),
            Argument(
                name=PyDeployProgram.ARG_SSH_PORT,
                help="The ssh port to use for connecting to hosts for deployment operations",
                kind=int,
                default=22,
                optional=True,
            ),
            Argument(
                name=PyDeployProgram.ARG_SSH_IDENTITY_FILE,
                help="The ssh identity file to use for connecting to hosts for deployment operations",
                kind=str,
                default=None,
                optional=True,
            ),
        ]
        return core_args + extra_args

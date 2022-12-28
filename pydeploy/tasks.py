import importlib
from invoke import task
from invoke.parser import ParserContext
from pydeploy.program import PyDeployProgram
from pydeploy.configs import Configs


class Tasks(object):

    PROGRAM = None
    NAMESPACE = None

    @staticmethod
    def get_config_value(core_args: ParserContext, key: str) -> any:
        arg = core_args[0].args[key]
        return arg.value

    @task
    def load_configs(_):
        """
        Will return an updated Collection (namespace) that includes a "configs" key which maps to a
        Configs instance and a "distro" key which maps to an instance of a concrete implementation
        of the pydeploy.distributions.Distribution class.
        """

        # Read the custom core arguments from the Program instance
        core = Tasks.PROGRAM.core
        pydeploy_config_dir = Tasks.get_config_value(
            core, PyDeployProgram.ARG_PYDEPLOY_CONFIG_PATH_LONG
        )

        config_file_path = Tasks.get_config_value(core, PyDeployProgram.ARG_CONFIG_PATH_LONG)
        hosts = Tasks.get_config_value(core, PyDeployProgram.ARG_HOSTS)
        hosts_connection_user = Tasks.get_config_value(
            core, PyDeployProgram.ARG_HOSTS_CONNECTION_USER_LONG
        )
        hosts_ssh_port = Tasks.get_config_value(core, PyDeployProgram.ARG_SSH_PORT)
        hosts_ssh_identity_file = Tasks.get_config_value(
            core, PyDeployProgram.ARG_SSH_IDENTITY_FILE
        )
        requests_disable_warnings = Tasks.get_config_value(
            core, PyDeployProgram.ARG_REQUESTS_DISABLE_WARNINGS_LONG
        )

        configs = Configs(
            pydeploy_config_dir=pydeploy_config_dir,
            config_file_path=config_file_path,
            hosts=hosts,
            hosts_connection_user=hosts_connection_user,
            hosts_ssh_port=hosts_ssh_port,
            hosts_ssh_identity_file=hosts_ssh_identity_file,
            requests_disable_warnings=requests_disable_warnings,
        )
        configs.init()

        # Dynamically instantiate our distribution class instance
        distro_module_name = f"pydeploy.distributions.{configs.distro.name.lower()}"
        distro_class_name = configs.distro.value
        distro_class = getattr(importlib.import_module(distro_module_name), distro_class_name)
        distro = distro_class(configs)

        # Update the namespace with the configs, and the distro instance
        Tasks.NAMESPACE.configure({"configs": configs, "distro": distro})

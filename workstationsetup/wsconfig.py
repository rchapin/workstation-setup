import logging
import os
import yaml
from invoke.exceptions import Exit
from workstationsetup import utils
from workstationsetup.enums import ConfigUpdateMode
from workstationsetup.enums import Distro, ConfigUpdateMode

logging.basicConfig(level=logging.INFO)


class WsConfig(object):

    ENV_PREFIX = "WS_SETUP"
    ENV_DISTRO = f"{ENV_PREFIX}_DISTRO"
    ENV_USER_CONFIGS = f"{ENV_PREFIX}_USER_CONFIGS"

    # An env var that is exported and set to 'true' will configure requests such that it will disable
    # SSL warnings.
    ENV_REQUESTS_DISABLE_WARNINGS = f"{ENV_PREFIX}_REQUESTS_DISABLE_WARN"

    REQUIRED_ENV_VARS = [ENV_DISTRO]

    CONFIGS_DIR = "configs"

    @staticmethod
    def load_base_configs(distro) -> dict:
        cfg_path = os.path.join(
            os.getcwd(), WsConfig.CONFIGS_DIR, f"{distro.name.lower()}.yaml"
        )
        retval = None
        with open(cfg_path, "r") as f:
            retval = yaml.safe_load(f)
        return retval

    def __init__(self) -> None:
        self.env_cfgs = None
        self.distro = None
        self.distro_version = None
        self.requests_disable_warnings = False
        self.distro_cfgs = None
        self.common_cfgs = None
        self.user_cfgs = None
        self.configs = None
        self.init()
        logging.info("WsConfig initialization complete")

    @staticmethod
    def get_env_configs() -> dict:
        retval = WsConfig.get_env_vars()

        for required_env_var in WsConfig.REQUIRED_ENV_VARS:
            if required_env_var not in retval:
                raise Exit(
                    f"Missing required env var; required_env_var={required_env_var}"
                )

        return retval

    @staticmethod
    def get_env_vars() -> dict:
        retval = {}
        for k, v in os.environ.items():
            if k.startswith(WsConfig.ENV_PREFIX):
                retval[k] = v
        return retval

    def get_task_configs(self, task) -> dict:
        return self.configs[task]

    def init(self) -> None:
        # Read in the required env vars
        self.env_cfgs = WsConfig.get_env_configs()

        distro_and_version = self.env_cfgs[WsConfig.ENV_DISTRO]
        distro_tokens = distro_and_version.split("_")
        self.distro = Distro.get_by_name(distro_tokens[0])
        self.distro_version = distro_tokens[1]

        # Read in all of the required config files
        ws_configs_dir = os.path.join(os.getcwd(), WsConfig.CONFIGS_DIR)
        distro_cfg_file_name = f"{self.distro.name.lower()}_{self.distro_version}.yaml"
        distro_cfg_path = os.path.join(ws_configs_dir, distro_cfg_file_name)
        self.distro_cfgs = utils.load_yaml_file(distro_cfg_path)
        common_cfg_path = os.path.join(ws_configs_dir, f"common.yaml")
        self.common_cfgs = utils.load_yaml_file(common_cfg_path)

        # Read in any user overrides/enrichment configs if they are provided
        self.user_cfgs = None
        if WsConfig.ENV_USER_CONFIGS in self.env_cfgs:
            self.user_cfgs = utils.load_yaml_file(self.env_cfgs[WsConfig.ENV_USER_CONFIGS])
        if WsConfig.ENV_REQUESTS_DISABLE_WARNINGS in self.env_cfgs:
            self.requests_disable_warnings = True

        # Merge the distro and common configs into a single dict
        self.configs = {**self.distro_cfgs, **self.common_cfgs}

        # Iterate over all of the keys in the user_cfgs and update the configs dict based on the
        # user customizations.
        if self.user_cfgs is None:
            return
        for user_task, user_task_cfg in self.user_cfgs.items():
            logging.info("Updating config for task; user_task={user_task}")
            # Iterate over all of the keys for this task and update the configs
            for user_task_cfg_key, user_task_cfg_val in user_task_cfg.items():
                # Determine the mode and based on that update the same key in the configs dict with
                # the current value
                if user_task_cfg_val["mode"] == ConfigUpdateMode.APPEND.name:
                    logging.info(
                        f"Appending config; task={user_task_cfg_key}, cfg_key={user_task_cfg_key}, value={user_task_cfg_val['value']}"
                    )
                    self.configs[user_task][user_task_cfg_key].extend(
                        user_task_cfg_val["value"]
                    )
                elif user_task_cfg_val["mode"] == ConfigUpdateMode.OVERRIDE.name:
                    self.configs[user_task][user_task_cfg_key] = user_task_cfg_val[
                        "value"
                    ]

    def is_request_warnings_disabled(self) -> bool:
        return self.requests_disable_warnings

    def is_request_verify(self) -> bool:
        return True if self.requests_disable_warnings is False else False

import copy
import logging
import os
from fabric import Connection
from pydeploy.enums import ConfigUpdateMode
from pydeploy.enums import Distro, ConfigUpdateMode
from pydeploy.utils import Utils

logging.basicConfig(level=logging.INFO)


class Configs(object):
    def __init__(
        self,
        pydeploy_config_dir: str,
        config_file_path: str,
        hosts: str,
        hosts_connection_user: str,
        hosts_ssh_port: int,
        hosts_ssh_identity_file: str = None,
        requests_disable_warnings: bool = False,
    ) -> None:

        self.pydeploy_config_dir = pydeploy_config_dir
        self.config_file_path = config_file_path
        self.hosts = hosts.split(",")
        self.hosts_connection_user = hosts_connection_user
        self.hosts_ssh_port = hosts_ssh_port
        self.hosts_ssh_identity_file = hosts_ssh_identity_file
        self.requests_disable_warnings = requests_disable_warnings
        self.connections = None

        self.config_file_data = None
        self.distro = None
        self.distro_version = None
        self.distro_window_manager = None

        self.common_configs = None
        self.distro_configs = None
        self.task_configs_overrides = None

        # The common, distro, and task_configs_overrides are merged together into this config dict.
        self.configs = None

    @staticmethod
    def apply_override_configs(base_configs: dict, override_configs: dict) -> dict:
        retval = copy.deepcopy(base_configs)

        # Iterate over all of the keys in the overrides and update the base configs
        # dict based on the user customizations.
        for override_task, override_task_cfg in override_configs.items():
            # Iterate over all of the keys for this task and update the configs
            for override_task_cfg_key, override_task_cfg_val in override_task_cfg.items():
                # Determine the mode and based on that update the same key in the configs dict with
                # the current value
                if override_task_cfg_val["mode"] == ConfigUpdateMode.APPEND.name:
                    logging.info(
                        f"Appending config; task={override_task}, cfg_key={override_task_cfg_key}, value={override_task_cfg_val['value']}"
                    )
                    retval[override_task][override_task_cfg_key].extend(
                        override_task_cfg_val["value"]
                    )
                elif override_task_cfg_val["mode"] == ConfigUpdateMode.OVERRIDE.name:
                    logging.info(
                        f"Overriding config; task={override_task}, cfg_key={override_task_cfg_key}, value={override_task_cfg_val['value']}"
                    )
                    retval[override_task][override_task_cfg_key] = override_task_cfg_val["value"]

        return retval

    @staticmethod
    def create_connections(
        hosts: list[str], user: str, ssh_port: int, ssh_identity_file: str = None
    ) -> dict:
        retval = {}
        for host in hosts:
            conn = None
            if ssh_identity_file:
                conn = Connection(
                    host=host,
                    user=user,
                    port=ssh_port,
                    connect_kwargs={
                        "key_filename": ssh_identity_file,
                    },
                )
            else:
                conn = Connection(
                    host=host,
                    user=user,
                    port=ssh_port,
                )
            retval[host] = conn
        return retval

    def get_task_configs(self, task) -> dict:
        return self.configs[task]

    def init(self) -> None:
        self.config_file_data = Utils.load_yaml_file(self.config_file_path)
        self.distro = Distro.get_by_name(self.config_file_data["distro"]["name"].lower())
        self.distro_version = self.config_file_data["distro"]["version"]
        if "window_manager" in self.config_file_data["distro"]:
            self.distro_window_manager = self.config_file_data["distro"]["window_manager"]
        if "task_configs" in self.config_file_data:
            self.task_configs_overrides = self.config_file_data["task_configs"]

        self.connections = Configs.create_connections(
            self.hosts,
            self.hosts_connection_user,
            self.hosts_ssh_port,
            self.hosts_ssh_identity_file,
        )

        # Load both the common configs and the distro configs and merge the common configs into the
        # distro configs dics.
        common_configs_path = os.path.join(self.pydeploy_config_dir, "common", "common.yaml")
        self.common_configs = Utils.load_yaml_file(common_configs_path)
        distro_configs_file_name = f"{self.distro.name.lower()}_{self.distro_version}.yaml"
        distro_configs_path = os.path.join(
            self.pydeploy_config_dir, "distros", distro_configs_file_name
        )
        distro_configs = Utils.load_yaml_file(distro_configs_path)
        # self.distro_configs = copy.deepcopy(distro_configs)
        # self.distro_configs.update(self.common_configs)
        self.distro_configs = Configs.merge_configs(self.common_configs, distro_configs)

        # If the user has provided any task override configs in the config file, merge those with the
        # distro configs.
        if self.task_configs_overrides is None:
            self.configs = self.distro_configs
        else:
            self.configs = Configs.apply_override_configs(
                base_configs=self.distro_configs,
                override_configs=self.task_configs_overrides,
            )
        logging.info("Configs initialization complete")

    def is_request_warnings_disabled(self) -> bool:
        return self.requests_disable_warnings

    def is_request_verify(self) -> bool:
        return True if self.requests_disable_warnings is False else False

    @staticmethod
    def merge_configs(a: dict, b: dict) -> dict:
        retval = {}

        # Base case: There are no matching keys in the dict that are dicts.
        a_keys = set(a.keys())
        b_keys = set(b.keys())
        all_keys = a_keys.union(b_keys)

        # Iterate over the union of the set of keys and see if there is an entry for that
        # key in both dicts.  If not, simply add the key to our retval.  If there is,
        # check to see if both of those values are dicts themselves, and recurse
        for key in all_keys:
            if key in a_keys and key in b_keys:
                if type(a[key]) is dict and type(b[key]) is dict:
                    merged_key = Configs.merge_configs(a[key], b[key])
                    retval[key] = merged_key
                else:
                    # We are not going to go down the route of trying to figure out which
                    # of the duplicate values that we should keep for a given key, so we
                    # will just take the a key and document the API to that effect.
                    retval[key] = a[key]
            else:
                retval[key] = a[key] if key in a else b[key]

        return retval

    def __str__(self) -> str:
        return (
            "Configs[\n"
            f"  pydeploy_config_dir={self.pydeploy_config_dir}\n"
            f"  config_file_path={self.config_file_path}\n"
            f"  hosts={self.hosts}\n"
            f"  hosts_connection_user={self.hosts_connection_user}\n"
            f"  requests_disable_warnings={self.requests_disable_warnings}\n"
            f"  connections={self.connections}\n"
            f"  distro={self.distro}\n"
            f"  distro_version={self.distro_version}\n"
            f"  distro_window_manager={self.distro_window_manager}\n"
            f"  distro_configs={self.distro_configs}\n"
            f"  common_configs={self.common_configs}\n"
            f"  task_configs_overrides={self.task_configs_overrides}\n"
            f"  configs={self.configs}"
            "]"
        )

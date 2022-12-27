import tempfile
import logging
from abc import ABC, abstractmethod
from string import Template
from workstationsetup import utils
from invoke import Context


class Distribution(ABC):
    def __init__(self, ws_cfgs) -> None:
        super().__init__()
        self.ws_cfgs = ws_cfgs

    def add_repo(self, c, task) -> None:
        temp_dir = None
        try:
            temp_dir = tempfile.TemporaryDirectory()
            cfgs = self.ws_cfgs.get_task_configs(task)

            # Determine the architecture and the release and expand the repo file contents and then
            # add the expanded value to the cfg dict.
            repo_file_dict = dict(
                architecture=self.get_architecture(c),
                release=self.get_release(c),
            )
            repo_file_contents = Template(cfgs["repo_file_template"]).safe_substitute(repo_file_dict)
            cfgs["repo_file_contents"] = repo_file_contents

            self.add_repo_impl(c, cfgs, temp_dir)
        finally:
            temp_dir.cleanup()

    @abstractmethod
    def add_repo_impl(self, task, c, temp_dir) -> None:
        pass

    @abstractmethod
    def get_architecture(self, c: Context) -> str:
        pass

    @abstractmethod
    def get_install_packages_cmd(self, packages_list) -> str:
        pass

    @abstractmethod
    def get_release(self, c: Context) -> str:
        pass

    def get_task_configs(self, task) -> dict:
        return self.ws_cfgs.get_task_configs(task)

    def install_package(self, c: Context, packages) -> None:
        if type(packages) != list:
            packages = [packages]
        packages_str = " ".join(packages)
        install_cmd = self.get_install_packages_cmd(c=c, packages_str=packages_str)

        r = c.conn.run(install_cmd)
        if not r.failed:
            logging.info(f"Packages successfully installed, packages={packages}")

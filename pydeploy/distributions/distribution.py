import tempfile
import logging
from abc import ABC, abstractmethod
from string import Template
from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory
from pydeploy.configs import Configs
from pydeploy.enums import PackageCommand


class Distribution(ABC):
    def __init__(self, configs: Configs) -> None:
        super().__init__()
        self.configs = configs

    def add_repo(self, configs: Configs, conn: Connection, task: str) -> None:
        task_configs = self.configs.get_task_configs(task)

        # Determine the architecture and the release and expand the repo file contents and then
        # add the expanded value to the cfg dict.
        repo_file_dict = dict(
            architecture=self.get_architecture(conn),
            release=self.get_release(conn),
        )
        repo_file_contents = Template(task_configs["repo_file_template"]).safe_substitute(
            repo_file_dict
        )
        task_configs["repo_file_contents"] = repo_file_contents

        self.add_repo_impl(configs, conn, task_configs)

    @abstractmethod
    def add_repo_impl(self, configs: Configs, conn: Connection, task_configs: dict) -> None:
        pass

    def add_user_to_group(self, conn: Connection, user: str, groups) -> None:
        if type(groups) != list:
            groups = [groups]
        for g in groups:
            r = conn.run(f"usermod -aG {g} {user}")
            logging.info(
                f"User added to group, user={user}, group={g} cmdStdOut=[{r.stdout.strip()}], cmdStdErr=[{r.stderr.strip()}]]"
            )
            print(
                f"If this is the first time you have added user [{user}] to the group {g} ",
                "you will need to log out of your session and then log back in to use the ",
                "group restricted commands",
            )

    def _apply_packages_command(
        self,
        conn: Connection,
        package_command: PackageCommand,
        packages,
        local_packages: bool = False,
    ) -> None:
        if type(packages) != list:
            packages = [packages]
        packages_str = " ".join(packages)

        cmd = None
        if package_command == PackageCommand.INSTALL:
            cmd = (
                self.get_install_local_packages_cmd(packages_str)
                if local_packages
                else self.get_install_packages_cmd(packages=packages_str)
            )
        if package_command == PackageCommand.REMOVE:
            cmd = self.get_remove_packages_cmd(packages=packages_str)

        conn.run(self.get_update_packages_cmd())
        r = conn.run(cmd)
        if not r.failed:
            logging.info(f"Success; package_command={package_command.name}, packages={packages}")

    @abstractmethod
    def get_architecture(self, conn: Connection) -> str:
        pass

    @abstractmethod
    def get_install_packages_cmd(self, packages: str) -> str:
        pass

    @abstractmethod
    def get_install_local_packages_cmd(self, packages: str) -> str:
        pass

    @abstractmethod
    def get_release(self, conn: Connection) -> None:
        pass

    @abstractmethod
    def get_remove_packages_cmd(self, packages: str) -> str:
        pass

    def get_task_configs(self, task: str) -> dict:
        return self.configs.get_task_configs(task)

    @abstractmethod
    def get_update_packages_cmd(self) -> str:
        pass

    @abstractmethod
    def install_cert(
        self,
        ctx: Context,
        conn: Connection,
        task_configs: dict,
        cert_path: str,
        cert_dir_name: str,
        cert_validation_str,
    ) -> bool:
        pass

    def install_local_package(self, conn: Connection, packages_paths: list[str]) -> None:
        self._apply_packages_command(
            conn=conn,
            package_command=PackageCommand.INSTALL,
            packages=packages_paths,
            local_packages=True,
        )

    def install_package(self, conn: Connection, packages) -> None:
        self._apply_packages_command(
            conn=conn,
            package_command=PackageCommand.INSTALL,
            packages=packages,
            local_packages=False,
        )

    def is_cert_in_cert_bundle(
        self, conn: Connection, ca_certs_bundle_path: str, cert_validation_string: str
    ) -> bool:
        # Validate that there is a cert in the bundle that contains the provided string.
        cmd_tmpl = "awk -v cmd='openssl x509 -noout -subject' '/BEGIN/{close(cmd)};{print | cmd}' < ${ca_certs_bundle_path} | grep -i ${cert_validation_string}"
        validation_cmd = Template(cmd_tmpl).substitute(
            cert_validation_string=cert_validation_string, ca_certs_bundle_path=ca_certs_bundle_path
        )
        r = conn.run(validation_cmd)
        r_stdout = r.stdout.strip()
        r_stderr = r.stderr.strip()
        if cert_validation_string in r.stdout.lower():
            logging.info(
                f"CA cert was found in bundle; ca_certs_bundle_path={ca_certs_bundle_path}, r_stdout={r_stdout}, r_stderr={r_stderr}"
            )
            return True
        else:
            logging.error(
                f"Unable to find CA cert in certificate bundle, ca_certs_bundle_path={ca_certs_bundle_path}, r_stdout={r_stdout}, r_stderr={r_stderr}"
            )
            return False

    def remove_package(self, conn: Connection, packages) -> None:
        self._apply_packages_command(
            conn=conn,
            package_command=PackageCommand.REMOVE,
            packages=packages,
        )

    @abstractmethod
    def verify_package(
        self,
        conn: Connection,
        temp_dir: TemporaryDirectory,
        package_file_path: str,
        public_key_file_path: str,
        verify_configs: dict,
    ) -> bool:
        pass

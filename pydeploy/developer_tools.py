import os
import requests
from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory
from string import Template
from pydeploy.utils import Utils, HashAlgo


class DeveloperTools(object):
    REDSHIFT_CONFIG_TEMPLATE = """[redshift]
temp-day=${temp_day}
temp-night=${temp_night}
brightness-day=${brightness_day}
brightness-night=${brightness_night}
location-provider=${location_provider}
"""

    REDSHIFT_FEEDBACK = """redshift has been installed for the specified user.
That user will need to enable and start the redshift service when they login
with the following commands
  systemctl --user enable redshift
  systemctl --user start redshift
"""

    REDSHIFT_UNIT_FILE = """[Unit]
Description=Runs redshift

[Service]
ExecStart=/usr/bin/redshift

[Install]
WantedBy = default.target
"""

    @staticmethod
    def install_drawio_get_dependencies(ctx: Context, temp_dir: TemporaryDirectory) -> dict:
        errors = []
        retval = {}

        configs = ctx.distro.configs
        task_configs = ctx.distro.get_task_configs("install-drawio")
        verify = ctx.distro.configs.is_request_verify()
        github_release_info = Utils.get_github_release_info(
            url=task_configs["github_release_url"],
            artifact_regex=task_configs["artifact_regex"],
            hashes_regex=task_configs["hashes_regex"],
            verify=verify,
        )

        # Download the artifact and then validate the checksum
        artifact_local_path, hashes_local_path = Utils.download_github_artifact_and_checksum(
            configs=configs, github_release_info=github_release_info, temp_dir=temp_dir
        )

        hashes_line_pattern = f".*{github_release_info.artifact_filename}.*"
        if not Utils.file_checksum_with_checksum_file(
            file_path=artifact_local_path,
            hashes_file_path=hashes_local_path,
            hashes_file_pattern=hashes_line_pattern,
            hashes_line_token=1,
            hash_algo=HashAlgo.SHA256SUM,
        ):
            raise Exception(
                f"checking sha256sum on file mismatch; "
                f"artifact_local_path={artifact_local_path}, "
                f"hashes_local_path={hashes_local_path}, "
            )

        retval["artifact_local_path"] = artifact_local_path
        retval["artifact_filename"] = github_release_info.artifact_filename
        return retval

    @staticmethod
    def install_drawio(ctx: Context, conn: Connection, dependencies: dict) -> None:
        artifact_remote_path = os.path.join(
            "/var/tmp/", dependencies["install-drawio"]["artifact_filename"]
        )
        conn.put(dependencies["install-drawio"]["artifact_local_path"], artifact_remote_path)
        packages_paths = [artifact_remote_path]
        ctx.distro.install_local_package(conn=conn, packages_paths=packages_paths)
        conn.run(f"rm -f {artifact_remote_path}")

    @staticmethod
    def install_minikube_get_dependencies(
        ctx: Context, architectures: dict, temp_dir: TemporaryDirectory = None, version: str = None
    ) -> dict:
        retval = {}

        managed_temp_dir = False
        if temp_dir is None:
            managed_temp_dir = True
            temp_dir = TemporaryDirectory()

        configs = ctx.distro.configs
        task_configs = ctx.distro.get_task_configs("install-minikube")

        for architecture in architectures:
            architecture_downloads = {}
            for download in ["minikube", "kvm2_driver"]:
                binary_file_name = Template(task_configs[download]["binary_template"]).substitute(
                    architecture=architecture
                )
                sha256sum_file_name = Template(
                    task_configs[download]["sha256sum_template"]
                ).substitute(architecture=architecture)
                binary_url = f"{task_configs['base_url']}/{binary_file_name}"
                sha256sum_url = f"{task_configs['base_url']}/{sha256sum_file_name}"
                binary_local_file_name = task_configs[download]["local_file_name"]
                binary_local_file_path = os.path.join(temp_dir.name, binary_local_file_name)
                Utils.download_file(
                    configs=configs,
                    url=binary_url,
                    target_local_path=binary_local_file_path,
                )
                r = requests.get(url=sha256sum_url, verify=configs.is_request_verify())
                if not r.ok:
                    raise Exception(
                        f"Unable to get sha256sum; sha256sum_url={sha256sum_url}, r={r}"
                    )
                sha256sum = r.text.strip()
                if not Utils.file_checksum(
                    file_path=binary_local_file_path,
                    checksum=sha256sum,
                    hash_algo=HashAlgo.SHA256SUM,
                ):
                    raise Exception(
                        "Checksum for downloaded file did not match; "
                        f"binary_local_file_path={binary_local_file_path}"
                    )
                architecture_downloads[download] = dict(
                    binary_local_file_path=binary_local_file_path,
                    binary_file_name=binary_local_file_name,
                )
            retval[architecture] = architecture_downloads

        if managed_temp_dir:
            temp_dir.cleanup()

        return retval

    @staticmethod
    def install_minikube(
        ctx: Context, conn: Connection, dependencies: dict = None, minikube_user: str = None
    ) -> None:
        distro = ctx.distro
        configs = distro.configs
        task_configs = distro.get_task_configs("install-minikube")
        ctx.distro.install_package(conn, task_configs["packages"])
        architecture = distro.get_architecture(conn)
        binaries_to_install = [
            dependencies["install-minikube"][architecture]["minikube"],
            dependencies["install-minikube"][architecture]["kvm2_driver"],
        ]
        for binary_to_install in binaries_to_install:
            target_path = os.path.join("/usr/local/bin", binary_to_install["binary_file_name"])
            conn.put(binary_to_install["binary_local_file_path"], target_path)
            conn.run(f"chmod 755 {target_path}")
            conn.run(f"chown root: {target_path}")

        # Add the specified minikube_user to the required groups
        if minikube_user:
            ctx.distro.add_user_to_group(
                conn=conn, user=minikube_user, groups=["libvirt", "libvirt-qemu"]
            )

    @staticmethod
    def install_redshift(
        ctx: Context,
        conn: Connection,
        redshift_user: str,
        dependencies: dict = None,
        temp_day: str = None,
        temp_night: str = None,
        brightness_day: float = None,
        brightness_night: float = None,
    ) -> None:
        if dependencies is None:
            dependencies = DeveloperTools.install_redshift_get_dependencies(
                ctx=ctx,
                temp_day=temp_day,
                temp_night=temp_night,
                brightness_day=brightness_day,
                brightness_night=brightness_night,
            )
        distro = ctx.distro
        configs = distro.configs
        task_configs = distro.get_task_configs("install-redshift")

        r = conn.run(f"grep {redshift_user} /etc/passwd")
        etc_passwd_line = r.stdout
        user_home = etc_passwd_line.split(":")[5]
        user_config_dir = os.path.join(user_home, ".config")
        user_home_dirs = [
            user_config_dir,
            os.path.join(user_config_dir, "systemd"),
            os.path.join(user_config_dir, "systemd", "user"),
        ]
        for dir in user_home_dirs:
            conn.run(f"mkdir -p {dir}")
            conn.run(f"chown {redshift_user}: {dir}")
        conn.run(f"chmod 0700 {user_config_dir}")

        redshift_target_config_path = os.path.join(user_config_dir, "redshift.conf")
        redshift_target_unit_file_path = os.path.join(
            user_config_dir, "systemd", "user", "redshift.service"
        )
        redshift_dependencies = dependencies["install-redshift"]
        conn.put(redshift_dependencies["redshift_configs_path"], redshift_target_config_path)
        conn.put(redshift_dependencies["redshift_unit_file_path"], redshift_target_unit_file_path)
        for dir in [redshift_target_config_path, redshift_target_unit_file_path]:
            conn.run(f"chown {redshift_user}: {dir}")

    def install_redshift_get_dependencies(
        ctx: Context,
        temp_dir: TemporaryDirectory = None,
        temp_day: str = None,
        temp_night: str = None,
        brightness_day: float = None,
        brightness_night: float = None,
    ) -> dict:
        managed_temp_dir = False
        if temp_dir is None:
            managed_temp_dir = True
            temp_dir = TemporaryDirectory()

        distro = ctx.distro
        configs = distro.configs
        task_configs = distro.get_task_configs("install-redshift")

        config_dict = dict(
            temp_day=temp_day if temp_day is not None else task_configs["temp_day"],
            temp_night=temp_night if temp_night is not None else task_configs["temp_night"],
            brightness_day=brightness_day
            if brightness_day is not None
            else task_configs["brightness_day"],
            brightness_night=brightness_night
            if brightness_night is not None
            else task_configs["brightness_night"],
            location_provider=task_configs["location_provider"],
        )
        redshift_configs = Template(DeveloperTools.REDSHIFT_CONFIG_TEMPLATE).substitute(config_dict)
        redshift_configs_path = os.path.join(temp_dir.name, "redshift.conf")
        with open(redshift_configs_path, "w") as f:
            f.write(redshift_configs)
        redshift_unit_file_path = os.path.join(temp_dir.name, "redshift.service")
        with open(redshift_unit_file_path, "w") as f:
            f.write(DeveloperTools.REDSHIFT_UNIT_FILE)

        if managed_temp_dir:
            temp_dir.cleanup()

        return {
            "redshift_configs_path": redshift_configs_path,
            "redshift_unit_file_path": redshift_unit_file_path,
        }

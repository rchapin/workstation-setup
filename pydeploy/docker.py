import copy
import json
import os
from io import StringIO
from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory
from pydeploy.utils import Utils, HashAlgo


class Docker(object):

    DOCKER_DAEMON_JSON_BIP_DEFAULT = "10.27.0.1/24"
    DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT = "10.27.0.1/25"
    DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT = "10.28.0.0/16"
    DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT = 24

    ARG_HELP_DOCKER_BIP = (
        "OPTIONAL - The overriding cidr network for the docker bridge; "
        f"example: {DOCKER_DAEMON_JSON_BIP_DEFAULT}"
    )
    ARG_HELP_DOCKER_FIXED_CIDR = (
        "OPTIONAL - The overriding cidr network for the fixed-cidr config; "
        f"example: {DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT}"
    )

    ARG_HELP_DOCKER_ADDR_POOLS_BASE = (
        "OPTIONAL - The overriding cidr network for the docker default-address-pools.base config; "
        f"example: {DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT}"
    )
    ARG_HELP_DOCKER_ADDR_POOLS_SIZE = (
        "OPTIONAL - The overriding cidr network for the docker default-address-pools.size config; "
        f"example: {DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT}"
    )
    ARG_HELP_DOCKER_INSECURE_REGISTRIES = (
        "OPTIONAL - If your org hosts registries without TLS or self signed certs include a CSV of entries; "
        f"example: git.example.com:8443,git.scm.example.com:8443"
    )

    DOCKER_ARCH_MAP = {
        "amd64": "x86_64",
    }

    DOCKER_DAEMON_JSON_DEFAULT = {
        "bip": DOCKER_DAEMON_JSON_BIP_DEFAULT,
        "fixed-cidr": DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT,
        "default-address-pools": [
            {
                "base": DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT,
                "size": DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT,
            }
        ],
    }

    @staticmethod
    def get_docker_mapped_architecture(architecture) -> str:
        if architecture in Docker.DOCKER_ARCH_MAP:
            return Docker.DOCKER_ARCH_MAP[architecture]
        else:
            return architecture

    @staticmethod
    def get_dependencies(ctx: Context, temp_dir: TemporaryDirectory, architectures: set) -> dict:
        configs = ctx.distro.configs
        task_configs = ctx.distro.get_task_configs("install-docker")

        # For each of the architectures download the required docker-compose binary.
        retval_architectures = {}
        for architecture in architectures:
            # Get the correct architecture string
            mapped_architecture = Docker.get_docker_mapped_architecture(architecture)

            # Hit the github repo and figure out the URL of the latest version, plus the sha256 sums.
            # In this case, we dynamically generate the artifact and hashes regex
            binary_filename = f"docker-compose-linux-{mapped_architecture}"
            hashes_filename = f"{binary_filename}.sha256"
            verify = ctx.distro.configs.is_request_verify()
            github_release_info = Utils.get_github_release_info(
                url=task_configs["github_release_url"],
                artifact_regex=binary_filename,
                hashes_regex=hashes_filename,
                verify=verify,
            )

            # Download the artifact and then validate the checksum
            artifact_local_path, hashes_local_path = Utils.download_github_artifact_and_checksum(
                configs=configs, github_release_info=github_release_info, temp_dir=temp_dir
            )

            # Validate the checksum for the downloaded file
            hashes_line_pattern = f".*{github_release_info.artifact_filename}.*"
            if not Utils.file_checksum_with_checksum_file(
                file_path=artifact_local_path,
                hashes_file_path=hashes_local_path,
                hashes_file_pattern=hashes_line_pattern,
                hashes_line_token=0,
                hash_algo=HashAlgo.SHA256SUM,
            ):
                raise Exception(
                    f"checking sha256sum on file mismatch; "
                    f"artifact_local_path={artifact_local_path}, "
                    f"hashes_local_path={hashes_local_path}, "
                )

            arch_artifacts = {
                "binary_filename": github_release_info.artifact_filename,
                "binary_local_file_path": artifact_local_path,
            }
            retval_architectures[mapped_architecture] = arch_artifacts

        return {"architectures": retval_architectures}

    @staticmethod
    def install(
        ctx: Context,
        conn: Connection,
        dependencies: dict,
        docker_user: str,
        docker_bip: str,
        docker_fixed_cidr: str,
        docker_default_addr_pools_base: str,
        docker_default_addr_pools_size: int,
        docker_insecure_registries: str,
    ):
        # Add the docker repo and install the packages
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-docker")
        task_configs = ctx.distro.get_task_configs("install-docker")
        packages = task_configs["packages"]
        ctx.distro.install_package(conn=conn, packages=packages)

        # The dependencies dict contains an "architecture" key which contains another dict that
        # contains artifacts specific to each architecture. The architecture that is returned by the
        # OS may not necessarily match the string that the docker maintainers have used for the
        # specific binary so we resolve it via our map.
        docker_dependencies = dependencies["install-docker"]
        os_arch = ctx.distro.get_architecture(conn)
        architecture = Docker.get_docker_mapped_architecture(os_arch)
        architecture_dependencies = docker_dependencies["architectures"][architecture]

        binary_file_remote_file_path = os.path.join("/var/tmp/", architecture_dependencies["binary_filename"])
        conn.put(architecture_dependencies["binary_local_file_path"], binary_file_remote_file_path)
        conn.run(f"chmod +x {binary_file_remote_file_path}")
        conn.run(f"mv -f {binary_file_remote_file_path} /usr/local/bin/")
        # Remove a possibly pre-existing symlink and then add it
        conn.run(f"rm -f /usr/local/bin/docker-compose")
        conn.run(
            f"ln -s /usr/local/bin/{architecture_dependencies['binary_filename']} /usr/local/bin/docker-compose"
        )

        # Customize and then write out the docker daemon.json file.  Put it on the remote host and
        # then restart docker.
        daemon_json = copy.deepcopy(Docker.DOCKER_DAEMON_JSON_DEFAULT)
        daemon_json["bip"] = docker_bip
        daemon_json["fixed-cidr"] = docker_fixed_cidr
        daemon_json["default-address-pools"][0]["base"] = docker_default_addr_pools_base
        daemon_json["default-address-pools"][0]["size"] = docker_default_addr_pools_size

        if docker_insecure_registries:
            # Split on the ',' and create a list
            docker_insecure_registries_entries = docker_insecure_registries.split(",")
            daemon_json["insecure-registries"] = docker_insecure_registries_entries

        daemon_json_str = json.dumps(daemon_json, indent=2)
        target_daemon_json_path = "/etc/docker/daemon.json"
        conn.put(StringIO(daemon_json_str), target_daemon_json_path)
        conn.run(f"chown root: {target_daemon_json_path}")
        conn.run("systemctl restart docker")

        # Add the specified docker use to the docker group
        if docker_user:
            ctx.distro.add_user_to_group(conn=conn, user=docker_user, groups="docker")

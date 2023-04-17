import os
import requests
from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory
from pydeploy.utils import  HashAlgo, ArchiveType, Utils


class Kubernetes(object):
    @staticmethod
    def get_helm_dependencies(
        ctx: Context, temp_dir: TemporaryDirectory, architectures: set
    ) -> dict:
        configs = ctx.distro.configs
        task_configs = ctx.distro.get_task_configs("install-helm")

        # For each of the architectures download the required tarball
        retval_architectures = {}
        for architecture in architectures:
            tarball_file_name = f"helm-v{task_configs['version']}-linux-{architecture}.tar.gz"
            tarball_url = f"{task_configs['base_url']}/{tarball_file_name}"
            tarball_local_file_path = os.path.join(temp_dir.name, tarball_file_name)
            Utils.download_file(
                configs=ctx.distro.configs,
                url=tarball_url,
                target_local_path=tarball_local_file_path,
            )

            shasum_file_name = f"{tarball_file_name}.sha256sum"
            r = requests.get(
                f"{task_configs['base_url']}/{shasum_file_name}",
                verify=configs.is_request_verify(),
            )
            shasum = r.text.split()[0]
            if not Utils.file_checksum(
                file_path=tarball_local_file_path, checksum=shasum, hash_algo=HashAlgo.SHA256SUM
            ):
                raise Exception(
                    f"Checksum for helm tarball did not match expected checksum; "
                    f"file_path={tarball_local_file_path}, check_sum={shasum}, "
                    f"hash_algo={HashAlgo.SHA256SUM}"
                )

            arch_artifacts = {
                "filename": tarball_file_name,
                "local_file_path": tarball_local_file_path,
            }
            retval_architectures[architecture] = arch_artifacts

        return {"architectures": retval_architectures}

    @staticmethod
    def install_helm(ctx: Context, conn: Connection, dependencies: dict) -> None:
        # The dependencies dict contains an "architecture" key which contains another dict that
        # contains artifacts specific to each architecture.
        helm_dependencies = dependencies["install-helm"]
        architecture = ctx.distro.get_architecture(conn)
        architecture_dependencies = helm_dependencies["architectures"][architecture]

        # Copy the tarball to the remote host and unpack and "install" it.
        tarball_remote_file_path = f"/var/tmp/{architecture_dependencies['filename']}"
        conn.put(architecture_dependencies["local_file_path"], tarball_remote_file_path)

        # The expectation is that the tarball is unpacked into a directory with the following name
        unpacked_dir_name = f"linux-{architecture}"
        unpacked_dir_path = os.path.join("/var/tmp/", unpacked_dir_name)
        unpacked_binary_path = os.path.join(unpacked_dir_path, "helm")
        target_binary_path = os.path.join("/usr/local/bin", "helm")
        conn.run(f"tar -xzf {tarball_remote_file_path} -C /var/tmp")
        conn.run(f"rm -f {target_binary_path}")
        conn.run(f"mv {unpacked_binary_path} {target_binary_path}")
        conn.run(f"chmod 755 {target_binary_path}")
        conn.run(f"chown root: {target_binary_path}")
        conn.run(f"rm -rf {unpacked_dir_path} {tarball_remote_file_path}")


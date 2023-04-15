import os
from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory
from pydeploy.utils import Utils


class SignedPackages(object):
    @staticmethod
    def download_package_and_pub_key(
        ctx: Context,
        temp_dir: TemporaryDirectory,
        package_url: str,
        package_file_name: str,
        pub_key_url: str,
        pub_key_file_name: str,
    ) -> dict:
        configs = ctx.distro.configs

        package_local_path = os.path.join(temp_dir.name, package_file_name)
        Utils.download_file(
            configs=configs,
            url=package_url,
            target_local_path=package_local_path,
        )

        public_key_local_path = os.path.join(temp_dir.name, pub_key_file_name)
        Utils.download_file(
            configs=configs,
            url=pub_key_url,
            target_local_path=public_key_local_path,
        )

        return {
            "package_path": package_local_path,
            "public_key_path": public_key_local_path,
        }

    @staticmethod
    def get_dependencies(ctx: Context, temp_dir: TemporaryDirectory, task_name: str) -> dict:
        task_configs = ctx.distro.get_task_configs(task_name)

        package_url = f"{task_configs['download_url_prefix']}/{task_configs['package']}"
        return SignedPackages.download_package_and_pub_key(
            ctx=ctx,
            temp_dir=temp_dir,
            package_url=package_url,
            package_file_name=task_configs["package"],
            pub_key_url=task_configs["verification"]["public_key_url"],
            pub_key_file_name=task_configs["verification"]["public_key_filename"],
        )

    @staticmethod
    def install(
        ctx: Context,
        conn: Connection,
        temp_dir: TemporaryDirectory,
        dependencies: dict,
        task_name: str,
    ) -> None:
        task_configs = ctx.distro.get_task_configs(task_name)
        verify_configs = task_configs["verification"]

        package_remote_path = os.path.join("/var/tmp/", task_configs["package"])
        public_key_remote_path = os.path.join("/var/tmp/", verify_configs["public_key_filename"])
        conn.put(dependencies[task_name]["package_path"], package_remote_path)
        conn.put(dependencies[task_name]["public_key_path"], public_key_remote_path)

        if ctx.distro.verify_package(
            ctx=ctx,
            conn=conn,
            temp_dir=temp_dir,
            package_file_path=package_remote_path,
            public_key_file_path=public_key_remote_path,
            verify_configs=task_configs["verification"],
        ):
            ctx.distro.install_local_package(conn=conn, packages_paths=[package_remote_path])
        else:
            raise Exception(f"verifying package; package_remote_path={package_remote_path}")

        conn.run(f"rm -f {package_remote_path}")
        conn.run(f"rm -f {public_key_remote_path}")

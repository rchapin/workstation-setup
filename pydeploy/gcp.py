from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory


class Gcp(object):
    @staticmethod
    def install_google_cloud_cli(
        ctx: Context, conn: Connection, dependencies: dict = None, version: str = None
    ) -> None:
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-google-cloud-cli")
        task_configs = ctx.distro.get_task_configs("install-google-cloud-cli")
        packages = task_configs["package"]
        ctx.distro.install_package(conn=conn, packages=packages)

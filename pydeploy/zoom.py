import os
from fabric import Connection
from invoke import Context
from tempfile import TemporaryDirectory
from pydeploy.signed_packages import SignedPackages


class Zoom(object):
    TASK_NAME = "install-zoom"

    @staticmethod
    def get_dependencies(ctx: Context, temp_dir: TemporaryDirectory) -> dict:
        return SignedPackages.get_dependencies(ctx, temp_dir, task_name=Zoom.TASK_NAME)

    @staticmethod
    def install(
        ctx: Context, conn: Connection, temp_dir: TemporaryDirectory, dependencies: dict
    ) -> None:
        SignedPackages.install(ctx, conn, temp_dir, dependencies, Zoom.TASK_NAME)

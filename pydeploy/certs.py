import os
from fabric import Connection
from invoke import Context

class Certs(object):

    @staticmethod
    def install_cert(
        ctx: Context,
        conn: Connection,
        cert_dir_name: str,
        cert_path: str,
        cert_validation_string: str,
    ) -> bool:
        task_configs = ctx.distro.get_task_configs("install-cert")
        cert_file_name = os.path.basename(cert_path)
        remote_cert_path = os.path.join("/var/tmp", cert_file_name)
        conn.put(cert_path, remote_cert_path)
        success = ctx.distro.install_cert(
            ctx, conn, task_configs, remote_cert_path, cert_dir_name, cert_validation_string
        )
        return success
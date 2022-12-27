import os
from tempfile import TemporaryDirectory
from string import Template
from invoke.exceptions import Exit
from invoke import Context
from workstationsetup import utils
from workstationsetup.distributions.distribution import Distribution


class Debian(Distribution):
    def __init__(self, ws_cfgs) -> None:
        super().__init__(ws_cfgs)

    def add_repo_impl(self, c: Context, cfgs: dict, temp_dir: TemporaryDirectory) -> None:
        local_gpg_file_path = os.path.join(temp_dir.name, cfgs["key_file_name"])
        utils.download_file(
            cfgs["key_url"], local_gpg_file_path, self.ws_cfgs.is_request_verify()
        )
        remote_gpg_temp_file_path = os.path.join("/var/tmp/", cfgs["key_file_name"])
        remote_target_gpg_file_path = os.path.join(
            "/etc/apt/trusted.gpg.d", cfgs["key_file_name"]
        )
        c.conn.put(local=local_gpg_file_path, remote=remote_gpg_temp_file_path)
        c.conn.run(f"rm -f {remote_target_gpg_file_path}")
        c.conn.run(f"gpg --dearmor -o {remote_target_gpg_file_path} {remote_gpg_temp_file_path}")
        c.conn.run(f"rm -f {remote_gpg_temp_file_path}")

        # Add the repo source.list.d file.
        local_temp_file_path = os.path.join(temp_dir.name, cfgs["repo_file_name"])
        remote_temp_file_path = os.path.join("/var/tmp/", cfgs["repo_file_name"])
        remote_target_file_path = os.path.join(
            "/etc/apt/sources.list.d", cfgs["repo_file_name"]
        )

        with open(local_temp_file_path, "wt") as f:
            f.write(cfgs["repo_file_contents"])
        c.conn.put(local=local_temp_file_path, remote=remote_temp_file_path)
        c.conn.run(f"mv -f {remote_temp_file_path} {remote_target_file_path}")
        c.conn.run(f"chown root: {remote_target_file_path}")
        c.conn.run("apt-get update")

    def get_architecture(self, c: Context) -> str:
        r = c.conn.run("dpkg --print-architecture")
        if r.failed:
            raise Exit("Unable go get architecture")
        return r.stdout.strip()

    def get_install_packages_cmd(self, c: Context, packages_str: str) -> str:
        c.conn.run("apt-get update")
        return f"apt-get install -y {packages_str}"

    def get_release(self, c: Context) -> None:
        r = c.conn.run("lsb_release -cs")
        if r.failed:
            raise Exit("Unable go get release")
        return r.stdout.strip()

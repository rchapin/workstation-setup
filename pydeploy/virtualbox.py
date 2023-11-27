import copy
import json
import os
import requests
from io import StringIO
from fabric import Connection
from invoke import Context, Exit
from string import Template
from tempfile import TemporaryDirectory
from pydeploy.utils import Utils, HashAlgo


class InvalidExtPackInput(Exception):
    pass


class VirtualBox(object):
    @staticmethod
    def get_dependencies(ctx: Context, temp_dir: TemporaryDirectory) -> dict:
        task_configs = ctx.distro.get_task_configs("install-virtualbox")

        version = {
            "version_full": f"{task_configs['version']}-{task_configs['revision']}",
            "version_short": task_configs["version"],
        }
        ext_pack_url = Template(task_configs["extension_pack_url_template"]).safe_substitute(
            version
        )
        ext_pack_shasums_url = Template(
            task_configs["extension_pack_shasums_url_template"]
        ).safe_substitute(version)
        ext_pack_filename = ext_pack_url.split("/")[-1]
        ext_pack_local_file_path = os.path.join(temp_dir.name, ext_pack_filename)
        Utils.download_file(
            configs=ctx.distro.configs,
            url=ext_pack_url,
            target_local_path=ext_pack_local_file_path,
        )
        r = requests.get(ext_pack_shasums_url)
        r_text_tokens = r.text.split("\n")
        checksum = None
        for line in r_text_tokens:
            line_tokens = line.split()
            if ext_pack_filename in line_tokens[1]:
                checksum = line_tokens[0]
                break
        if checksum is None:
            raise Exception(
                "Unable to get checksum for virtualbox "
                f"ext_pack_shasums_url={ext_pack_shasums_url}"
            )
        if Utils.file_checksum(
            file_path=ext_pack_local_file_path,
            checksum=checksum,
            hash_algo=HashAlgo.SHA256SUM,
        ):
            return {
                "filename": ext_pack_filename,
                "local_file_path": ext_pack_local_file_path,
            }

        return None

    @staticmethod
    def install(ctx: Context, conn: Connection, dependencies: dict) -> None:
        # Install the repo and the package
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-virtualbox")
        task_configs = ctx.distro.get_task_configs("install-virtualbox")
        package = task_configs["package"]
        ctx.distro.install_package(conn=conn, packages=package)

        # First check to see if this extension pack is installed
        r = conn.run(f"vboxmanage list extpacks")
        if r.failed:
            raise Exit(f"Unable to list vbox extpack; r.stderr={r.stderr}")
        installed_extpacks = VirtualBox.parse_installed_extpacks(r.stdout)

        # An empty dict indicates that there is not yet any extension packs installed, nothing else
        # to do but fall through and install the extension pack defined in the configs.
        if installed_extpacks != {}:
            # Is the version that we want to install already installed?
            if (
                task_configs["version"] == installed_extpacks["version"]
                and task_configs["revision"] == installed_extpacks["revision"]
                and installed_extpacks["usable"] == True
            ):
                # We already have the correct version installed . . . nothing else to do
                return
            r = conn.run('vboxmanage extpack uninstall "Oracle VM VirtualBox Extension Pack"')

        # Put the extension pack on the remote host and install it
        virtualbox_dependencies = dependencies["install-virtualbox"]
        remote_ext_pack_file_path = os.path.join("/var/tmp/", virtualbox_dependencies["filename"])
        conn.put(virtualbox_dependencies["local_file_path"], remote_ext_pack_file_path)
        r = conn.run(f"yes y | vboxmanage extpack install {remote_ext_pack_file_path}")

    @staticmethod
    def parse_installed_extpacks(cmd_stdout: str) -> dict:
        retval = {}

        lines = cmd_stdout.splitlines()
        if len(lines) == 0:
            raise InvalidExtPackInput("extpack stdout did not contain any lines")

        found_ext_packs_line = False
        num_extpacks = None
        for line in lines:
            if "Extension Packs:" not in line:
                continue
            found_ext_packs_line = True
            # The line is expected to be something like the following
            #   "Extension Packs: 1"
            # We will split it to find out how many extpacks are installed
            num_extpacks_tokens = line.split(":")
            if len(num_extpacks_tokens) != 2:
                raise InvalidExtPackInput(
                    "First line of stdout did not contain expected string format indicating number of extpacks installed; "
                    f"first_line={line}"
                )
            try:
                num_extpacks = int(num_extpacks_tokens[1].strip())
            except:
                raise InvalidExtPackInput(
                    "First line of stdout did not contain valid token to convert to int to determine the number of extpacks installed; "
                    f"first_line={line}"
                )
        if found_ext_packs_line == False:
            raise InvalidExtPackInput(
                f"Unable to determine the number of existing extension packs; lines={lines}"
            )

        def get_line_value(line) -> str:
            tokens = line.split()
            return tokens[1]

        if num_extpacks > 0:
            for line in lines:
                if "Version" in line:
                    retval["version"] = get_line_value(line)
                elif "Revision" in line:
                    retval["revision"] = get_line_value(line)
                elif "Usable" in line:
                    retval["usable"] = Utils.str_to_bool(get_line_value(line))

        return retval

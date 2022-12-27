import hashlib
import yaml
import logging
import os
import requests
import tempfile
from enum import Enum, auto
from invoke import Result, run, sudo, task
from invoke.exceptions import Exit
from workstationsetup.enums import Distro

logging.basicConfig(level=logging.INFO)


class HashAlgo(Enum):
    MD5SUM = auto()
    SHA256SUM = auto()
    SHA512SUM = auto()


# def add_repo(cfgs, ws_cfgs) -> None:
#     temp_dir = None
#     try:
#         temp_dir = tempfile.TemporaryDirectory()
#         if ws_cfgs.distro == Distro.DEBIAN_11:
#             from workstationsetup import debian_libs

#             debian_libs.add_repo(cfgs, ws_cfgs, temp_dir)
#         else:
#             unsupported_distro(ws_cfgs.distro)

#     finally:
#         temp_dir.cleanup()


def add_user_to_group(user, groups):
    if type(groups) != list:
        groups = [groups]
    for g in groups:
        r = run_sudo(f"usermod -aG {g} {user}")
        logging.info(
            f"User added to group, user={user}, group={g} cmdStdOut=[{r.stdout.strip()}], cmdStdErr=[{r.stderr.strip()}]]"
        )
        print(
            f"If this is the first time you have added user [{user}] to the group {g} ",
            "you will need to log out of your session and then log back in to use the ",
            "group restricted commands",
        )


def download_file(url, target_local_path, verify, chunk_size=8192):
    logging.info(f"Downloading file, url={url} target_local_path={target_local_path}")
    # The stream=True parameter enables us to download large files in chunks
    with requests.get(url, stream=True, verify=verify) as r:
        r.raise_for_status()
        with open(target_local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                f.write(chunk)


def install_local_package(packages_paths, distro) -> None:
    if type(packages_path) != list:
        packages_path = [packages_path]

    if distro == Distro.DEBIAN_11:
        from workstationsetup import debian_libs

        debian_libs.install_local_package(packages_paths)
    else:
        raise Exit("Unsupported distro; distro={distro}")


def file_checksum(file_path, check_sum, hash_algo, chunk_size=1024) -> bool:
    h = None
    match hash_algo:
        case HashAlgo.MD5SUM:
            h = hashlib.md5()
        case HashAlgo.SHA256SUM:
            h = hashlib.sha256()
        case HashAlgo.SHA512SUM:
            h = hashlib.sha512()

    # Open the file for reading in binary mode
    with open(file_path, "rb") as f:
        # Loop until we finish reading the entire file reading the file a chunk at a time
        chunk = 0
        while chunk != b"":
            chunk = f.read(chunk_size)
            h.update(chunk)
    # Generate a hexidecimal representation of the hash digest and compare it against
    # the check sum that was passed in.
    actual_check_sum = h.hexdigest()

    if check_sum != actual_check_sum:
        logging.error(
            f"Actual hash of file did not match expected hash, file_path={file_path}, check_sum={check_sum}, hash_algo={hash_algo}"
        )
        return False
    return True


def get_file_type(path) -> str:
    r = run_cmd(f"file {path}")
    if not r.failed:
        return r.stdout.strip()


def get_java_home() -> str:
    r = run_cmd("readlink -f $(which java) | sed 's|/bin/java||'")
    return r.stdout.strip()


def is_string_empty(s) -> bool:
    if not (s and s.strip()):
        return True
    return False


def load_yaml_file(path) -> dict:
    retval = None
    with open(path, "r") as f:
        retval = yaml.safe_load(f)
    return retval


def run_cmd(
    cmd, hide_stdout=True, hide_stderr=True, exit_on_failure=True, warn=False
) -> Result:
    return _run_cmd(cmd, False, hide_stdout, hide_stderr, exit_on_failure, warn)


def run_sudo(
    cmd, hide_stdout=True, hide_stderr=True, exit_on_failure=True, warn=False
) -> Result:
    return _run_cmd(cmd, True, hide_stdout, hide_stderr, exit_on_failure, warn)


def _run_cmd(cmd, run_sudo, hide_stdout, hide_stderr, exit_on_failure, warn) -> Result:
    hide = False
    if hide_stdout and hide_stderr:
        hide = "both"
    else:
        if hide_stdout:
            hide = "stdout"
        if hide_stdout:
            hide = "stdout"

    r = None
    if run_sudo:
        r = sudo(cmd, hide=hide, warn=warn)
    else:
        r = run(cmd, hide=hide, warn=warn)
    if exit_on_failure and r.failed:
        logging.error(
            f"Command failed, cmd={cmd}, stdout={r.stdout}, stderr={r.stderr}"
        )
        raise Exit()
    return r


def unsupported_distro(distro) -> None:
    raise Exit(f"Unsuppported distro; distro={distro}")

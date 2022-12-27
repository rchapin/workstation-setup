import os
from workstationsetup import utils


def add_repo(cfgs, ws_cfgs, temp_dir) -> None:
    downloaded_gpg_file_path = os.path.join(temp_dir.name, cfgs["key_file_name"])
    target_gpg_file_path = os.path.join("/etc/apt/trusted.gpg.d", cfgs["key_file_name"])
    utils.download_file(ws_cfgs, cfgs["key_url"], downloaded_gpg_file_path)
    utils.run_sudo(f"rm -f {target_gpg_file_path}")
    utils.run_sudo(
        f"gpg --dearmor -o {target_gpg_file_path} {downloaded_gpg_file_path}"
    )

    # Add the repo source.list.d file.
    temp_file_path = os.path.join(temp_dir.name, cfgs["sources_list_name"])
    target_file_path = os.path.join(
        "/etc/apt/sources.list.d", cfgs["sources_list_name"]
    )
    with open(temp_file_path, "wt") as f:
        f.write(cfgs["sources_list_contents"])
    utils.run_sudo(f"mv -f {temp_file_path} {target_file_path}")
    utils.run_sudo(f"chown root: {target_file_path}")
    utils.run_sudo("apt-get update")


def debsig_verify(temp_dir, deb_file_path, cfgs, ws_cfgs) -> bool:
    # Download Slack's public key:
    public_key_local_path = os.path.join(temp_dir.name, cfgs["public_key_filename"])
    utils.download_file(ws_cfgs, cfgs["public_key_url"], public_key_local_path)

    # Create directories to store debsigs policies and keyrings for the public key
    utils.run_sudo(f"rm -rf {cfgs['debsig_keyring_dir']}")
    utils.run_sudo(f"mkdir -p {cfgs['debsig_keyring_dir']}")
    utils.run_sudo(f"rm -rf {cfgs['debsig_policy_dir']}")
    utils.run_sudo(f"mkdir -p {cfgs['debsig_policy_dir']}")

    # Initialize an empty keyring (the signing key is a GPGv1 key, so you must follow this step to
    # ensure it's imported correctly):
    keyring_path = os.path.join(cfgs["debsig_keyring_dir"], "debsig.gpg")
    utils.run_sudo(f"touch {keyring_path}")

    # Import the public key into the corresponding debsigs keyring:
    utils.run_sudo(
        f"gpg --no-default-keyring --keyring {keyring_path} --import {public_key_local_path}"
    )

    # Write out the policy file to the temp dir, then move it to the correct location and update the
    # permissions
    policy_file_temp_path = os.path.join(temp_dir.name, cfgs["debsig_policy_filename"])
    policy_file_target_path = os.path.join(
        cfgs["debsig_policy_dir"], cfgs["debsig_policy_filename"]
    )
    with open(policy_file_temp_path, "w") as f:
        f.write(cfgs["debsig_policy_contents"])
    utils.run_sudo(f"mv {policy_file_temp_path} {policy_file_target_path}")
    utils.run_sudo(f"chown root: {policy_file_target_path}")

    # Finally, verify the package signature
    r = utils.run_sudo(f"debsig-verify {deb_file_path}")
    if r.return_code == 0:
        return True
    else:
        return False

def get_install_packages_cmd(packages_list) -> str:
    utils.run_sudo("apt-get update")
    cmd = f"apt-get update"
    return f"apt-get install -y {packages_list}"

def install_local_package(packages_paths) -> None:
    for package in packages_paths:
        utils.run_sudo(f"apt-get install {package}")

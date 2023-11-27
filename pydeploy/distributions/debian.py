import os
import requests
from io import BytesIO, StringIO
from tempfile import TemporaryDirectory
from string import Template
from fabric import Connection
from invoke.exceptions import Exit
from invoke import Context
from pydeploy.configs import Configs
from pydeploy.distributions.distribution import Distribution
from pydeploy.utils import Utils, HashAlgo


class Debian(Distribution):
    def __init__(self, configs: Configs) -> None:
        super().__init__(configs)

    def add_repo_impl(self, configs: Configs, conn: Connection, task_configs: dict) -> None:
        self.install_package(conn, ["gpg"])
        r = Utils.requests_retry(url=task_configs["key_url"], verify=configs.is_request_verify())
        gpg_file_contents = r.content

        remote_gpg_temp_file_path = os.path.join("/var/tmp/", task_configs["key_file_name"])
        remote_target_gpg_file_path = os.path.join(
            "/etc/apt/trusted.gpg.d", task_configs["key_file_name"]
        )
        conn.put(local=BytesIO(gpg_file_contents), remote=remote_gpg_temp_file_path)
        conn.run(f"rm -f {remote_target_gpg_file_path}")
        conn.run(f"gpg --dearmor -o {remote_target_gpg_file_path} {remote_gpg_temp_file_path}")
        conn.run(f"rm -f {remote_gpg_temp_file_path}")

        # Add the repo source.list.d file.
        remote_temp_file_path = os.path.join("/var/tmp/", task_configs["repo_file_name"])
        remote_target_file_path = os.path.join(
            "/etc/apt/sources.list.d", task_configs["repo_file_name"]
        )

        conn.put(local=StringIO(task_configs["repo_file_contents"]), remote=remote_temp_file_path)
        conn.run(f"mv -f {remote_temp_file_path} {remote_target_file_path}")
        conn.run(f"chown root: {remote_target_file_path}")
        conn.run("apt-get update")

    def get_architecture(self, conn: Connection) -> str:
        r = conn.run("dpkg --print-architecture")
        if r.failed:
            raise Exit("Unable go get architecture")
        return r.stdout.strip()

    def get_install_local_packages_cmd(self, packages: str) -> str:
        return self.get_install_packages_cmd(packages)

    def get_install_packages_cmd(self, packages: str) -> str:
        return f"apt-get install -y {packages}"

    def get_release(self, conn: Connection) -> None:
        r = conn.run("lsb_release -cs")
        if r.failed:
            raise Exit("Unable get release")
        return r.stdout.strip()

    def get_remove_packages_cmd(self, packages: str) -> str:
        return f"apt-get remove -y --purge {packages}"

    def get_update_packages_cmd(self) -> str:
        return "apt-get update"

    def install_cert(
        self,
        ctx: Context,
        conn: Connection,
        task_configs: dict,
        cert_path: str,
        cert_dir_name: str,
        cert_validation_string: str,
    ) -> bool:
        cert_file_name = os.path.basename(cert_path)
        conn.run(f"mv -f {cert_path} {task_configs['ca_cert_dir']}")
        conn.run("update-ca-certificates -f")
        return self.is_cert_in_cert_bundle(
            conn=conn,
            ca_certs_bundle_path=task_configs["ca_certs_bundle_path"],
            cert_validation_string=cert_validation_string,
        )

    def verify_package(
        self,
        ctx: Context,
        conn: Connection,
        temp_dir: TemporaryDirectory,
        package_file_path: str,
        public_key_file_path: str,
        verify_configs: dict,
    ) -> bool:
        """
        verify_package will, given that the package and public key are already on the
        remote host verify the package based on the public signature.
        """

        # There are (at least) two different methods for signing and verifying debian
        # packages that are completely different.  Check the verify_configs for the
        # specific implementation required
        retval = None
        mode = verify_configs["mode"]
        if mode == "debsigs":
            retval = self.verify_package_debsig(
                ctx=ctx,
                conn=conn,
                temp_dir=temp_dir,
                package_file_path=package_file_path,
                public_key_file_path=public_key_file_path,
                verify_configs=verify_configs,
            )
        elif mode == "dpkg-sig":
            retval = self.verify_package_dpkgsig(
                ctx=ctx,
                conn=conn,
                temp_dir=temp_dir,
                package_file_path=package_file_path,
                public_key_file_path=public_key_file_path,
                verify_configs=verify_configs,
            )
        elif mode == "dpkg-sig-legacy":
            retval = self.verify_package_dpkgsig_legacy(
                ctx=ctx,
                conn=conn,
                temp_dir=temp_dir,
                package_file_path=package_file_path,
                public_key_file_path=public_key_file_path,
                verify_configs=verify_configs,
            )
        else:
            raise Exception(f"Unknown verify_configs.mode; mode={mode}")

        return retval

    def verify_package_dpkgsig(
        self,
        ctx: Context,
        conn: Connection,
        temp_dir: TemporaryDirectory,
        package_file_path: str,
        public_key_file_path: str,
        verify_configs: dict,
    ) -> bool:
        # Ensure that required packages are installed on the target host
        # Do not use this function with Debian 12 distro; dpkg-sig has been removed
        packages = ["gpg", "dpkg-sig"]
        ctx.distro.install_package(conn=conn, packages=packages)
        r = conn.run(f"gpg --import {public_key_file_path}")
        if r.return_code != 0:
            raise Exception(
                f"importing gpg key; public_key_file_path={public_key_file_path}, r.stderr={r.stderr}"
            )
        r = conn.run(f"dpkg-sig --verify {package_file_path}")
        if r.return_code == 0:
            if "GOODSIG" in r.stdout:
                return True
            else:
                return False
        else:
            raise Exception(
                f"verifying package; package_file_path={package_file_path}, r.stderr={r.stderr}"
            )

    def verify_package_dpkgsig_legacy(
        self,
        ctx: Context,
        conn: Connection,
        temp_dir: TemporaryDirectory,
        package_file_path: str,
        public_key_file_path: str,
        verify_configs: dict,
    ) -> bool:
        """
        verify_package_dpkgsig_legacy will attempt to unpack the deb file and validate that a file
        signed file defined in the verify_configs has been signed by the provided GPG public key.
        """
        # Ensure that we have the required packages installed
        ctx.distro.install_package(conn=conn, packages=["gpg"])
        r = conn.run(f"gpg --import {public_key_file_path}")
        if r.return_code != 0:
            raise Exception(
                f"importing gpg key; public_key_file_path={public_key_file_path}, r.stderr={r.stderr}"
            )

        # Create a temp dir on the remote box and unpack the deb file into it
        file_name = os.path.basename(package_file_path)
        temp_dir_path = os.path.join("/var/tmp/", f"{file_name}_unpack")

        def cleanup_temp_dir():
            conn.run(f"rm -rf {temp_dir_path}")

        cleanup_temp_dir()
        conn.run(f"mkdir -p {temp_dir_path}")
        conn.run(f"cd {temp_dir_path} && ar -x {package_file_path}")

        # Verify the signature file
        sig_file_path = os.path.join(temp_dir_path, verify_configs["gpg_sig_file_name"])
        r = conn.run(f"gpg --verify {sig_file_path}")

        if r.return_code != 0:
            return False
        output = r.stdout
        output += r.stderr
        if "Good signature" not in output:
            return False

        # Now that we have validated the signature, validate the MD5sums of the files contained in
        # the deb file listed in the signature.
        r = conn.run(f"ls -1 {temp_dir_path}")
        unpacked_files = r.stdout.splitlines()
        assert len(unpacked_files) > 0
        for unpacked_file in unpacked_files:
            if unpacked_file == verify_configs["gpg_sig_file_name"]:
                # Skip the signature file
                continue
            r = conn.run(f'grep "{unpacked_file}" {sig_file_path}')
            tokens = r.stdout.split()
            shasum = tokens[1]
            file_path = os.path.join(temp_dir_path, unpacked_file)
            if not Utils.file_checksum_remote(
                conn=conn,
                file_path=file_path,
                checksum=shasum,
                hash_algo=HashAlgo[verify_configs["hash_algo"]],
            ):
                cleanup_temp_dir()
                return False

        cleanup_temp_dir()
        return True

    def verify_package_debsig(
        self,
        ctx: Context,
        conn: Connection,
        temp_dir: TemporaryDirectory,
        package_file_path: str,
        public_key_file_path: str,
        verify_configs: dict,
    ) -> bool:
        # Ensure that required packages are installed on the target host
        ctx.distro.install_package(conn=conn, packages=["debsig-verify"])

        # Create directories to store debsigs policies and keyrings for the public key
        conn.run(f"rm -rf {verify_configs['debsig_keyring_dir']}")
        conn.run(f"mkdir -p {verify_configs['debsig_keyring_dir']}")
        conn.run(f"rm -rf {verify_configs['debsig_policy_dir']}")
        conn.run(f"mkdir -p {verify_configs['debsig_policy_dir']}")

        # Initialize an empty keyring (the signing key is a GPGv1 key, so you must follow this step to
        # ensure it's imported correctly):
        keyring_path = os.path.join(verify_configs["debsig_keyring_dir"], "debsig.gpg")
        conn.run(f"touch {keyring_path}")

        # Import the public key into the corresponding debsigs keyring:
        conn.run(
            f"gpg --no-default-keyring --keyring {keyring_path} --import {public_key_file_path}"
        )

        # Write out the policy file to the temp dir, then move it to the correct location and update
        # the permissions
        policy_file_local_path = os.path.join(
            temp_dir.name, verify_configs["debsig_policy_filename"]
        )
        policy_file_remote_path = os.path.join(
            verify_configs["debsig_policy_dir"], verify_configs["debsig_policy_filename"]
        )
        with open(policy_file_local_path, "w") as f:
            f.write(verify_configs["debsig_policy_contents"])
        conn.put(policy_file_local_path, policy_file_remote_path)
        conn.run(f"chown root: {policy_file_remote_path}")

        # There are still some packages out there that are using SHA1 or other weak algorithms with
        # their signatures. If so configured, enable the use of weak digest algos.
        added_gpg_config = False
        pre_existing_gpg_config_dir = False
        if (
            "allow_weak_digest_algos" in verify_configs
            and verify_configs["allow_weak_digest_algos"] == True
        ):
            pre_existing_gpg_config_dir = self.add_gpg_config(
                conn, Distribution.GNUPG_CONF_ALLOW_WEAK_DIGEST_ALGO
            )
            added_gpg_config = True

        # Finally, verify the package signature
        r = conn.run(f"debsig-verify {package_file_path}", warn=True)

        # Remove the gpg config if we added it.
        if added_gpg_config == True:
            self.remove_gpg_config(
                conn,
                Distribution.GNUPG_CONF_ALLOW_WEAK_DIGEST_ALGO,
                (pre_existing_gpg_config_dir == False),
            )

        if r.return_code == 0:
            return True
        else:
            return False

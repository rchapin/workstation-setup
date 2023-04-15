import copy
import json
import logging
import os
import requests
import sys
from fabric import Connection
from invoke.exceptions import Exit
from invoke import Context, task
from tempfile import TemporaryDirectory
from pydeploy.tasks import Tasks
from pydeploy.utils import Utils, HashAlgo
from pydeploy.java import Java
from pydeploy.gcp import Gcp
from pydeploy.developer_tools import DeveloperTools
from pydeploy.slack import Slack
from pydeploy.zoom import Zoom

logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

ARG_HELP_USER_EMAIL = "REQUIRED - The current user's complete email address"
ARG_HELP_USER_FULL_NAME = (
    'REQUIRED - The current user\'s full name, wrapped in quotes, example: "John Doe"'
)
ARG_HELP_USER_ID = (
    "REQUIRED - The current user's uid string for the user account on the workstation"
)
ARG_HELP_CA_CERT_ALIAS = "The alias for the CA cert that is to be added to the trust store."
ARG_HELP_CA_CERT_ALIAS_REQUIRED = (
    "REQUIRED - The alias for the CA cert that is to be added to the trust store."
)
ARG_HELP_CA_CERT_PATH = "The fully qualified path to the CA cert .pem file"
ARG_HELP_CA_CERT_PATH_REQUIRED = f"REQUIRED - {ARG_HELP_CA_CERT_PATH}"
ARG_HELP_CA_CERT_DIR_NAME = (
    "The name of the dir into which the CA cert will be written before re-bundled"
)
ARG_HELP_CA_CERT_DIR_NAME_REQUIRED = (
    "REQUIRED - The name of the dir into which the CA cert will be written before re-bundled"
)
ARG_HELP_CA_CERT_VALIDATION_STRING = (
    "A string that is contained in the output from running the following command against "
    "the certificate that you are installing that will be used to verify that it has been "
    "added to the ca-cert bundle: "
    "awk -v cmd='openssl x509 -noout -subject' '/BEGIN/{close(cmd)};{print | cmd}' < /path/to/cert"
)
ARG_HELP_CA_CERT_VALIDATION_STRING_REQUIRED = f"REQUIRED - {ARG_HELP_CA_CERT_VALIDATION_STRING}"

ARG_HELP_INTELLIJ_TARBALL_PATH = (
    "OPTIONAL - The fully qualified path to the downloaded intellij tar.gz file.  "
    "Download the tarball and put it in a known location on your local disk"
)

ARG_HELP_INSTALL_VERSION = (
    "OPTIONAL - Override the version that is defined in the PyDeploy configs."
)

ARG_HELP_JVM_TRUST_STORE_PASSWORD_OPTIONAL = (
    "OPTIONAL - The password for the currently configured JVM's trust store. "
    "Only add this argument if you have changed the default after installing the jvm."
)

ARG_HELP_JDK_VERSION = (
    "REQUIRED - Version of the JDK to install; format <version-number>; example: 17"
)

DOCKER_DAEMON_JSON_BIP_DEFAULT = "10.27.0.1/24"
DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT = "10.27.0.1/25"
DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT = "10.28.0.0/16"
DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT = 24

ARG_HELP_DOCKER_BIP = (
    "OPTIONAL - The overriding cidr network for the docker bridge; "
    f"example: {DOCKER_DAEMON_JSON_BIP_DEFAULT}"
)
ARG_HELP_DOCKER_FIXED_CIDR = (
    "OPTIONAL - The overriding cidr network for the fixed-cidr config; "
    f"example: {DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT}"
)

ARG_HELP_DOCKER_ADDR_POOLS_BASE = (
    "OPTIONAL - The overriding cidr network for the docker default-address-pools.base config; "
    f"example: {DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT}"
)
ARG_HELP_DOCKER_ADDR_POOLS_SIZE = (
    "OPTIONAL - The overriding cidr network for the docker default-address-pools.size config; "
    f"example: {DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT}"
)
ARG_HELP_DOCKER_INSECURE_REGISTRIES = (
    "OPTIONAL - If your org hosts registries without TLS or self signed certs include a CSV of entries; "
    f"example: git.example.com:8443,git.scm.example.com:8443"
)

DOCKER_ARCH_MAP = {
    "amd64": "x86_64",
}

DOCKER_DAEMON_JSON_DEFAULT = {
    "bip": DOCKER_DAEMON_JSON_BIP_DEFAULT,
    "fixed-cidr": DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT,
    "default-address-pools": [
        {
            "base": DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT,
            "size": DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT,
        }
    ],
}

CONFIGURE_GIT_DEFAULT_EDITOR = "vim"


# A list of strings that we collect during the processing of any tasks that we then print to the
# user via the print_feedback task
# FIXME: this needs to be a dict so that we can idempotently overwrite the same key if we add the
# result more than once.
FEEDBACK = []


class WorkstationSetup(Tasks):
    @task
    def print_feedback(_):
        """
        A utility task to print all collected feedback during an invocation.  Running this task directly will have no result.
        """
        print("-- Tasks Complete!")
        for feedback in FEEDBACK:
            print()
            print(f"-- {feedback}")

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "user": "REQUIRED - The user-id for the user which the .gitconfigs are being set",
            "user_email": ARG_HELP_USER_EMAIL,
            "user_full_name": ARG_HELP_USER_FULL_NAME,
            "editor": f"OPTIONAL - The default editor for git to user for commit messages, default={CONFIGURE_GIT_DEFAULT_EDITOR}",
            "default_pull_reconcile_method": (
                "OPTIONAL - Sets the default reconciliation strategy when pulling for all branches, "
                "default=None, which will not set this git config value. "
                "'rebase_false' = git config pull.rebase false; (merge - the default strategy). "
                "'rebase_true' = git config pull.rebase true;  (rebase). "
                "'ff_only' = git config pull.ff only; (fast-forward only)."
            ),
        },
    )
    def configure_git(
        ctx,
        user,
        user_email,
        user_full_name,
        editor=CONFIGURE_GIT_DEFAULT_EDITOR,
        default_pull_reconcile_method=None,
    ):
        """
        Configures git for the given user with the provided user information.
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._configure_git(
                ctx,
                conn,
                user,
                user_email,
                user_full_name,
                editor,
                default_pull_reconcile_method,
            )

    def _configure_git(
        ctx: Context,
        conn: Connection,
        user: str,
        user_email: str,
        user_full_name: str,
        editor: str = CONFIGURE_GIT_DEFAULT_EDITOR,
        default_pull_reconcile_method=None,
    ) -> None:
        logger.info(
            f"Configuring git; user={user}, user_mail={user_email}, "
            f"user_full_name={user_full_name}, editor={editor}"
        )
        conn.sudo(command=f'git config --global user.name "{user_full_name}"', user=user)
        conn.sudo(command=f'git config --global user.email "{user_email}"', user=user)
        conn.sudo(command=f'git config --global core.editor "{editor}"', user=user)
        if default_pull_reconcile_method:
            cmd_prefix = "git config --global"
            cmd = None
            if default_pull_reconcile_method == "rebase_false":
                cmd = f"{cmd_prefix} pull.rebase false"
            if default_pull_reconcile_method == "rebase_true":
                cmd = f"{cmd_prefix} pull.rebase true"
            if default_pull_reconcile_method == "ff_only":
                cmd = f"{cmd_prefix} pull.ff only"
            conn.sudo(command=cmd, user=user)

            """
            rebase_false
            - git config pull.rebase false  # merge (the default strategy)\n"

                "rebase_true
                - git config pull.rebase true   # rebase\n"

                "ff_only
                - git config pull.ff only       # fast-forward only"
            """

    @staticmethod
    def get_docker_mapped_architecture(architecture) -> str:
        if architecture in DOCKER_ARCH_MAP:
            return DOCKER_ARCH_MAP[architecture]
        else:
            return architecture

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "cert_path": ARG_HELP_CA_CERT_PATH_REQUIRED,
            "cert_dir_name": ARG_HELP_CA_CERT_DIR_NAME_REQUIRED,
            "cert_validation_string": ARG_HELP_CA_CERT_VALIDATION_STRING_REQUIRED,
        },
    )
    def install_cert(ctx, cert_path, cert_dir_name, cert_validation_string):
        """
        Installs an additional ca cert, in PEM format, into the os ca certificates bundle.
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_cert(
                ctx, conn, cert_dir_name, cert_path, cert_validation_string
            )

    def _install_cert(
        ctx: Context,
        conn: Connection,
        cert_dir_name: str,
        cert_path: str,
        cert_validation_string: str,
    ):
        logger.info(f"Installing cert; cert_path={cert_path}")
        task_configs = ctx.distro.get_task_configs("install-cert")
        cert_file_name = os.path.basename(cert_path)
        remote_cert_path = os.path.join("/var/tmp", cert_file_name)
        conn.put(cert_path, remote_cert_path)
        success = ctx.distro.install_cert(
            ctx, conn, task_configs, remote_cert_path, cert_dir_name, cert_validation_string
        )
        if success == False:
            logger.error("Could not validate that cert was installed")
        else:
            logger.info(f"Cert successfully installed; cert_path={cert_path}")

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "cert_path": ARG_HELP_CA_CERT_PATH_REQUIRED,
            "cert_alias": ARG_HELP_CA_CERT_ALIAS_REQUIRED,
            "jvm_trust_store_password": ARG_HELP_JVM_TRUST_STORE_PASSWORD_OPTIONAL,
        },
    )
    def install_cert_into_jvm(ctx, cert_path, cert_alias, jvm_trust_store_password="changeit"):
        """
        Installs the provided CA cert, in pem format, into the jvm for which java-alternatives is currently configured.
        """
        temp_dir = TemporaryDirectory()
        der_file_name, der_file_path = Utils.convert_pem_cert_to_der(
            cert_path=cert_path, temp_dir=temp_dir
        )
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_cert_into_jvm(
                ctx=ctx,
                conn=conn,
                cert_file_name=der_file_name,
                local_cert_path=der_file_path,
                cert_alias=cert_alias,
                jvm_trust_store_password=jvm_trust_store_password,
            )
        temp_dir.cleanup()

    def _install_cert_into_jvm(
        ctx: Context,
        conn: Connection,
        cert_file_name: str,
        local_cert_path: str,
        cert_alias: str,
        jvm_trust_store_password: str = "changeit",
    ) -> None:
        Java.install_cert(
            ctx=ctx,
            conn=conn,
            cert_file_name=cert_file_name,
            local_cert_path=local_cert_path,
            cert_alias=cert_alias,
            jvm_trust_store_password=jvm_trust_store_password,
        )

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_chrome(ctx):
        """
        Installs the Google Chrome browser.
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_chrome(ctx, conn)

    def _install_chrome(ctx: Context, conn: Connection) -> None:
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-chrome")
        task_configs = ctx.distro.get_task_configs("install-chrome")
        packages = task_configs["package"]
        ctx.distro.install_package(conn=conn, packages=packages)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "docker_user": "OPTIONAL - The optional user name to add to the docker group",
            "docker_bip": ARG_HELP_DOCKER_BIP,
            "docker_fixed_cidr": ARG_HELP_DOCKER_FIXED_CIDR,
            "docker_default_addr_pools_base": ARG_HELP_DOCKER_ADDR_POOLS_BASE,
            "docker_default_addr_pools_size": ARG_HELP_DOCKER_ADDR_POOLS_SIZE,
            "docker_insecure_registries": ARG_HELP_DOCKER_INSECURE_REGISTRIES,
        },
    )
    def install_docker(
        ctx,
        docker_user=None,
        docker_bip=DOCKER_DAEMON_JSON_BIP_DEFAULT,
        docker_fixed_cidr=DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT,
        docker_default_addr_pools_base=DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT,
        docker_default_addr_pools_size=DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT,
        docker_insecure_registries=None,
    ):
        """
        Installs docker and docker-compose, and adds the provided user to the docker group.
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_docker(
                ctx,
                conn,
                docker_user,
                docker_bip,
                docker_fixed_cidr,
                docker_default_addr_pools_base,
                docker_default_addr_pools_size,
                docker_insecure_registries,
            )

    def _install_docker(
        ctx: Context,
        conn: Connection,
        docker_user: str,
        docker_bip: str,
        docker_fixed_cidr: str,
        docker_default_addr_pools_base: str,
        docker_default_addr_pools_size: int,
        docker_insecure_registries: str,
    ):
        logging.info(
            "Installing docker, docker-compose and adding user to docker group, "
            f"docker_user={docker_user}, docker_bip={docker_bip}, "
            f"docker_fixed_cidr={docker_fixed_cidr}, "
            f"docker_default_addr_pools_base={docker_default_addr_pools_base}, "
            f"docker_default_addr_pools_size={docker_default_addr_pools_size}"
        )

        # Add the docker repo and install the packages
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-docker")
        task_configs = ctx.distro.get_task_configs("install-docker")
        packages = task_configs["packages"]
        ctx.distro.install_package(conn=conn, packages=packages)

        temp_dir = TemporaryDirectory()

        # Install docker-compose
        # Hit the github repo and figure out the URL of the latest version, plus the sha256 sums.
        #
        # Read the GitHub web page that includes the details about the URLs for the files contained in
        # the latest release. We parse the JSON returned and look for the binary for the given os
        # and architecture along with the sha256 file.
        os_arch = ctx.distro.get_architecture(conn)

        # Docker might use a different string for the architecture that your OS returns, so we need
        # to resolve it in a map to get the correct value.
        docker_arch = WorkstationSetup.get_docker_mapped_architecture(os_arch)

        binary_file_name = f"docker-compose-linux-{docker_arch}"
        binary_local_file_path = None
        shasum_file_name = f"{binary_file_name}.sha256"
        shasum_local_file_path = None

        # FIXME: use get_github abstraction function for this
        r = requests.get(
            "https://api.github.com/repos/docker/compose/releases/latest",
            verify=ctx.distro.configs.is_request_verify(),
        )
        docker_release_data = r.json()
        for asset in docker_release_data["assets"]:
            if asset["name"] in [binary_file_name, shasum_file_name]:
                local_file_path = os.path.join(temp_dir.name, asset["name"])
                Utils.download_file(
                    configs=ctx.distro.configs,
                    url=asset["browser_download_url"],
                    target_local_path=local_file_path,
                )
                if asset["name"] == binary_file_name:
                    binary_local_file_path = local_file_path
                if asset["name"] == shasum_file_name:
                    shasum_local_file_path = local_file_path
                if binary_local_file_path is not None and shasum_local_file_path is not None:
                    break

        # Now we have both of the files downloaded and we have captured the paths to those files on
        # the local filesystem.  We need to read the checksum from the shasum file and validate that
        # the downloaded file's checksum matches.
        #
        # Read the contents of the shasum file
        shasum = None
        with open(shasum_local_file_path) as f:
            shasum = f.read().strip().split()[0]
        if not Utils.file_checksum(binary_local_file_path, shasum, HashAlgo.SHA256SUM):
            raise Exit(
                f"Unable to verify checksum of docker-compose binary;binary_local_file_path={binary_local_file_path}"
            )

        # If we have not raised an exception because of a checksum mismatch, we put the binary to
        # the remote host and then "install" the docker-compose binary and then cleanup our temp
        # files.
        binary_file_remote_file_path = os.path.join("/var/tmp/", binary_file_name)
        conn.put(binary_local_file_path, binary_file_remote_file_path)
        conn.run(f"chmod +x {binary_file_remote_file_path}")
        conn.run(f"mv -f {binary_file_remote_file_path} /usr/local/bin/")
        conn.run(f"rm -f /usr/local/bin/docker-compose")
        conn.run(f"ln -s /usr/local/bin/{binary_file_name} /usr/local/bin/docker-compose")

        # Customize and then write out the docker daemon.json file.  Put it on the remote host and
        # then restart docker.
        daemon_json = copy.deepcopy(DOCKER_DAEMON_JSON_DEFAULT)
        daemon_json["bip"] = docker_bip
        daemon_json["fixed-cidr"] = docker_fixed_cidr
        daemon_json["default-address-pools"][0]["base"] = docker_default_addr_pools_base
        daemon_json["default-address-pools"][0]["size"] = docker_default_addr_pools_size
        temp_daemon_json_path = os.path.join(temp_dir.name, "daemon.json")
        if docker_insecure_registries:
            # Split on the ',' and create a list
            docker_insecure_registries_entries = docker_insecure_registries.split(",")
            daemon_json["insecure-registries"] = docker_insecure_registries_entries
        with open(temp_daemon_json_path, "w") as f:
            json.dump(daemon_json, f)

        target_daemon_json_path = "/etc/docker/daemon.json"
        conn.put(temp_daemon_json_path, target_daemon_json_path)
        conn.run(f"chown root: {target_daemon_json_path}")
        conn.run("systemctl restart docker")

        temp_dir.cleanup()

        # Add the specified docker use to the docker group
        if docker_user:
            ctx.distro.add_user_to_group(conn=conn, user=docker_user, groups="docker")

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_drawio(ctx):
        """
        Installs the Drawio desktop application.
        """
        temp_dir = TemporaryDirectory()
        # The dependencies dict is designed to contain a key for each installation task.
        # The value for each is a dict that contains specific dependencies, or paths to
        # dependencies for that task.  In most cases is is paths to artifacts that reside
        # on the deployment server that are downloaded or created one time and then put
        # to each of the hosts on which the installation task is to be run.
        dependencies = {}
        dependencies["install-drawio"] = DeveloperTools.install_drawio_get_dependencies(
            ctx, temp_dir
        )
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_drawio(ctx, conn, dependencies)
        temp_dir.cleanup()

    def _install_drawio(ctx: Context, conn: Connection, dependencies: dict) -> None:
        DeveloperTools.install_drawio(ctx=ctx, conn=conn, dependencies=dependencies)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_google_cloud_cli(ctx):
        """
        Installs the google-cloud-cli program suite.
        """
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_google_cloud_cli(ctx, conn)

    def _install_google_cloud_cli(ctx: Context, conn: Connection) -> None:
        Gcp.install_google_cloud_cli(ctx=ctx, conn=conn)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"version": ARG_HELP_INSTALL_VERSION},
    )
    def install_gradle(ctx, version=None):
        """
        Install the gradle build tool.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-gradle"] = Java.install_gradle_get_dependencies(
            ctx, temp_dir, version
        )
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_gradle(ctx, conn, dependencies, version)
        temp_dir.cleanup()

    def _install_gradle(
        ctx: Context, conn: Connection, dependencies: dict, version: str = None
    ) -> None:
        Java.install_gradle(ctx=ctx, conn=conn, dependencies=dependencies, version=version)
        FEEDBACK.append(Java.GRADLE_FEEDBACK)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_helm(ctx):
        """
        Install the helm client.
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_helm(ctx, conn)

    def _install_helm(ctx: Context, conn: Connection) -> None:
        temp_dir = TemporaryDirectory()
        architecture = ctx.distro.get_architecture(conn)
        task_configs = ctx.distro.get_task_configs("install-helm")

        tarball_file_name = f"helm-v{task_configs['version']}-linux-{architecture}.tar.gz"
        tarball_url = f"{task_configs['base_url']}/{tarball_file_name}"
        tarball_local_file_path = os.path.join(temp_dir.name, tarball_file_name)
        Utils.download_file(
            configs=ctx.distro.configs, url=tarball_url, target_local_path=tarball_local_file_path
        )

        shasum_file_name = f"{tarball_file_name}.sha256sum"
        r = requests.get(
            f"{task_configs['base_url']}/{shasum_file_name}",
            verify=ctx.distro.configs.is_request_verify(),
        )
        shasum = r.text.split()[0]
        if not Utils.file_checksum(
            file_path=tarball_local_file_path, check_sum=shasum, hash_algo=HashAlgo.SHA256SUM
        ):
            raise Exit(
                f"Checksum for helm tarball did not match expected checksum; "
                f"file_path={tarball_local_file_path}, check_sum={shasum}, "
                f"hash_algo={HashAlgo.SHA256SUM}"
            )

        # Copy the tarball to the remote host and unpack and "install" it.
        tarball_remote_file_path = f"/var/tmp/{tarball_file_name}"
        conn.put(tarball_local_file_path, tarball_remote_file_path)

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

        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"version": ARG_HELP_INSTALL_VERSION},
    )
    def install_intellij(ctx, version=None):
        """
        Install the IntelliJ community addition IDE.
        """
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_intellij(ctx, conn, version)

    def _install_intellij(ctx: Context, conn: Connection, version: str = None) -> None:
        Java.install_intellij(ctx=ctx, conn=conn, version=version)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"version": ARG_HELP_JDK_VERSION},
    )
    def install_java_adoptium_eclipse_temurin(ctx, version):
        """
        Installs the Adoptium OpenJDK package.
        """
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_java_adoptium_eclipse_temurin(ctx, conn, version)

    def _install_java_adoptium_eclipse_temurin(
        ctx: Context, conn: Connection, version: int
    ) -> None:
        Java._install_java_adoptium_eclipse_temurin(ctx=ctx, conn=conn, version=version)
        FEEDBACK.append(Java.JAVA_FEEDBACK)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"version": ARG_HELP_JDK_VERSION},
    )
    def install_java_openjdk(ctx, version):
        """
        Installs Oracle’s free, GPL-licensed, production-ready OpenJDK package.
        """
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_java_openjdk(ctx, conn, version)

    def _install_java_openjdk(ctx: Context, conn: Connection, version: int) -> None:
        Java._install_java_openjdk(ctx=ctx, conn=conn, version=version)
        FEEDBACK.append(Java.JAVA_FEEDBACK)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"version": ARG_HELP_INSTALL_VERSION},
    )
    def install_maven(ctx, version=None):
        """
        Installs the Apache Maven build tool.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-maven"] = Java.install_maven_get_dependencies(ctx, temp_dir, version)
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_maven(ctx, conn, dependencies, version)
        temp_dir.cleanup()

    def _install_maven(
        ctx: Context, conn: Connection, dependencies: dict, version: str = None
    ) -> None:
        Java.install_maven(ctx=ctx, conn=conn, dependencies=dependencies, version=version)
        FEEDBACK.append(Java.MAVEN_FEEDBACK)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "minikube_user": "OPTIONAL - The optional user name to required groups for the non-root user to be able to run minikube."
        },
    )
    def install_minikube(ctx, minikube_user=None):
        """
        Installs Minikube; a lightweight Kubernetes implementation that creates a K8s cluster on a VM on your local machine.
        """
        # Get dependencies for each of the different architectures for the set of hosts onto which
        # we will install minikube.
        architectures = set()
        for _, conn in ctx.configs.connections.items():
            architectures.add(ctx.distro.get_architecture(conn))
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-minikube"] = DeveloperTools.install_minikube_get_dependencies(
            ctx=ctx, architectures=architectures, temp_dir=temp_dir
        )
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_minikube(
                ctx=ctx, conn=conn, dependencies=dependencies, minikube_user=minikube_user
            )
        temp_dir.cleanup()

    def _install_minikube(
        ctx: Context, conn: Connection, dependencies: dict, minikube_user: str
    ) -> None:
        DeveloperTools.install_minikube(ctx=ctx, conn=conn, dependencies=dependencies)
        # Should reboot after this install

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_packages(ctx):
        """
        Installs the base set of packages.
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_packages(ctx, conn)

    def _install_packages(ctx: Context, conn: Connection) -> None:
        logger.info("Installing base set of packages")
        cfgs = ctx.distro.get_task_configs("install-packages")
        packages = cfgs["packages"]
        ctx.distro.install_package(conn=conn, packages=packages)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_pgadmin(ctx):
        """
        Installs PostgreSQL pgAdmin
        """
        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_pgadmin(ctx, conn)

    def _install_pgadmin(ctx: Context, conn: Connection) -> None:
        logger.info("Installing pgadmin")
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-pgadmin")
        task_cfgs = ctx.distro.get_task_configs("install-pgadmin")
        packages = task_cfgs["packages"]
        ctx.distro.install_package(conn=conn, packages=packages)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "redshift_user": "REQUIRED - The user for which redshift will be installed",
            "temp_day": "OPTIONAL - The day temperature which overrides the setting defined in the PyDeploy configs.",
            "temp_night": "OPTIONAL - The night temperature which overrides the setting defined in the PyDeploy configs.",
            "brightness_day": "OPTIONAL - The day brightness which overrides the setting defined in the PyDeploy configs.",
            "brightness_night": "OPTIONAL - The night brightness which overrides the setting defined in the PyDeploy configs.",
        },
    )
    def install_redshift(
        ctx,
        redshift_user,
        temp_day=None,
        temp_night=None,
        brightness_day=None,
        brightness_night=None,
    ):
        """
        Installs redshift, the configs, and the user-level systemd configurations
        """
        brightness_day = None if brightness_day is None else float(brightness_day)
        brightness_night = None if brightness_night is None else float(brightness_night)
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-redshift"] = DeveloperTools.install_redshift_get_dependencies(
            ctx=ctx,
            temp_dir=temp_dir,
            temp_day=temp_day,
            temp_night=temp_night,
            brightness_day=brightness_day,
            brightness_night=brightness_night,
        )

        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_redshift(
                ctx=ctx,
                conn=conn,
                redshift_user=redshift_user,
                dependencies=dependencies,
                temp_day=temp_day,
                temp_night=temp_night,
                brightness_day=brightness_day,
                brightness_night=brightness_night,
            )
        temp_dir.cleanup()

    def _install_redshift(
        ctx: Context,
        conn: Connection,
        redshift_user: str,
        dependencies: dict = None,
        temp_day: str = None,
        temp_night: str = None,
        brightness_day: float = None,
        brightness_night: float = None,
    ) -> None:
        DeveloperTools.install_redshift(
            ctx=ctx,
            conn=conn,
            redshift_user=redshift_user,
            dependencies=dependencies,
            temp_day=temp_day,
            temp_night=temp_night,
            brightness_day=brightness_day,
            brightness_night=brightness_night,
        )
        FEEDBACK.append(DeveloperTools.REDSHIFT_FEEDBACK)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_slack(ctx):
        """
        Installs the Slack client.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {
            "install-slack": Slack.get_dependencies(ctx, temp_dir)
        }

        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_slack(ctx, conn, temp_dir, dependencies)

        temp_dir.cleanup()

    def _install_slack(ctx: Context, conn: Connection, temp_dir: TemporaryDirectory, dependencies: dict) -> None:
        Slack.install(ctx, conn, temp_dir, dependencies)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_vscode(ctx):
        """
        Installs the Visual Studio Code IDE.
        """
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._install_vscode(ctx, conn)

    def _install_vscode(ctx: Context, conn: Connection) -> None:
        ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-vscode")
        task_configs = ctx.distro.get_task_configs("install-vscode")
        packages = task_configs["package"]
        ctx.distro.install_package(conn=conn, packages=packages)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"max_user_watches": "OPTIONAL - The number of inotify file watches, default=524288"},
    )
    def setup_inotify(ctx, max_user_watches=524288):
        """
        Increase the maximum user file watches for inotify.
        """
        for _, conn in ctx.configs.connections.items():
            WorkstationSetup._setup_inotify(ctx, conn, max_user_watches)

    def _setup_inotify(ctx, conn, max_user_watches):
        temp_dir = TemporaryDirectory()
        inotify_file_name = "inotify_max_watches.conf"
        inotify_local_file_path = os.path.join(temp_dir.name, inotify_file_name)
        inotify_remote_file_path = os.path.join("/etc/sysctl.d/", inotify_file_name)
        with open(inotify_local_file_path, "w") as f:
            f.write(f"fs.inotify.max_user_watches = {max_user_watches}")
        conn.put(inotify_local_file_path, inotify_remote_file_path)
        conn.run(f"chmod 644 {inotify_remote_file_path}")
        conn.run("sysctl -p --system")
        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_zoom(ctx):
        """
        Installs the Zoom client.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {
            "install-zoom": Zoom.get_dependencies(ctx, temp_dir)
        }

        for host, conn in ctx.configs.connections.items():
            WorkstationSetup._install_zoom(ctx, conn, temp_dir, dependencies)

        temp_dir.cleanup()

    def _install_zoom(
        ctx: Context, conn: Connection, temp_dir: TemporaryDirectory, dependencies: dict
    ) -> None:
        Zoom.install(ctx, conn, temp_dir, dependencies)

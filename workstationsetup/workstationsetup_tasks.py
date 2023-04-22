import logging
import os
import requests
import sys
from fabric import Connection
from invoke.exceptions import Exit
from invoke import Context, task
from tempfile import TemporaryDirectory
from pydeploy.certs import Certs
from pydeploy.docker import Docker
from pydeploy.developer_tools import DeveloperTools
from pydeploy.gcp import Gcp
from pydeploy.git import Git
from pydeploy.kubernetes import Kubernetes
from pydeploy.java import Java
from pydeploy.os import OS
from pydeploy.slack import Slack
from pydeploy.tasks import Tasks
from pydeploy.utils import Utils, HashAlgo
from pydeploy.virtualbox import VirtualBox
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

CONFIGURE_GIT_DEFAULT_EDITOR = "vim"
ARG_HELP_CONFIGURE_GIT_USER = (
    "REQUIRED - The user-id for the user which the .gitconfigs are being set"
)
ARG_HELP_CONFIGURE_GIT_EDITOR = f"OPTIONAL - The default editor for git to user for commit messages, default={CONFIGURE_GIT_DEFAULT_EDITOR}"
ARG_HELP_CONFIGURE_GIT_RECONCILE_METHOD = (
    "OPTIONAL - Sets the default reconciliation strategy when pulling for all branches, "
    "default=None, which will not set this git config value. "
    "'rebase_false' = git config pull.rebase false; (merge - the default strategy). "
    "'rebase_true' = git config pull.rebase true;  (rebase). "
    "'ff_only' = git config pull.ff only; (fast-forward only)."
)


# A list of strings that we collect during the processing of any tasks that we then print to the
# user via the print_feedback task
FEEDBACK = {}


class WorkstationSetup(Tasks):
    @task
    def print_feedback(_):
        """
        A utility task to print all collected feedback during an invocation.  Running this task directly will have no result.
        """
        print("-- Tasks Complete!")
        for k, v in FEEDBACK.items():
            print()
            print(f"-- {v}")

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "user": ARG_HELP_CONFIGURE_GIT_USER,
            "user_email": ARG_HELP_USER_EMAIL,
            "user_full_name": ARG_HELP_USER_FULL_NAME,
            "editor": ARG_HELP_CONFIGURE_GIT_EDITOR,
            "default_pull_reconcile_method": ARG_HELP_CONFIGURE_GIT_RECONCILE_METHOD,
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
            Git.configure_git(
                ctx,
                conn,
                user,
                user_email,
                user_full_name,
                editor,
                default_pull_reconcile_method,
            )

    @staticmethod
    def get_architectures(ctx: Context) -> set[str]:
        # Figure out the set of architectures for all of the hosts configured for this task.
        retval = set()
        for _, conn in ctx.configs.connections.items():
            retval.add(ctx.distro.get_architecture(conn))
        return retval

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
            success = Certs.install_cert(
                ctx, conn, cert_dir_name, cert_path, cert_validation_string
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
            Java.install_cert(
                conn=conn,
                cert_file_name=der_file_name,
                local_cert_path=der_file_path,
                cert_alias=cert_alias,
                jvm_trust_store_password=jvm_trust_store_password,
            )
        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_chrome(ctx):
        """
        Installs the Google Chrome browser.
        """
        for host, conn in ctx.configs.connections.items():
            ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-chrome")
            task_configs = ctx.distro.get_task_configs("install-chrome")
            packages = task_configs["package"]
            ctx.distro.install_package(conn=conn, packages=packages)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={
            "docker_user": "OPTIONAL - The optional user name to add to the docker group",
            "docker_bip": Docker.ARG_HELP_DOCKER_BIP,
            "docker_fixed_cidr": Docker.ARG_HELP_DOCKER_FIXED_CIDR,
            "docker_default_addr_pools_base": Docker.ARG_HELP_DOCKER_ADDR_POOLS_BASE,
            "docker_default_addr_pools_size": Docker.ARG_HELP_DOCKER_ADDR_POOLS_SIZE,
            "docker_insecure_registries": Docker.ARG_HELP_DOCKER_INSECURE_REGISTRIES,
        },
    )
    def install_docker(
        ctx,
        docker_user=None,
        docker_bip=Docker.DOCKER_DAEMON_JSON_BIP_DEFAULT,
        docker_fixed_cidr=Docker.DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT,
        docker_default_addr_pools_base=Docker.DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT,
        docker_default_addr_pools_size=Docker.DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT,
        docker_insecure_registries=None,
    ):
        """
        Installs docker and docker-compose, and adds the provided user to the docker group.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-docker"] = Docker.get_dependencies(
            ctx=ctx, temp_dir=temp_dir, architectures=WorkstationSetup.get_architectures(ctx)
        )

        for host, conn in ctx.configs.connections.items():
            Docker.install(
                ctx,
                conn,
                dependencies,
                docker_user,
                docker_bip,
                docker_fixed_cidr,
                docker_default_addr_pools_base,
                docker_default_addr_pools_size,
                docker_insecure_registries,
            )

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
            DeveloperTools.install_drawio(ctx=ctx, conn=conn, dependencies=dependencies)
        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_google_cloud_cli(ctx):
        """
        Installs the google-cloud-cli program suite.
        """
        for _, conn in ctx.configs.connections.items():
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
            Java.install_gradle(ctx=ctx, conn=conn, dependencies=dependencies, version=version)
        temp_dir.cleanup()
        FEEDBACK["install-gradle"] = Java.GRADLE_FEEDBACK

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_helm(ctx):
        """
        Install the helm client.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-helm"] = Kubernetes.get_helm_dependencies(
            ctx=ctx, temp_dir=temp_dir, architectures=WorkstationSetup.get_architectures(ctx)
        )

        for host, conn in ctx.configs.connections.items():
            Kubernetes.install_helm(ctx, conn, dependencies)
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
        temp_dir = TemporaryDirectory()
        dependencies = {}
        dependencies["install-intellij"] = Java.install_intellij_get_dependencies(
            ctx=ctx, temp_dir=temp_dir, architectures=WorkstationSetup.get_architectures(ctx)
        )
        for _, conn in ctx.configs.connections.items():
            Java.install_intellij(ctx=ctx, conn=conn, dependencies=dependencies)
        temp_dir.cleanup()

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
            Java._install_java_adoptium_eclipse_temurin(ctx=ctx, conn=conn, version=version)
        FEEDBACK["install-java-adoptium-eclipse-temurin"] = Java.JAVA_FEEDBACK

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
        help={"version": ARG_HELP_JDK_VERSION},
    )
    def install_java_openjdk(ctx, version):
        """
        Installs Oracle's free, GPL-licensed, production-ready OpenJDK package.
        """
        for _, conn in ctx.configs.connections.items():
            Java._install_java_openjdk(ctx=ctx, conn=conn, version=version)
        FEEDBACK["install-java-openjdk"] = Java.JAVA_FEEDBACK

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
            Java.install_maven(ctx=ctx, conn=conn, dependencies=dependencies, version=version)
        temp_dir.cleanup()
        FEEDBACK["install-maven"] = Java.MAVEN_FEEDBACK

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
            DeveloperTools.install_minikube(ctx=ctx, conn=conn, dependencies=dependencies)
        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_packages(ctx):
        """
        Installs the base set of packages.
        """
        for host, conn in ctx.configs.connections.items():
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
        temp_dir.cleanup()
        FEEDBACK["install-redshift"] = DeveloperTools.REDSHIFT_FEEDBACK

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_slack(ctx):
        """
        Installs the Slack client.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {"install-slack": Slack.get_dependencies(ctx, temp_dir)}
        for host, conn in ctx.configs.connections.items():
            Slack.install(ctx, conn, temp_dir, dependencies)
        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_virtualbox(ctx):
        """
        Installs Oracle VirtualBox
        """
        temp_dir = TemporaryDirectory()
        dependencies = {"install-virtualbox": VirtualBox.get_dependencies(ctx, temp_dir)}
        for host, conn in ctx.configs.connections.items():
            VirtualBox.install(ctx, conn, dependencies)
        temp_dir.cleanup()

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_vscode(ctx):
        """
        Installs the Visual Studio Code IDE.
        """
        for _, conn in ctx.configs.connections.items():
            ctx.distro.add_repo(configs=ctx.configs, conn=conn, task="install-vscode")
            task_configs = ctx.distro.get_task_configs("install-vscode")
            packages = task_configs["package"]
            ctx.distro.install_package(conn=conn, packages=packages)

    @task(
        pre=[Tasks.load_configs],
        post=[print_feedback],
    )
    def install_zoom(ctx):
        """
        Installs the Zoom client.
        """
        temp_dir = TemporaryDirectory()
        dependencies = {"install-zoom": Zoom.get_dependencies(ctx, temp_dir)}
        for host, conn in ctx.configs.connections.items():
            Zoom.install(ctx, conn, temp_dir, dependencies)
        temp_dir.cleanup()

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
            OS.setup_inotify(conn, max_user_watches)

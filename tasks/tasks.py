import copy
import json
import logging
import ntpath
import shutil
import os
import tempfile
import requests
from pathlib import Path
from string import Template
from struct import pack
from invoke import Context, Result, run, sudo, task
from invoke.exceptions import Exit
from OpenSSL import crypto
import workstationsetup.utils as utils
from workstationsetup.utils import HashAlgo
from workstationsetup.enums import Distro
from workstationsetup.wsconfig import WsConfig

# ##############################################################################
# Overall configurations, includes details for all configurable tasks
ws_cfgs = WsConfig()
distro = None
if ws_cfgs.distro == Distro.DEBIAN:
    from workstationsetup.distributions.debian import Debian

    distro = Debian(ws_cfgs)
else:
    utils.unsupported_distro(ws_cfgs.distro)

# Optionally disable requests lib warnings
if ws_cfgs.is_request_warnings_disabled():
    requests.packages.urllib3.disable_warnings()

# ##############################################################################

# # Prints out some overall usage messages to the user
# print("============================================================")
# print("If you are running behind a VPN you can export the following")
# print("to disable the requests lib warnings")
# print("============================================================")

logging.basicConfig(level=logging.INFO)

REQUIRED = "Required"
ARG_HELP_USER_EMAIL = "REQUIRED - The current user's complete email address"
ARG_HELP_USER_FULL_NAME = (
    'REQUIRED - The current user\'s full name, wrapped in quotes, example: "John Doe"'
)
ARG_HELP_USER_ID = (
    "REQUIRED - The current user's uid string for the user account on the workstation"
)
ARG_HELP_CA_CERT_PATH = "The fully qualified path to the CA cert .pem file"
ARG_HELP_CA_CERT_PATH_REQUIRED = f"{REQUIRED} - {ARG_HELP_CA_CERT_PATH}"
ARG_HELP_CA_CERT_DIR_NAME = (
    "The name of the dir into which the CA cert will be written before re-bundled"
)
ARG_HELP_CA_CERT_DIR_NAME_REQUIRED = f"{REQUIRED} - The name of the dir into which the CA cert will be written before re-bundled"
ARG_HELP_CA_CERT_VALIDATION_STRING = (
    "A string that is contained in the output from running the following command against "
    "the certificate that you are installing that will be used to verify that it has been "
    "added to the ca-cert bundle: "
    "awk -v cmd='openssl x509 -noout -subject' '/BEGIN/{close(cmd)};{print | cmd}' < /path/to/cert"
)
ARG_HELP_CA_CERT_VALIDATION_STRING_REQUIRED = (
    f"{REQUIRED} - {ARG_HELP_CA_CERT_VALIDATION_STRING}"
)

ARG_HELP_INTELLIJ_TARBALL_PATH = (
    "OPTIONAL - The fully qualified path to the downloaded intellij tar.gz file.  "
    "Download the tarball and put it in a known location on your local disk"
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

DOCKER_ARCH_MAP = {
    "amd64": "x86_64",
}

DOCKER_DAEMON_JSON_DEFAULT = {
    "insecure-registries": ["git.example.com:8443"],
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
JVM_CERT_ALIAS = "cert-alias"
JAVA_VERSION = "11.0.16+8-1~deb11u1"
JAVA_FEEDBACK = """Java has been installed.
Add the following to your .bashrc and then add '$JAVA_HOME/bin' to your path
  export JAVA_HOME=$(readlink -f $(which java) | sed 's|/bin/java||')"""
MAVEN_DOWNLOAD_URL_FMT = (
    "https://archive.apache.org/dist/maven/maven-3/$version/binaries"
)
MAVEN_DOWNLOAD_FILE_FMT = "apache-maven-$version-bin.tar.gz"
MAVEN_VERSION = "3.6.3"
MAVEN_FEEDBACK = """Apache Maven has been installed.
Add the following to your .bashrc and then add $MAVEN_HOME/bin' to your path
  export MAVEN_HOME=/usr/local/apache-maven"""

GRADLE_VERSION = "4.4.1-13"

HELM_VERSION = "3.10.1"
HELM_DOWNLOAD_BASE_URL = "https://get.helm.sh"

# A list of strings that we collect during the processing of any tasks that we then print to the user via
# the print_feedback task
FEEDBACK = []


@task
def print_feedback(_):
    """
    A utility task to print all collected feedback during a setup invocation.  Running this task
    directly will have no result.
    """
    print("-- Tasks Complete!")
    for feedback in FEEDBACK:
        print()
        print(f"-- {feedback}")



@task(
    post=[print_feedback],
    help={
        "user_email": ARG_HELP_USER_EMAIL,
        "user_full_name": ARG_HELP_USER_FULL_NAME,
        "editor": f"The default editor for git to user for commit messages, default={CONFIGURE_GIT_DEFAULT_EDITOR}",
    },
)
def configure_git(_, user_email, user_full_name, editor=CONFIGURE_GIT_DEFAULT_EDITOR):
    """
    Configures git with the provided user information.
    """
    _configure_git(user_email, user_full_name, editor)


def _configure_git(user_email, user_full_name, editor="vim"):
    logging.info(
        f"Configuring git for user_mail={user_email}, user_full_name={user_full_name}, editor={editor}"
    )
    utils.run_cmd(f'git config --global user.name "{user_full_name}"')
    utils.run_cmd(f'git config --global user.email "{user_email}"')
    utils.run_cmd('git config --global core.editor "vim"')


@task(
    post=[print_feedback],
    help={
        "cert_path": ARG_HELP_CA_CERT_PATH_REQUIRED,
        "cert_dir_name": ARG_HELP_CA_CERT_DIR_NAME_REQUIRED,
        "cert_validation_string": ARG_HELP_CA_CERT_VALIDATION_STRING_REQUIRED,
    },
)
def install_cert(_, cert_path, cert_dir_name, cert_validation_string):
    """
    Installs the cert provided in the os ca certificates.
    """
    _install_cert(cert_path, cert_dir_name, cert_validation_string)


def _install_cert(cert_path, cert_dir_name, cert_validation_string):
    logging.info(f"Installing cert; cert_path={cert_path}")

    cfgs = ws_cfgs.get_task_configs("install-cert")

    cert_name = os.path.basename(cert_path)
    cert_dir = os.path.join(cfgs["ca_cert_dir"], cert_dir_name)
    utils.run_sudo(f"mkdir -p {cert_dir}")
    target_crt_path = os.path.join(cert_dir, cert_name)
    utils.run_sudo(f"cp {cert_path} {target_crt_path}")
    utils.run_sudo("update-ca-certificates -f")

    # Validate that the cert has been loaded by searching for our cert in newly installed bundle
    cmd_tmpl = "awk -v cmd='openssl x509 -noout -subject' '/BEGIN/{close(cmd)};{print | cmd}' < ${ca_certs_bundle_path} | grep -i ${cert_validation_string}"
    validation_cmd = Template(cmd_tmpl).substitute(
        cert_validation_string=cert_validation_string,
        cert_bundle_path=cfgs["ca_certs_bundle_path"],
    )
    r = utils.run_cmd(validation_cmd)
    r_stdout = r.stdout.strip()
    r_stderr = r.stderr.strip()
    if cert_validation_string in r.stdout.lower():
        logging.info(f"CA cert was successfully installed, {r_stdout}")
    else:
        logging.error(
            f"Unable to find CA cert in new certificate bundle, cmd stdout=[{r_stdout}], stderr=[{r_stderr}]"
        )
        raise Exit("exiting....")


@task(post=[print_feedback])
def install_chrome(c):
    """
    Installs the Google Chrome browser
    """
    _install_chrome(c)


def _install_chrome(c) -> None:
    distro.add_repo(c=c, task="install-chrome")
    cfgs = distro.get_task_configs("install-chrome")
    packages = cfgs["package"]
    distro.install_package(c=c, packages=packages)


@task
def install_dbeaver(_):
    """
    Install the DBeaver database client.

    If you are running behind a VPN You will probably need to turn it off to install this.  There is
    something going on with the MITM cert that it causing apt to fail when validating the GPG key
    for dbeaver when on VPNs.
    """
    _install_dbeaver()


def _install_dbeaver():
    distro.add_repo(task="install-dbeaver")
    cfgs = distro.get_task_configs("install-dbeaver")
    packages = cfgs["package"]
    distro.install_package(packages)


@task(
    post=[print_feedback],
    help={
        "docker_user": "OPTIONAL - The optional user name to add to the docker group",
        "docker_bip": ARG_HELP_DOCKER_BIP,
        "docker_fixed_cidr": ARG_HELP_DOCKER_FIXED_CIDR,
        "docker_default_addr_pools_base": ARG_HELP_DOCKER_ADDR_POOLS_BASE,
        "docker_default_addr_pools_size": ARG_HELP_DOCKER_ADDR_POOLS_SIZE,
    },
)
def install_docker(
    _,
    docker_user=None,
    docker_bip=DOCKER_DAEMON_JSON_BIP_DEFAULT,
    docker_fixed_cidr=DOCKER_DAEMON_JSON_FIXED_CIDR_DEFAULT,
    docker_default_addr_pools_base=DOCKER_DAEMON_JSON_ADDR_POOLS_BASE_DEFAULT,
    docker_default_addr_pools_size=DOCKER_DAEMON_JSON_ADDR_POOLS_SIZE_DEFAULT,
):
    """
    Installs docker and docker-compose, and adds the provided user to the docker group.
    """
    _install_docker(
        docker_user,
        docker_bip,
        docker_fixed_cidr,
        docker_default_addr_pools_base,
        docker_default_addr_pools_size,
    )


def _install_docker(
    docker_user,
    docker_bip,
    docker_fixed_cidr,
    docker_default_addr_pools_base,
    docker_default_addr_pools_size,
):
    logging.info(
        "Installing docker, docker-compose and adding user to docker group, "
        f"docker_user={docker_user}, docker_bip={docker_bip}"
    )

    # Add the docker repo and install the packages
    distro.add_repo(task="install-docker")
    cfgs = distro.get_task_configs("install-docker")
    packages = cfgs["packages"]
    distro.install_package(packages)

    temp_dir = tempfile.TemporaryDirectory()

    # Install docker-compose
    # Hit the github repo and figure out the URL of the latest version, plus the sha256 sums.
    #
    # Read the GitHub web page that includes the details about the URLs for the files contained in
    # the latest release. We parse the JSON returned and look for the binary for the given os
    # and architecture along with the sha256 file.
    os_arch = distro.get_architecture()

    # Docker might use a different string for the architecture that your OS returns, so we need
    # to resolve it in a map to get the correct value.
    docker_arch = get_docker_mapped_architecture(os_arch)

    binary_file_name = f"docker-compose-{cfgs['os_name']}-{docker_arch}"
    binary_local_file_path = None
    shasum_file_name = f"{binary_file_name}.sha256"
    shasum_local_file_path = None

    r = requests.get(
        "https://api.github.com/repos/docker/compose/releases/latest",
        verify=ws_cfgs.is_request_verify(),
    )
    docker_release_data = r.json()
    for asset in docker_release_data["assets"]:
        if asset["name"] in [binary_file_name, shasum_file_name]:
            local_file_path = os.path.join(temp_dir.name, asset["name"])
            utils.download_file(
                asset["browser_download_url"],
                local_file_path,
                ws_cfgs.is_request_verify(),
            )
            if asset["name"] == binary_file_name:
                binary_local_file_path = local_file_path
            if asset["name"] == shasum_file_name:
                shasum_local_file_path = local_file_path

    # Now we have both of the files downloaded and we have captured the paths to those files on the
    # local filesystem.  We need to read the checksum from the shasum file and validate that the
    # downloaded files checksum matches.
    #
    # Read the contents of the shasum file
    shasum = None
    with open(shasum_local_file_path) as f:
        shasum = f.read().strip().split()[0]
    if not utils.file_checksum(binary_local_file_path, shasum, HashAlgo.SHA256SUM):
        raise Exit()

    # If we have not raised an exception because of a checksum mismatch, we "install" the docker-
    # compose binary and then cleanup our temp files.
    utils.run_sudo(f"chmod +x {binary_local_file_path}")
    utils.run_sudo(f"mv -f {binary_local_file_path} /usr/local/bin/")
    utils.run_sudo(f"rm -f /usr/local/bin/docker-compose")
    utils.run_sudo(
        f"ln -s /usr/local/bin/{binary_file_name} /usr/local/bin/docker-compose"
    )

    # Customize and then write out the docker daemon.json file and restart docker
    temp_daemon_json_path = os.path.join(temp_dir.name, "daemon.json")
    target_daemon_json_path = "/etc/docker/daemon.json"
    daemon_json = copy.deepcopy(DOCKER_DAEMON_JSON_DEFAULT)
    daemon_json["bip"] = docker_bip
    daemon_json["fixed-cidr"] = docker_fixed_cidr
    daemon_json["default-address-pools"][0]["base"] = docker_default_addr_pools_base
    daemon_json["default-address-pools"][0]["size"] = docker_default_addr_pools_size
    with open(temp_daemon_json_path, "w") as f:
        json.dump(daemon_json, f)
    utils.run_sudo(f"mv -f {temp_daemon_json_path} {target_daemon_json_path}")
    utils.run_sudo(f"chown root: {target_daemon_json_path}")
    utils.run_sudo("systemctl restart docker", hide_stdout=False)

    temp_dir.cleanup()

    # Add the specified docker use to the docker group
    if docker_user:
        utils.add_user_to_group(docker_user, "docker")


def get_docker_mapped_architecture(architecture) -> str:
    if architecture in DOCKER_ARCH_MAP:
        return DOCKER_ARCH_MAP[architecture]
    else:
        return architecture


@task(post=[print_feedback])
def install_gradle(_):
    """
    Installs the Gradle build tool.
    """
    _install_gradle()


def _install_gradle():
    logging.info("Installing Gradle")
    # FIXME
    # install_package(f"gradle={GRADLE_VERSION}")
    r = requests.get(
        "https://gradle.org/release-checksums/", verify=ws_cfgs.is_request_verify()
    )


@task
def install_helm(_):
    """
    Installs helm
    """
    _install_helm()


def _install_helm(operating_system="linux"):
    temp_dir = tempfile.TemporaryDirectory()

    r = utils.run_cmd("dpkg --print-architecture")
    architecture = r.stdout.strip()
    tarball_file_name = f"helm-v{HELM_VERSION}-{operating_system}-{architecture}.tar.gz"
    shashum_file_name = f"{tarball_file_name}.sha256sum"
    tarball_local_file_path = os.path.join(temp_dir.name, tarball_file_name)
    r = requests.get(
        f"{HELM_DOWNLOAD_BASE_URL}/{shashum_file_name}",
        verify=ws_cfgs.is_request_verify(),
    )
    shasum = r.text.split()[0]
    utils.download_file(
        ws_cfgs,
        f"{HELM_DOWNLOAD_BASE_URL}/{tarball_file_name}",
        tarball_local_file_path,
    )
    if not utils.file_checksum(tarball_local_file_path, shasum, HashAlgo.SHA256SUM):
        raise Exit()
    utils.run_sudo(f"tar -xzf {tarball_local_file_path} -C {temp_dir.name}")

    # The expectation is that the tarball is unpacked into a directory with the following name
    unpack_dir_name = f"{operating_system}-{architecture}"
    unpacked_binary_path = os.path.join(temp_dir.name, unpack_dir_name, "helm")
    target_binary_path = os.path.join("/usr/local/bin", "helm")
    utils.run_sudo(f"rm -f {target_binary_path}")
    utils.run_sudo(f"mv {unpacked_binary_path} {target_binary_path}")
    utils.run_sudo(f"chmod +x {target_binary_path}")

    # The contents of the tarball may not be owned by the non-root user and might throw
    # an exception when we go to clean up the temp dir, so we'll chown it to the current user
    current_user = os.getlogin()
    utils.run_sudo(f"chown -R {current_user}: {temp_dir.name}")
    temp_dir.cleanup()


@task(
    post=[print_feedback],
    help={"intellij_tarball_path": ARG_HELP_INTELLIJ_TARBALL_PATH},
)
def install_intellij(_, intellij_tarball_path):
    """
    Will unpack the provided tarbarll and "install" it in /usr/local creating a /usr/local/intellij symlink
    """
    _install_intellij(intellij_tarball_path)


def _install_intellij(tarball_path):
    if not tarball_path:
        # Nothing to do
        return
    tarball_path = tarball_path.strip()
    if utils.is_string_empty(tarball_path):

        logging.error("tarball_path was an empty string")
        raise Exit()

    # We unpack the tarball to a new temp directory.  We then look in that directory to figure out
    # the name of the containing directory for this version.  Then, move that dir to /usr/local and
    # create a symlink.
    temp_dir = tempfile.TemporaryDirectory()
    logging.info(f"Unpacking intellij tarball, tarball_path={tarball_path}")
    utils.run_sudo(f"tar -xzf {tarball_path} -C {temp_dir.name}")
    temp_dir_contents = os.listdir(temp_dir.name)
    assert (
        len(temp_dir_contents) == 1
    ), f"Temporary directory was empty.  Unable to unpack intellij tarbal into expected location."
    intellij_dir_name = temp_dir_contents[0]
    if utils.is_string_empty(intellij_dir_name):
        logging.error(
            f"Intellij directcory name was empty, intellij_dir_name=[{intellij_dir_name}]"
        )
        raise Exit()
    source_dir = os.path.join(temp_dir.name, intellij_dir_name)
    target_dir = os.path.join("/usr/local", intellij_dir_name)
    target_symlink = os.path.join("/usr/local", "intellij")
    utils.run_sudo(f"rm -rf {target_dir}")
    utils.run_sudo(f"rm -f {target_symlink}")
    utils.run_sudo(f"mv {source_dir} {target_dir}")
    utils.run_sudo(f"ln -s {target_dir} {target_symlink}")

    FEEDBACK.append(
        f"Intellij {intellij_dir_name} has been installed to {target_dir}. "
        f"A symlink, {target_symlink} has been created that points to {target_dir}"
    )
    temp_dir.cleanup()


@task(post=[print_feedback])
def install_java(_):
    """
    Installs the JDK, docs, and source.
    """
    _install_java()


def _install_java():
    logging.info("Installing Java")
    """
    FIXME: There are adoptium packages that we should probably install instead.  There is
    a blog entry on using a debian apt repo that is evidently hosted under an artifactory
    instance; https://blog.adoptium.net/2021/12/eclipse-temurin-linux-installers-available/
    However there are problems with the https cert and the gpg key provided.
    """
    packages = ["openjdk-11-doc", "openjdk-11-jdk", "openjdk-11-source"]
    packages = [f"{package}={JAVA_VERSION}" for package in packages]
    utils.install_package(
        ["openjdk-11-doc", "openjdk-11-jdk", "openjdk-11-source"], ws_cfgs.distro
    )
    FEEDBACK.append(JAVA_FEEDBACK)


@task(post=[print_feedback])
def install_cert_into_jvm(_, cert_path, jvm_trust_store_passwd="changeit"):
    """
    Installs the provided pem cert into the JVM trust store.
    """
    _install_cert_into_jvm(cert_path)


def _install_cert_into_jvm(cert_path, jvm_trust_store_passwd="changeit"):
    logging.info(f"Installing cert into Java JVM, cert_path={cert_path}")

    # Ensure that it is a pem file
    file_type = utils.get_file_type(cert_path)
    if "pem certificate" not in file_type.lower():
        logging.error(
            f"Provided cert is not a pem file, get_file_type result=[{file_type}]"
        )
        raise Exit()

    # Convert the file to der format and then import into the JVM certs store
    temp_dir = tempfile.TemporaryDirectory()
    # Figure out the name of the file minus the ".pem" suffix
    cert_file_name = ntpath.basename(cert_path)
    cert_file_name = cert_file_name.removesuffix(".pem")
    der_file_path = os.path.join(temp_dir.name, f"{cert_file_name}.der")
    with open(cert_path, "r") as f_in:
        cert_contents = f_in.read()
        cert_pem = crypto.load_certificate(crypto.FILETYPE_PEM, cert_contents)
        cert_der = crypto.dump_certificate(crypto.FILETYPE_ASN1, cert_pem)
        with open(der_file_path, "wb") as f_out:
            f_out.write(cert_der)

    java_home = utils.get_java_home()
    # cacerts_dir = os.path.join(java_home, "lib/security/cacerts")
    # Ensure the alias for this cert doesn't exist and then add it.
    r = utils.run_sudo(
        cmd=f"keytool -cacerts -delete -alias {JVM_CERT_ALIAS} -storepass {jvm_trust_store_passwd}",
        exit_on_failure=False,
        warn=True,
    )
    utils.run_sudo(
        f"keytool -cacerts -importcert -noprompt -alias {JVM_CERT_ALIAS} -storepass {jvm_trust_store_passwd} -file {der_file_path}"
    )
    run(
        f"keytool -cacerts -list -storepass {jvm_trust_store_passwd} | grep -i {JVM_CERT_ALIAS}"
    )
    if r.failed:
        logging.error(
            f"Unable to verify that cert has been added to keystore, cert={cert_path}"
        )
        raise Exit()
    temp_dir.cleanup()


@task(post=[print_feedback])
def install_maven(_):
    """
    Downloads and installs the specified version of apache-maven.
    """
    _install_maven()


def _install_maven():
    logging.info("Installing Apache Maven")
    temp_dir = tempfile.TemporaryDirectory()
    base_url = Template(MAVEN_DOWNLOAD_URL_FMT).substitute(version=MAVEN_VERSION)
    gz_file_name = Template(MAVEN_DOWNLOAD_FILE_FMT).substitute(version=MAVEN_VERSION)
    shasum_file_name = Template(MAVEN_DOWNLOAD_FILE_FMT).substitute(
        version=MAVEN_VERSION
    )
    gz_file_url = f"{base_url}/{gz_file_name}"
    shasum_file_url = f"{base_url}/{gz_file_name}.sha512"
    gz_downloaded_file_path = os.path.join(temp_dir.name, gz_file_name)
    shasum_downloaded_file_path = os.path.join(temp_dir.name, gz_file_name)
    utils.download_file(ws_cfgs, gz_file_url, gz_downloaded_file_path)
    r = requests.get(shasum_file_url, verify=ws_cfgs.is_request_verify())
    shasum = r.content.strip().decode("utf-8")
    if not utils.file_checksum(gz_downloaded_file_path, shasum, HashAlgo.SHA512SUM):
        raise Exit()

    # If we have not raised an exception because of a checksum mismatch, we "install" maven
    # and then cleanup our temp files.
    target_dir = os.path.join("/usr/local", f"apache-maven-{MAVEN_VERSION}")
    target_symlink = os.path.join("/usr/local", f"apache-maven")
    utils.run_sudo(f"rm -rf {target_dir}")
    utils.run_sudo(f"rm -f {target_symlink}")
    utils.run_sudo(f"tar -xzf {gz_downloaded_file_path} -C /usr/local")
    utils.run_sudo(f"ln -s {target_dir} {target_symlink}")
    temp_dir.cleanup()
    FEEDBACK.append(MAVEN_FEEDBACK)


@task(post=[print_feedback])
def install_minikube(_, minikube_user=None):
    """
    Installs minikube
    """
    _install_minikube(minikube_user)


def _install_minikube(minikube_user):
    utils.install_package(
        [
            "bridge-utils",
            "qemu-kvm",
            "kubernetes-client",
            "libvirt-daemon",
            "libvirt-daemon-system",
            "virtinst",
        ],
        ws_cfgs.distro,
    )

    temp_dir = tempfile.TemporaryDirectory()
    downloads = [
        dict(
            url="https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64",
            file_name="minikube",
        ),
        dict(
            url="https://storage.googleapis.com/minikube/releases/latest/docker-machine-driver-kvm2",
            file_name="docker-machine-driver-kvm2",
        ),
    ]
    for download in downloads:
        downloaded_file_path = os.path.join(temp_dir.name, download["file_name"])
        utils.download_file(ws_cfgs, download["url"], downloaded_file_path)
        target_path = os.path.join("/usr/local/bin", download["file_name"])
        utils.run_sudo(f"mv -f {downloaded_file_path} {target_path}")
        utils.run_sudo(f"chmod 755 {target_path}")
        utils.run_sudo(f"chown root: {target_path}")

    temp_dir.cleanup()

    # Add the specified minikube_user to the required groups
    if minikube_user:
        utils.add_user_to_group(minikube_user, ["libvirt", "libvirt-qemu"])


@task(post=[print_feedback])
def install_packages(c):
    """
    Installs the base set of packages.
    """
    _install_packages(c)


def _install_packages(c: Context) -> None:
    logging.info("Installing base set of packages")
    cfgs = ws_cfgs.get_task_configs("install-packages")
    packages = cfgs["packages"]
    distro.install_package(c=c, packages=packages)


@task(post=[print_feedback])
def install_redshift(_):
    """
    Installs and configures a user-level systemd service to run redshift
    """
    _install_redshift()


def _install_redshift():
    # FIXME: split up via distro config
    logging.info("Installing redshift and redshift service")

    cfgs = ws_cfgs["install-redshift"]
    _install_packages(cfgs["packages"])

    conf_file = "redshift.conf"
    unit_file = "redshift.service"
    # FIXME: make a constant or util retval
    user_config_dir = os.path.join(Path.home(), ".config")
    redshift_conf_source_path = os.path.join(
        os.getcwd(), WsConfig.CONFIGS_DIR, conf_file
    )
    redshift_conf_target_path = os.path.join(user_config_dir, conf_file)
    systemd_dir = os.path.join(user_config_dir, "systemd", "user")
    redshift_service_source_path = os.path.join(
        os.getcwd(), WsConfig.CONFIGS_DIR, unit_file
    )
    redshift_service_target_path = os.path.join(systemd_dir, unit_file)

    # Create the config systemd dir if it does not already exist and then copy the files into the
    # appropriate locations.
    Path(systemd_dir).mkdir(parents=True, exist_ok=True)
    shutil.copy(redshift_conf_source_path, redshift_conf_target_path)
    shutil.copy(redshift_service_source_path, redshift_service_target_path)

    utils.run_cmd("systemctl --user daemon-reload")
    utils.run_cmd("systemctl --user enable redshift")
    utils.run_cmd("systemctl --user restart redshift")


@task
def install_slack(_):
    """
    Installs the slack
    """
    _install_slack()


def _install_slack() -> None:
    cfgs = ws_cfgs.get_task_configs("install-slack")
    temp_dir = None
    try:
        temp_dir = tempfile.TemporaryDirectory()
        download_url = f"{cfgs['download_url_prefix']}/{cfgs['package']}"
        download_local_path = os.path.join(temp_dir.name, cfgs["package"])
        utils.download_file(ws_cfgs, download_url, download_local_path)

        if ws_cfgs.distro == Distro.DEBIAN_11:
            from workstationsetup import debian_libs

            debian_libs.debsig_verify(
                temp_dir, download_local_path, cfgs["verification"], ws_cfgs
            )
            debian_libs.install_local_package([download_local_path])
        else:
            utils.unsupported_distro(ws_cfgs.distro)
    finally:
        if temp_dir:
            temp_dir.cleanup()


def install_vscode(_) -> None:
    pass


# vscode
# $ wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
# $ sudo install -o root -g root -m 644 packages.microsoft.gpg /etc/apt/trusted.gpg.d/
# $ sudo sh -c 'echo "deb [arch=amd64 signed-by=/etc/apt/trusted.gpg.d/packages.microsoft.gpg] https://packages.microsoft.com/repos/vscode stable main" > /etc/apt/sources.list.d/vscode.list'


@task(
    post=[print_feedback],
    help={
        "user_email": ARG_HELP_USER_EMAIL,
        "user_full_name": ARG_HELP_USER_FULL_NAME,
        "user_id": ARG_HELP_USER_ID,
        "docker_bip": ARG_HELP_DOCKER_BIP,
        "ca_cert_path": ARG_HELP_CA_CERT_PATH,
    },
)
def setup(
    _,
    user_email,
    user_full_name,
    user_id,
    docker_bip=None,
    ca_cert_path=None,
):
    """
    The uber task that runs all of the sub-tasks in the following order:
    - install_cert (optional)
    - install_packages
    - install_docker
    - install_java
    - install_maven
    - install_gradle
    - configure_git
    - setup_inotify

    Run the following to see details about each task
        inv -h <task-name>
    """
    if ca_cert_path:
        _install_cert(cert_path=ca_cert_path)

    _install_packages()
    _install_docker(docker_user=user_id, docker_bip=docker_bip)
    _install_java()
    _install_maven()
    _install_gradle()
    _configure_git(user_email=user_email, user_full_name=user_full_name)
    _setup_inotify


@task
def setup_inotify(_):
    """
    Increase the max user file watches for inotify
    """
    _setup_inotify()


def _setup_inotify():
    temp_dir = tempfile.TemporaryDirectory()
    inotify_file_name = "inotify_max_watches.conf"
    inotify_temp_file_path = os.path.join(temp_dir.name, inotify_file_name)
    inotify_file_path = os.path.join("/etc/sysctl.d/", inotify_file_name)
    with open(inotify_temp_file_path, "w") as f:
        f.write("fs.inotify.max_user_watches = 524288")
    utils.run_sudo(f"mv -f {inotify_temp_file_path} {inotify_file_path}")
    utils.run_sudo("sysctl -p --system")
    temp_dir.cleanup()

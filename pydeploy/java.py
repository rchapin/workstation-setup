import os
import requests
from string import Template
from invoke import Context, Exit
from fabric import Connection
from tempfile import TemporaryDirectory
from pydeploy.utils import Utils, HashAlgo
from pydeploy.enums import ArchiveType


class Java(object):

    GRADLE_DEPENDENCY_COMPRESSED_FILE_PATH = "gradle_compressed_file_path"
    GRADLE_DEPENDENCY_COMPRESSED_FILE_NAME = "gradle_compressed_file_name"
    GRADLE_FEEDBACK = """Gradle has been installed.`
Add the following to your .bashrc and then add $GRADLE_HOME/bin' to your path
  export GRADLE_HOME=/usr/local/gradle"""

    INTELLIJ_ARCH_MAP = {
        # Intellij does not include the architecture string in the version for x86_64 architecture
        "amd64": "",
        "arm64": "aarch64",
    }

    JAVA_FEEDBACK = """Java has been installed.
Add the following to your .bashrc and then add '$JAVA_HOME/bin' to your path
  export JAVA_HOME=$(readlink -f $(which java) | sed 's|/bin/java||')"""

    MAVEN_DOWNLOAD_URL_FMT = "https://archive.apache.org/dist/maven/maven-3/$version/binaries"
    MAVEN_DOWNLOAD_FILE_FMT = "apache-maven-$version-bin.tar.gz"
    MAVEN_FEEDBACK = """Apache Maven has been installed.`
Add the following to your .bashrc and then add $MAVEN_HOME/bin' to your path
  export MAVEN_HOME=/usr/local/apache-maven"""

    MAVEN_DEPENDENCY_TARBALL_PATH = "maven_tarball_path"

    @staticmethod
    def get_java_home(ctx: Context = None, conn: Connection = None) -> str:
        Utils._is_ctx_or_conn(ctx, conn)
        c = ctx if ctx else conn
        cmd = "readlink -f $(which java) | sed 's|/bin/java||'"
        r = c.run(cmd)
        if not r.failed:
            return r.stdout.strip()
        else:
            raise Exception(f"Unable to get java home, cmd={cmd}, stderr={r.stderr}")

    @staticmethod
    def install_cert(
        conn: Connection,
        cert_file_name: str,
        local_cert_path: str,
        cert_alias: str,
        jvm_trust_store_password: str = "changeit",
    ) -> None:
        """
        Installs the der formatted cert from the provided cert_path into the currently configured JVM.
        You MUST pass a connection that is configured for the root user.
        """
        remote_cert_path = os.path.join("/var/tmp/", cert_file_name)
        conn.put(local_cert_path, remote_cert_path)

        # Ensure the alias for this cert does not already exist and then add it.
        r = conn.run(
            command=f"keytool -cacerts -delete -alias {cert_alias} -storepass {jvm_trust_store_password}",
            warn=True,
        )
        conn.run(
            f"keytool -cacerts -importcert -noprompt -alias {cert_alias} -storepass {jvm_trust_store_password} -file {remote_cert_path}"
        )
        r = conn.run(
            f"keytool -cacerts -list -storepass {jvm_trust_store_password} | grep -i {cert_alias}"
        )
        if r.failed:
            raise Exit(
                f"Unable to verify that cert has been added to keystore, "
                f"cert_file_name={cert_file_name}, remote_cert_path={remote_cert_path}, "
                f"r.stderr={r.stderr}"
            )

    @staticmethod
    def install_gradle(
        ctx: Context, conn: Connection, dependencies: dict = None, version: str = None
    ) -> None:
        if dependencies is None:
            dependencies = Java.install_gradle_get_dependencies(ctx=ctx, version=version)

        target_parent_dir = "/usr/local"
        target_dir = os.path.join(target_parent_dir, f"gradle-{version}")
        target_symlink = os.path.join(target_parent_dir, f"gradle")
        local_compressed_file_path = dependencies["install-gradle"][
            Java.GRADLE_DEPENDENCY_COMPRESSED_FILE_PATH
        ]
        remote_compressed_file_path = os.path.join(
            "/var/tmp", dependencies["install-gradle"][Java.GRADLE_DEPENDENCY_COMPRESSED_FILE_NAME]
        )
        conn.put(local_compressed_file_path, remote_compressed_file_path)
        Utils.unpack_file(
            conn=conn,
            archive_file_path=remote_compressed_file_path,
            archive_file_type=ArchiveType.ZIP,
            target_dir=target_dir,
            target_parent_dir=target_parent_dir,
            symlink_path=target_symlink,
        )

    @staticmethod
    def install_gradle_get_dependencies(
        ctx: Context, temp_dir: TemporaryDirectory, version: str = None
    ) -> dict:
        retval = {}

        task_configs = ctx.distro.get_task_configs("install-gradle")
        configs = ctx.distro.configs
        if version is None:
            version = str(task_configs["version"])

        # Get the the gradle versions JSON document and get the details for the version that we want
        # to install.
        r = requests.get(
            task_configs["versions_url"], verify=ctx.distro.configs.is_request_verify()
        )
        versions_json = r.json()
        version_json = None
        for version_entry in versions_json:
            if version_entry["version"] == version:
                version_json = version_entry
                break
        if version_json is None:
            raise Exception(
                "Unable to find version data in output from the versions url for gradle; "
                f"version={version}, version_json={version_json}"
            )

        zipfile_file_name = version_json["downloadUrl"].split("/")[-1]
        zipfile_local_file_path = os.path.join(temp_dir.name, zipfile_file_name)
        Utils.download_file(
            configs=configs,
            url=version_json["downloadUrl"],
            target_local_path=zipfile_local_file_path,
        )
        r = requests.get(url=version_entry["checksumUrl"], verify=configs.is_request_verify())
        shasum = r.text.strip()
        if not Utils.file_checksum(
            file_path=zipfile_local_file_path, checksum=shasum, hash_algo=HashAlgo.SHA256SUM
        ):
            retval["errors"] = [
                f"Downloaded file checksum does not match; zipfile_local_file_path={zipfile_local_file_path}, shasum={shasum}"
            ]
            return retval
        retval[Java.GRADLE_DEPENDENCY_COMPRESSED_FILE_PATH] = zipfile_local_file_path
        retval[Java.GRADLE_DEPENDENCY_COMPRESSED_FILE_NAME] = zipfile_file_name
        return retval

    @staticmethod
    def install_intellij_get_dependencies(
        ctx: Context, temp_dir: TemporaryDirectory, architectures: set, version: str = None
    ) -> dict:
        task_configs = ctx.distro.get_task_configs("install-intellij")
        version = version if version is not None else task_configs["version"]

        retval_architectures = {}
        for architecture in architectures:
            # IntelliJ does not have a consistent way of naming their packages/urls.  They only add the
            # architecture if it is aarch64, AFAIK.  So, we lookup the architecture that IntelliJ uses
            # and then based on the result generate a string that we will use for the
            # version_architecture key in the url string substitution.
            if architecture not in Java.INTELLIJ_ARCH_MAP:
                raise Exception(
                    f"Architecture key not found in Java.INTELLIJ_ARCH_MAP; architecture={architecture}"
                )
            intellij_arch = Java.INTELLIJ_ARCH_MAP[architecture]
            version_and_architecture = None
            if Utils.is_string_empty(intellij_arch):
                # We need to create a string for the substitution that ONLY includes the version.
                version_and_architecture = version
            else:
                # We need to create a string for the substitution that includes both the version and the
                # architecture.
                version_and_architecture = f"{version}-{intellij_arch}"

            gz_download_url = Template(task_configs["url_template"]).substitute(
                version_and_architecture=version_and_architecture
            )
            gz_download_file_name = gz_download_url.split("/")[-1]
            local_gz_download_file_path = os.path.join(temp_dir.name, gz_download_file_name)
            Utils.download_file(
                configs=ctx.distro.configs,
                url=gz_download_url,
                target_local_path=local_gz_download_file_path,
            )
            shasum_url = f"{gz_download_url}.sha256"
            r = requests.get(shasum_url, verify=ctx.distro.configs.is_request_verify())
            shasum = r.text.split()[0]
            if not Utils.file_checksum(
                file_path=local_gz_download_file_path,
                checksum=shasum,
                hash_algo=HashAlgo.SHA256SUM,
            ):
                raise Exception(
                    "Downloaded file checksum does not match; "
                    f"gz_download_path={local_gz_download_file_path}, shasum={shasum}"
                )

            arch_artifacts = {
                "filename": gz_download_file_name,
                "local_file_path": local_gz_download_file_path,
            }
            retval_architectures[architecture] = arch_artifacts

        return {"architectures": retval_architectures}

    @staticmethod
    def install_intellij(ctx: Context, conn: Connection, dependencies: dict) -> None:
        intellij_dependencies = dependencies["install-intellij"]
        architecture = ctx.distro.get_architecture(conn)
        architecture_dependencies = intellij_dependencies["architectures"][architecture]
        target_parent_dir = "/usr/local"
        target_symlink = os.path.join(target_parent_dir, "intellij")
        remote_gz_file_path = os.path.join("/var/tmp/", architecture_dependencies["filename"])
        conn.put(architecture_dependencies["local_file_path"], remote_gz_file_path)
        Utils.unpack_file(
            conn=conn,
            archive_file_path=remote_gz_file_path,
            archive_file_type=ArchiveType.TAR_GZ,
            target_parent_dir=target_parent_dir,
            symlink_path=target_symlink,
        )

    @staticmethod
    def _install_java_adoptium_eclipse_temurin(
        ctx: Context, conn: Connection, version: int
    ) -> None:
        ctx.distro.add_repo(
            configs=ctx.configs, conn=conn, task="install-java-adoptium-eclipse-temurin"
        )
        task_configs = ctx.distro.get_task_configs("install-java-adoptium-eclipse-temurin")
        packages = task_configs["packages"]
        hydrated_packages = Utils.hydrate(templates=packages, values={"version": version})
        ctx.distro.install_package(conn=conn, packages=hydrated_packages)

    @staticmethod
    def _install_java_openjdk(ctx: Context, conn: Connection, version: int) -> None:
        task_configs = ctx.distro.get_task_configs("install-java-openjdk")
        packages = task_configs["packages"]
        hydrated_packages = Utils.hydrate(templates=packages, values={"version": version})
        ctx.distro.install_package(conn=conn, packages=hydrated_packages)

    @staticmethod
    def install_maven(
        ctx: Context, conn: Connection, dependencies: dict = None, version: str = None
    ) -> None:
        if dependencies is None:
            dependencies = Java.install_maven_get_dependencies(ctx=ctx, version=version)
        task_configs = ctx.distro.get_task_configs("install-maven")
        if version is None:
            version = task_configs["version"]

        target_parent_dir = "/usr/local"
        target_dir = os.path.join("/usr/local", f"apache-maven-{version}")
        target_symlink = os.path.join("/usr/local", f"apache-maven")
        local_compressed_file_path = dependencies["install-maven"][
            Java.MAVEN_DEPENDENCY_TARBALL_PATH
        ]
        remote_compressed_file_path = "/var/tmp/maven.tar.gz"
        conn.put(local_compressed_file_path, remote_compressed_file_path)
        Utils.unpack_file(
            conn=conn,
            archive_file_path=remote_compressed_file_path,
            archive_file_type=ArchiveType.TAR_GZ,
            target_dir=target_dir,
            target_parent_dir=target_parent_dir,
            symlink_path=target_symlink,
        )

    @staticmethod
    def install_maven_get_dependencies(
        ctx: Context, temp_dir: TemporaryDirectory = None, version: str = None
    ) -> dict:
        retval = {}
        managed_temp_dir = False
        if temp_dir is None:
            managed_temp_dir = True
            temp_dir = TemporaryDirectory()

        task_configs = ctx.distro.get_task_configs("install-maven")
        configs = ctx.distro.configs
        if version is None:
            version = task_configs["version"]
        base_url = Template(Java.MAVEN_DOWNLOAD_URL_FMT).substitute(version=version)
        gz_file_name = Template(Java.MAVEN_DOWNLOAD_FILE_FMT).substitute(version=version)

        gz_file_url = f"{base_url}/{gz_file_name}"
        shasum_file_url = f"{base_url}/{gz_file_name}.sha512"
        gz_downloaded_file_path = os.path.join(temp_dir.name, gz_file_name)
        Utils.download_file(
            configs=configs,
            url=gz_file_url,
            target_local_path=gz_downloaded_file_path,
        )
        r = requests.get(shasum_file_url, verify=ctx.distro.configs.is_request_verify())
        shasum = r.content.strip().decode("utf-8")
        if not Utils.file_checksum(
            file_path=gz_downloaded_file_path, checksum=shasum, hash_algo=HashAlgo.SHA512SUM
        ):
            retval["errors"] = [
                f"Downloaded file checksum does not match; gz_download_path={gz_downloaded_file_path}, shasum={shasum}"
            ]
        retval[Java.MAVEN_DEPENDENCY_TARBALL_PATH] = gz_downloaded_file_path

        if managed_temp_dir:
            temp_dir.cleanup()

        return retval

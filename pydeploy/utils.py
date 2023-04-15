import hashlib
import logging
import os
import re
import requests
import sys
import yaml
from enum import Enum, auto
from invoke import Context
from fabric import Connection
from OpenSSL import crypto
from string import Template
from tempfile import TemporaryDirectory
from typing import Tuple
from pydeploy.enums import ArchiveType

logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class HashAlgo(Enum):
    MD5SUM = auto()
    SHA256SUM = auto()
    SHA512SUM = auto()


class Utils(object):
    @staticmethod
    def convert_pem_cert_to_der(cert_path: str, temp_dir: TemporaryDirectory) -> Tuple[str, str]:
        # Figure out the name of the file minus the ".pem" suffix
        cert_file_name = os.path.basename(cert_path)
        cert_file_name = cert_file_name.removesuffix(".pem")
        der_file_name = f"{cert_file_name}.der"
        der_file_path = os.path.join(temp_dir.name, der_file_name)
        with open(cert_path, "r") as f_in:
            cert_contents = f_in.read()
            cert_pem = crypto.load_certificate(crypto.FILETYPE_PEM, cert_contents)
            cert_der = crypto.dump_certificate(crypto.FILETYPE_ASN1, cert_pem)
            with open(der_file_path, "wb") as f_out:
                f_out.write(cert_der)
        return der_file_name, der_file_path

    @staticmethod
    def download_file(configs, url: str, target_local_path: str, chunk_size=8192):
        # We cannot include the type-hint for the configs parameter because it would otherwise cause
        # a circular import.
        logging.info(f"Downloading file, url={url} target_local_path={target_local_path}")

        # The stream=True parameter enables us to download large files in chunks
        verify = configs.is_request_verify()
        with requests.get(url, stream=True, verify=verify) as r:
            r.raise_for_status()
            with open(target_local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)

    @staticmethod
    def file_checksum(
        file_path: str, check_sum: str, hash_algo: HashAlgo, chunk_size: int = 1024
    ) -> bool:
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

    @staticmethod
    def get_file_type(path: str, ctx: Context = None, conn: Connection = None) -> str:
        Utils._is_ctx_or_conn(ctx, conn)
        c = ctx if ctx else conn
        cmd = f"file {path}"
        r = c.run(cmd)
        if not r.failed:
            return r.stdout.strip()
        else:
            raise Exception(f"Unable to get file type, cmd={cmd}, stderr={r.stderr}")

    @staticmethod
    def get_github_release_info(
        url: str, artifact_regex: str, hashes_regex: str, verify: bool = True
    ) -> Tuple[str, str]:
        def get_url(pattern: str, asset_json: dict) -> str:
            name = asset_json["name"]
            result = re.match(pattern, name)
            if result:
                return asset_json["browser_download_url"]
            else:
                return None

        r = requests.get(url=url, verify=verify)
        if not r.ok:
            raise Exception(f"Unable to get github release info json; url={url}, r={r}")

        release_json = r.json()
        artifact_url = None
        hashes_url = None
        for asset in release_json["assets"]:
            if artifact_url is None:
                artifact_url = get_url(artifact_regex, asset)
            if hashes_url is None:
                hashes_url = get_url(hashes_regex, asset)
            if artifact_url is not None and hashes_url is not None:
                break

        return artifact_url, hashes_url

    @staticmethod
    def get_lines_from_file(path: str, pattern: str) -> list[str]:
        retval = []

        with open(path, "r") as f:
            while True:
                line = f.readline().strip()
                if not line:
                    break
                result = re.match(pattern, line)
                if result:
                    retval.append(line)

        return retval

    @staticmethod
    def hydrate(templates: list[str], values: dict) -> list[str]:
        retval = []
        for template in templates:
            hydrated_str = Template(template).substitute(values)
            retval.append(hydrated_str)
        return retval

    @staticmethod
    def _is_ctx_or_conn(ctx: Context, conn: Connection) -> None:
        if ctx is None and conn is None:
            raise Exception("You must pass wither a Context or a Connection object")

    @staticmethod
    def is_string_empty(s) -> bool:
        if not (s and s.strip()):
            return True
        return False

    @staticmethod
    def load_yaml_file(path) -> dict:
        retval = None
        with open(path, "r") as f:
            retval = yaml.safe_load(f)
        return retval

    @staticmethod
    def str_to_bool(input: str) -> bool:
        input = input.upper()
        return True if input == "TRUE" else False

    @staticmethod
    def unpack_file(
        conn: Connection,
        archive_file_path: str,
        archive_file_type: ArchiveType,
        target_parent_dir: str,
        symlink_path: str = None,
        target_dir: str = None,
    ) -> None:
        archive_list_exception_msg = (
            "The first line of the archive list output did not contain a directory name. "
            "You will need to call this function with the 'target_dir' path that will be "
            "the path of the unpacked archive data."
        )

        def get_archive_file_list(file_path: str, cmd: str) -> str:
            r = conn.run(cmd)
            if r.failed:
                raise Exception(
                    "Unable to get file list from archive; cmd={cmd}, stderr={r.stderr}"
                )
            return r.stdout

        # We do not know what the name of the directory inside the compressed file will be, so we
        # will need to peek inside so that we will know what the name of the directory will be when
        # we unpack it.
        unpacked_dir_name = None

        tar_gzip_flag = ""
        if archive_file_type == ArchiveType.TAR_GZ:
            tar_gzip_flag = "z"
        if archive_file_type == ArchiveType.TAR or archive_file_type == ArchiveType.TAR_GZ:
            if not target_dir:
                list_cmd = f"tar -t{tar_gzip_flag}f {archive_file_path} | head -n 1"
                # The list output should contain a string, which is the name of the directory, followed
                # by a '/' and '\n' char.
                list_output = get_archive_file_list(archive_file_path, list_cmd)
                if not list_output.endswith("/\n"):
                    raise Exception(f"{archive_list_exception_msg}; list_output={list_output}")
                unpacked_dir_name = list_output.split("/")[0]

            unpack_cmd = f"tar -x{tar_gzip_flag}f {archive_file_path} -C {target_parent_dir}"

        if archive_file_type == ArchiveType.ZIP:
            unpack_cmd = f"unzip {archive_file_path} -d {target_parent_dir}"

        # Only generate a target_dir if we have not been provided with one.
        target_dir = (
            target_dir if target_dir else os.path.join(target_parent_dir, unpacked_dir_name)
        )
        conn.run(f"rm -rf {target_dir}")
        logger.info(f"Unpacking compressed file; unpack_cmd={unpack_cmd}")
        conn.run(unpack_cmd)

        if symlink_path is not None:
            conn.run(f"rm -f {symlink_path}")
            conn.run(f"ln -s {target_dir} {symlink_path}")

        conn.run(f"rm -f {archive_file_path}")

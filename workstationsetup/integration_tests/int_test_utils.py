import datetime
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
import yaml
from git import Repo
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydeploy.enums import ConfigUpdateMode, Distro, WindowManager

logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


class IntegrationTestUtils(object):
    @staticmethod
    def create_base_configs(distro: Distro, version: str, window_manager: WindowManager) -> dict:
        return dict(
            distro=dict(
                name=distro.name.lower(),
                version=version,
                window_manager=window_manager.name.lower(),
            )
        )

    @staticmethod
    def create_test_ca_cert_pem(
        temp_dir: TemporaryDirectory,
        key_name: str,
        cert_name: str,
        common_name: str,
        org_name: str,
        org_unit_name: str,
    ) -> Tuple[str, str]:

        now = datetime.datetime.utcnow()
        one_day = datetime.timedelta(1, 0, 0)
        ten_days = datetime.timedelta(10, 0, 0)
        date_not_valid_before = now - one_day
        date_not_valid_after = now + ten_days

        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        public_key = private_key.public_key()
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, org_name),
                    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, org_unit_name),
                ]
            )
        )
        builder = builder.issuer_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, common_name),
                ]
            )
        )
        builder = builder.not_valid_before(date_not_valid_before)
        builder = builder.not_valid_after(date_not_valid_after)
        builder = builder.serial_number(int(uuid.uuid4()))
        builder = builder.public_key(public_key)
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        certificate = builder.sign(
            private_key=private_key, algorithm=hashes.SHA256(), backend=default_backend()
        )

        key_file_path = os.path.join(temp_dir.name, key_name)
        with open(key_file_path, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.BestAvailableEncryption(
                        b"openstack-ansible"
                    ),
                )
            )

        cert_file_path = os.path.join(temp_dir.name, cert_name)
        with open(cert_file_path, "wb") as f:
            f.write(
                certificate.public_bytes(
                    encoding=serialization.Encoding.PEM,
                )
            )
        return (key_file_path, cert_file_path)

    @staticmethod
    def get_env_vars(prefix: str = None) -> dict:
        """
        Returns env vars in a dict, optionally filtering on a prefix if provided
        """
        retval = {}
        for k, v in os.environ.items():
            if prefix:
                startswith = k.startswith(prefix)
                if startswith == False:
                    continue
            retval[k] = v

        return retval

    @staticmethod
    def get_project_root() -> Path:
        return Path(Repo(".", search_parent_directories=True).working_tree_dir)

    @staticmethod
    def is_cert_in_bundle(cert_path: str, search_string: str) -> bool:
        """
        This function will take a provided ca cert bundle and will 'search' through all of the bundled search for
        the provided search string.  If the string is found, it will return True, else False.
        """
        retval = False
        temp_dir = TemporaryDirectory()
        try:
            # Decode the cert into ASCII and write it to a file.
            cmd = ["openssl", "crl2pkcs7", "-nocrl", "-certfile", cert_path]
            return_code, stdout, stderr = IntegrationTestUtils.run_subprocess(cmd)
            if return_code != 0:
                logger.error(
                    f"Unable to execute command to validate cert; "
                    f"cmd={cmd}, return_code={return_code}, stdout={stdout}, stderr={stderr}"
                )
            actual_certs_ascii_file_path = os.path.join(
                temp_dir.name, "actual_certs_ascii_file.txt"
            )
            with open(actual_certs_ascii_file_path, "w") as f:
                actual_certs_ascii_lines = stdout.split("\n")
                for actual_certs_ascii_line in actual_certs_ascii_lines:
                    f.write(f"{actual_certs_ascii_line}\n")

            # Parse the ascii of the certs and write the output to a text file.
            cmd = [
                "openssl",
                "pkcs7",
                "-in",
                actual_certs_ascii_file_path,
                "-print_certs",
                "-text",
                "-noout",
            ]
            return_code, stdout, stderr = IntegrationTestUtils.run_subprocess(cmd)
            if return_code != 0:
                logger.error(
                    f"Unable to execute command to validate cert; "
                    f"cmd={cmd}, return_code={return_code}, stdout={stdout}, stderr={stderr}"
                )
            actual_certs_parsed_file_path = os.path.join(temp_dir.name, "actual_certs_parsed.txt")
            with open(actual_certs_parsed_file_path, "w") as f:
                f.write(stdout)

            # Read the parsed certs file, line-by-line and search for the provided string.
            with open(actual_certs_parsed_file_path, "r") as f:
                while True:
                    line = f.readline()
                    if not line:
                        break
                    if search_string in line:
                        retval = True
                        break

        except Exception as e:
            logger.error(e)
            raise e
        finally:
            temp_dir.cleanup()

        return retval

    @staticmethod
    def load_yaml_file(path) -> dict:
        retval = None
        with open(path, "r") as f:
            retval = yaml.safe_load(f)
        return retval

    @staticmethod
    def read_file_to_list(path: str) -> list[str]:
        retval = []
        

        return retval


    @staticmethod
    def run_subprocess(command: list[str]) -> Tuple[int, str, str]:
        r = subprocess.run(
            command, universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return (r.returncode, r.stdout, r.stderr)

    @staticmethod
    def wait_for_port_to_be_available(
        host: str, port: int, sleep_time: int = 1, timeout: int = 60
    ) -> None:

        timeout_exception = Exception(
            f"Timed-out waiting to be able to connect; timeout={timeout}, host={host}, port={port}"
        )
        def is_timeout_reached(start_time: float, timeout: int) -> bool:
            time_diff = time.time() - start_time
            if time_diff >= timeout:
                return True
            return False

        start_time = time.time()
        while True:
            test_socket = None
            try:
                if is_timeout_reached(start_time, timeout):
                    raise timeout_exception
                test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_socket.settimeout(timeout)
                test_socket.connect((host, port))
                logger.info(f"Able to connect; host={host}, port={port}")
                break
            except Exception as e:
                logger.info(f"Unable to connect; host={host}, port={port}")
                if is_timeout_reached(start_time, timeout):
                    raise timeout_exception
                logger.info(f"Waiting to retry to connect: sleep_time={sleep_time}")
                time.sleep(sleep_time)
            finally:
                if test_socket:
                    test_socket.close()

    @staticmethod
    def write_yaml_file(output_path, data):
        with open(output_path, "w") as fh:
            yaml.dump(data, fh)

from __future__ import annotations
from abc import ABC, abstractmethod
import logging
from typing import Tuple
import unittest
import json
import os
import socket
import sys
from pathlib import Path
from fabric import Connection, Result
from invoke import Collection
from invoke.program import Program
from tempfile import TemporaryDirectory
from vagrant import Vagrant
from pydeploy.program import PyDeployProgram
from pydeploy.tasks import Tasks
from pydeploy.utils import Utils
from workstationsetup.workstationsetup_tasks import WorkstationSetup
from workstationsetup.integration_tests.int_test_utils import IntegrationTestUtils

os.environ["PYTHONUNBUFFERED"] = "1"

logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

VAGRANT_SSH_WAIT_TIME = 1
ENV_VAR_PREFIX = "WS_SETUP_INTTEST_"

ENV_VAR_KEY_CONFIG_DIR = f"{ENV_VAR_PREFIX}CONFIG_DIR"
ENV_VAR_KEY_PARENT_DIR = f"{ENV_VAR_PREFIX}PARENT_DIR"
ENV_VAR_KEY_PYDEPLOY_CONFIGS_REPO_DIR = f"{ENV_VAR_PREFIX}PYDEPLOY_CONFIGS_REPO_DIR"
ENV_VAR_KEY_SSH_IDENTITY_FILE = f"{ENV_VAR_PREFIX}SSH_IDENTITY_FILE"
ENV_VAR_KEY_SSH_IDENTITY_FILE_PUB = f"{ENV_VAR_PREFIX}SSH_IDENTITY_FILE_PUB"
ENV_VAR_KEY_TEST_HOST = f"{ENV_VAR_PREFIX}TEST_HOST"
ENV_VAR_KEY_TEST_USER = f"{ENV_VAR_PREFIX}TEST_USER"
ENV_VAR_KEY_VAGRANT_BOX_INSTANCE_PREFIX = f"{ENV_VAR_PREFIX}VAGRANT_BOX_INSTANCE_"
ENV_VAR_KEY_VAGRANT_BOX_REUSE = f"{ENV_VAR_PREFIX}VAGRANT_BOX_REUSE"
ENV_VAR_KEY_VAGRANT_BOX_START_PORT = f"{ENV_VAR_PREFIX}VAGRANT_BOX_START_PORT"
ENV_VAR_KEY_VAGRANT_DIR = f"{ENV_VAR_PREFIX}VAGRANT_DIR"
ENV_VAR_KEY_VIRTENV_DIR = f"{ENV_VAR_PREFIX}VIRTENV_DIR"

ENV_VARS_REQUIRED = [
    ENV_VAR_KEY_CONFIG_DIR,
    ENV_VAR_KEY_PARENT_DIR,
    ENV_VAR_KEY_PYDEPLOY_CONFIGS_REPO_DIR,
    ENV_VAR_KEY_SSH_IDENTITY_FILE,
    ENV_VAR_KEY_SSH_IDENTITY_FILE_PUB,
    ENV_VAR_KEY_TEST_HOST,
    ENV_VAR_KEY_TEST_USER,
    ENV_VAR_KEY_VAGRANT_BOX_REUSE,
    ENV_VAR_KEY_VAGRANT_BOX_START_PORT,
    ENV_VAR_KEY_VAGRANT_DIR,
    ENV_VAR_KEY_VIRTENV_DIR,
]


class ITBase(unittest.TestCase, ABC):
    TEST_CERT_KEY_NAME = "inttest.key"
    TEST_CERT_NAME = "inttest.crt"
    TEST_CERT_COMMON_NAME = "inttest-ca"
    TEST_CERT_ORG_NAME = "inttest-org"
    TEST_CERT_ORG_UNIT_NAME = "inttest-org-unit"
    TEST_CERT_ALIAS = "inttest-cert-alias"

    TEST_ENV_VARS = None
    TEST_HOST = None
    TEST_USER = None
    CONFIG_DIR = None
    PYDEPLOY_REPO_DIR = None
    VAGRANT_BOX_FAB_CONNECTION = None
    DISTRO_NAME = None
    VAGRANT_DIR = None
    VAGRANT_BOX_CONFIGS = None
    VAGRANT_BOX_NAME = None
    VAGRANT_BOX_DIR = None
    VAGRANT_SSH_PORT = None
    VAGRANT_SSH_IDENTITY_FILE = None
    VAGRANT_BOX = None
    VAGRANT_BOX_REUSE = False

    def __init__(self, methodName: str = ...) -> None:
        super().__init__(methodName)
        self.test_task_configs = None
        self.test_task_configs_path = None
        self.test_program = None

    @abstractmethod
    def get_installed_packages(self) -> set[str]:
        pass

    def clean_config_dir(self) -> None:
        logger.info("Cleaning config dir; self.CONFIG_DIR={self.CONFIG_DIR}")
        files = Path(self.CONFIG_DIR).glob("**/*")
        for file in files:
            logger.info(f"Deleting config file; file={file}")
            file.unlink()

    def _check_fab_result(
        self,
        result: Result,
        print_stdout: bool = False,
        print_stderr: bool = False,
        fail_on_failure: bool = True,
        validation_string: str = None,
        check_stderr: bool = False,
    ) -> None:
        def print_lines(output: str) -> None:
            if not output:
                return
            lines = output.split("\n")
            for line in lines:
                logger.info(line)

        logger.info(f"result; command={result.command}")
        if print_stdout == True:
            print_lines(result.stdout)
        if print_stderr == True:
            print_lines(result.stderr)

        if fail_on_failure == True:
            if result.failed == True:
                print_lines(result.stderr)
                self.fail("Execution of command failed; command={result.command}")

        if validation_string is not None:
            output_lines = result.stderr.split("\n") if check_stderr else result.stdout.split("\n")
            found_expected_line = False
            for line in output_lines:
                if validation_string in line:
                    found_expected_line = True
                    break
            self.assertTrue(
                found_expected_line,
                f"Did not find expected output from command; validation_string:{validation_string}",
            )

    @staticmethod
    def create_test_ca_cert(temp_dir) -> str:
        _, cert_file_path = IntegrationTestUtils.create_test_ca_cert_pem(
            temp_dir=temp_dir,
            key_name=ITBase.TEST_CERT_KEY_NAME,
            cert_name=ITBase.TEST_CERT_NAME,
            common_name=ITBase.TEST_CERT_COMMON_NAME,
            org_name=ITBase.TEST_CERT_ORG_NAME,
            org_unit_name=ITBase.TEST_CERT_ORG_UNIT_NAME,
        )
        return cert_file_path

    @staticmethod
    def create_vagrant_box(path: str) -> Vagrant:
        return Vagrant(root=path)

    def _exec_bootstrap_test(self, expected_packages: set[str]) -> None:
        r = self.run_bootstrap_file()
        self._check_fab_result(r)
        self._validate_bootstrap_test_user_setup()
        self._validate_bootstrap_test_user_added_to_sudoers()
        self._validate_bootstrap_ssh_configs()
        self._validate_installed_packages(expected_packages)

    @staticmethod
    def get_bootstrap_file_path(distro: str) -> str:
        repo_project_root_path = IntegrationTestUtils.get_project_root()
        bootstrap_file_name = f"bootstrap-{distro}.sh"
        bootstrap_file_path = os.path.join(
            repo_project_root_path.__str__(), "bootstrap", bootstrap_file_name
        )
        return (bootstrap_file_name, bootstrap_file_path)

    @staticmethod
    def get_container() -> Vagrant:
        return ITBase.VAGRANT_BOX

    @staticmethod
    def get_test_env_vars() -> dict:
        retval = IntegrationTestUtils.get_env_vars(ENV_VAR_PREFIX)

        # Ensure that all of the required env vars are present
        for required_var in ENV_VARS_REQUIRED:
            if required_var not in retval:
                raise Exception(f"Missing required env var: env_var_variable_name={required_var}")

        return retval

    def get_test_program_args(self, args: list[str], hosts: list[str] = ["localhost"]) -> list[str]:
        retval = [
            # Add the first element to the args list which otherwise is the name of the binary to be
            # called.  It will be filtered out when parsing argv in the Program class, so it doesn't
            # matter what it is, as long as it is some valid string.
            "dummy-binary",
            f"--{PyDeployProgram.ARG_SSH_PORT}",
            str(self.VAGRANT_SSH_PORT),
            f"--{PyDeployProgram.ARG_SSH_IDENTITY_FILE}",
            self.VAGRANT_SSH_IDENTITY_FILE,
            "--pydeploy-config-dir",
            self.PYDEPLOY_REPO_DIR.__str__(),
            "--config-path",
            self.test_task_configs_path,
            "--hosts",
        ]
        host_str = ",".join(hosts)
        retval.append(host_str)

        # Finally, add the specific args for the task that we want to test
        retval = retval + args
        return retval

    @staticmethod
    def get_box_configs(test_env_vars: dict) -> dict:
        box_env_vars = {}
        for k, v in test_env_vars.items():
            if ENV_VAR_KEY_VAGRANT_BOX_INSTANCE_PREFIX in k:
                box_env_vars[k] = v

        # Create two dicts, one indexed by the box name, the other indexed by the port
        boxes = {}
        ports = {}

        for _, v in box_env_vars.items():
            tokens = v.split(":")
            assert (
                len(tokens) == 2
            ), "Env var entry for a vagrant box did not contain a boxname:port value"
            box_name = tokens[0]
            port = tokens[1]
            port_int = int(tokens[1])
            box_dir = os.path.join(test_env_vars[ENV_VAR_KEY_VAGRANT_DIR], box_name)
            boxes[box_name] = dict(port=port_int, box_dir=box_dir)
            ports[port] = dict(box_name=box_name, box_dir=box_dir)

        return dict(boxes=boxes, ports=ports)

    @staticmethod
    def is_box_running_on_port(port: int, box_configs: dict) -> Tuple[bool, Vagrant]:
        test_socket = None
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.bind(("localhost", port))
            logger.info(f"Port is free; port={port}")
        except Exception as e:
            logger.info(f"There is already a process bound to this port; port={port}, e={e}")
            # Do the reverse lookup on the port and then return a Vagrant object bound to the
            # correct box directory.
            box_configs_by_port = box_configs["ports"][str(port)]
            return (True, Vagrant(root=box_configs_by_port["box_dir"]))
        finally:
            if test_socket:
                test_socket.close()

        return (False, None)

    def put_bootstrap_file(self) -> str:
        # Get a reference to the bootstrap file for this distro and put it on the test box.
        bootstrap_file_name, bootstrap_file_local_path = ITBase.get_bootstrap_file_path(
            self.DISTRO_NAME
        )
        bootstrap_file_remote_path = os.path.join(os.sep, "var", "tmp", bootstrap_file_name)
        self.VAGRANT_BOX_FAB_CONNECTION.put(
            local=bootstrap_file_local_path, remote=bootstrap_file_remote_path
        )
        return bootstrap_file_remote_path

    def reboot_vagrant_box(self) -> None:
        logger.info(f"Halting vagrant box; self.VAGRANT_BOX={self.VAGRANT_BOX}")
        self.VAGRANT_BOX.halt()
        logger.info(f"Starting vagrant box; self.VAGRANT_BOX={self.VAGRANT_BOX}")
        self.VAGRANT_BOX.up()
        IntegrationTestUtils.wait_for_port_to_be_available(
            host=self.TEST_HOST, port=self.VAGRANT_SSH_PORT, sleep_time=5, timeout=90
        )
        logger.info("Vagrant box up and accepting connections")

    def run_bootstrap_file(self):
        bootstrap_remote_file_path = self.put_bootstrap_file()
        return self.VAGRANT_BOX_FAB_CONNECTION.run(
            f"{bootstrap_remote_file_path} -u {self.TEST_USER}"
        )

    def setup(self):
        logger.info(f"Running setup; test_id={self.id()}")
        is_running, box = ITBase.is_box_running_on_port(
            self.VAGRANT_SSH_PORT, self.VAGRANT_BOX_CONFIGS
        )

        if box == None:
            box = ITBase.create_vagrant_box(self.VAGRANT_BOX_DIR)

        if self.VAGRANT_BOX_REUSE == True and is_running == False:
            self.VAGRANT_BOX = box
            self.VAGRANT_BOX.up()
        elif self.VAGRANT_BOX_REUSE == False:
            if is_running == True:
                # Stop the existing box, whatever it might be and then fire up the one we will use for
                # the test.
                box.destroy()
            self.VAGRANT_BOX.up()

        # TODO: determine if we need to do something to ensure that the box is up and listening on the port
        # We probably need to ensure we can connect to is on the port first
        logger.info(f"Box ready; port={self.VAGRANT_SSH_PORT}")

        self.clean_config_dir()

    @classmethod
    def setUpBaseClass(cls: ITBase, distro: str) -> None:
        cls.TEST_ENV_VARS = cls.get_test_env_vars()
        cls.TEST_HOST = cls.TEST_ENV_VARS[ENV_VAR_KEY_TEST_HOST]
        cls.TEST_USER = cls.TEST_ENV_VARS[ENV_VAR_KEY_TEST_USER]
        cls.CONFIG_DIR = Path(cls.TEST_ENV_VARS[ENV_VAR_KEY_CONFIG_DIR])
        cls.PYDEPLOY_REPO_DIR = Path(cls.TEST_ENV_VARS[ENV_VAR_KEY_PYDEPLOY_CONFIGS_REPO_DIR])
        cls.DISTRO_NAME = distro
        cls.VAGRANT_BOX_NAME = distro
        cls.VAGRANT_DIR = cls.TEST_ENV_VARS[ENV_VAR_KEY_VAGRANT_DIR]
        cls.VAGRANT_BOX_CONFIGS = cls.get_box_configs(cls.TEST_ENV_VARS)
        cls.VAGRANT_SSH_PORT = cls.VAGRANT_BOX_CONFIGS["boxes"][distro]["port"]
        cls.VAGRANT_SSH_IDENTITY_FILE = cls.TEST_ENV_VARS[ENV_VAR_KEY_SSH_IDENTITY_FILE]
        cls.VAGRANT_BOX_DIR = cls.VAGRANT_BOX_CONFIGS["boxes"][distro]["box_dir"]

        # We want to load the pydeploy configs dict for the distro and version.  The cls.DISTRO_NAME
        # will include the window manager as well, so we need to trim that from the string to
        # concatenate the path to the distro config yaml file.
        distro_name_tokens = cls.DISTRO_NAME.split("_")
        assert (
            len(distro_name_tokens) == 3
        ), f"Splitting cls.DISTRO_NAME on '_' did not result in 3 tokens; cls.DISTRO_NAME={cls.DISTRO_NAME}"
        distro_and_version_file_name = f"{distro_name_tokens[1]}_{distro_name_tokens[2]}.yaml"
        distro_configs_path = os.path.join(
            cls.PYDEPLOY_REPO_DIR, "distros", distro_and_version_file_name
        )
        cls.VAGRANT_BOX = cls.create_vagrant_box(cls.VAGRANT_BOX_DIR)

        # Determine if we should be leaving the box up after we finish the test
        cls.VAGRANT_BOX_REUSE = Utils.str_to_bool(cls.TEST_ENV_VARS[ENV_VAR_KEY_VAGRANT_BOX_REUSE])

    def setup_test_program(self) -> Program:
        if self.VAGRANT_BOX_FAB_CONNECTION:
            self.VAGRANT_BOX_FAB_CONNECTION.close()
        self.setup_vagrant_box_fab_connection()
        namespace = Collection.from_module(WorkstationSetup)
        program = PyDeployProgram(namespace=namespace, version="0.1.0")
        Tasks.PROGRAM = program
        Tasks.NAMESPACE = namespace
        return program

    def setup_sub_test_and_run(self, args: list[str]):
        self.test_program = self.setup_test_program()
        self.test_program.run(argv=args)

    def setup_vagrant_box_fab_connection(self) -> None:
        if self.VAGRANT_BOX_FAB_CONNECTION:
            self.VAGRANT_BOX_FAB_CONNECTION.close()
        self.VAGRANT_BOX_FAB_CONNECTION = Connection(
            host=self.TEST_HOST,
            user="root",
            port=self.VAGRANT_SSH_PORT,
            connect_kwargs={
                "key_filename": self.VAGRANT_SSH_IDENTITY_FILE,
            },
        )

    def tear_down(self):
        if self.VAGRANT_BOX_REUSE == False:
            logger.info(f"Destroying vagrant box; self.VAGRANT_BOX_NAME={self.VAGRANT_BOX_NAME}")
            self.VAGRANT_BOX.destroy()
            logger.info(f"Vagrant box destroyed self.VAGRANT_BOX_NAME={self.VAGRANT_BOX_NAME}")
        if self.VAGRANT_BOX_FAB_CONNECTION:
            self.VAGRANT_BOX_FAB_CONNECTION.close()

    # #########################################################################
    # Tests applicable for all distros
    #

    def _test_configure_git(self):
        def exec_configure_git_test(args: dict, expected_git_config_values: set[str]):
            # Delete the .gitconfig file for the test user before each test
            self.setup_vagrant_box_fab_connection()
            r = self.VAGRANT_BOX_FAB_CONNECTION.sudo(
                f'bash -c "cd /home/{self.TEST_USER} && rm -f .gitconfig"', user=self.TEST_USER
            )
            self.assertTrue(r.ok)

            self.setup_sub_test_and_run(args)
            r = self.VAGRANT_BOX_FAB_CONNECTION.sudo("git config --list", user=self.TEST_USER)
            self.assertTrue(
                r.ok, "Unable to execute git config command to test result of configure-git task"
            )
            # Build a dict keyed by the gitconfig entries
            lines = r.stdout.split("\n")
            actual_git_config_values = {}
            for line in lines:
                if line.isspace() or len(line) == 0:
                    continue
                line_tokens = line.split("=")
                actual_git_config_values[line_tokens[0]] = line_tokens[1]
            self.assertDictEqual(expected_git_config_values, actual_git_config_values)

        test_email_address = f"{self.TEST_USER}@example.com"
        test_name = "Joe Blogs"
        test_data = [
            {
                # Test without configuring the default pull reconcilliaton method
                "args": self.get_test_program_args(
                    args=[
                        "configure-git",
                        "--user",
                        self.TEST_USER,
                        "--user-email",
                        test_email_address,
                        "--user-full-name",
                        test_name,
                        "--editor",
                        "vim",
                    ]
                ),
                "expected_git_config_values": {
                    "user.name": test_name,
                    "user.email": test_email_address,
                    "core.editor": "vim",
                },
            },
            {
                # Test configuring pull resolution permutations
                "args": self.get_test_program_args(
                    args=[
                        "configure-git",
                        "--user",
                        self.TEST_USER,
                        "--user-email",
                        test_email_address,
                        "--user-full-name",
                        test_name,
                        "--editor",
                        "vim",
                        "--default-pull-reconcile-method",
                        "rebase_false",
                    ]
                ),
                "expected_git_config_values": {
                    "user.name": test_name,
                    "user.email": test_email_address,
                    "core.editor": "vim",
                    "pull.rebase": "false",
                },
            },
            {
                # Test configuring pull resolution permutations
                "args": self.get_test_program_args(
                    args=[
                        "configure-git",
                        "--user",
                        self.TEST_USER,
                        "--user-email",
                        test_email_address,
                        "--user-full-name",
                        test_name,
                        "--editor",
                        "vim",
                        "--default-pull-reconcile-method",
                        "rebase_true",
                    ]
                ),
                "expected_git_config_values": {
                    "user.name": test_name,
                    "user.email": test_email_address,
                    "core.editor": "vim",
                    "pull.rebase": "true",
                },
            },
            {
                # Test configuring pull resolution permutations
                "args": self.get_test_program_args(
                    args=[
                        "configure-git",
                        "--user",
                        self.TEST_USER,
                        "--user-email",
                        test_email_address,
                        "--user-full-name",
                        test_name,
                        "--editor",
                        "vim",
                        "--default-pull-reconcile-method",
                        "ff_only",
                    ]
                ),
                "expected_git_config_values": {
                    "user.name": test_name,
                    "user.email": test_email_address,
                    "core.editor": "vim",
                    "pull.ff": "only",
                },
            },
        ]

        for t in test_data:
            exec_configure_git_test(t["args"], t["expected_git_config_values"])

    def _test_bootstrap(self, expected_packages: dict):
        self.setup_vagrant_box_fab_connection()
        self._exec_bootstrap_test(expected_packages)

    def _test_install_cert(self, ca_certs_bundle_path: str):
        cert_file_path = None
        temp_dir = None
        try:
            # Create a test CA cert that we will use for the test
            temp_dir = TemporaryDirectory()
            cert_file_path = ITBase.create_test_ca_cert(temp_dir)
            args = self.get_test_program_args(
                [
                    "install-cert",
                    "--cert-path",
                    cert_file_path,
                    "--cert-dir-name",
                    "ws-setup-cert",
                    "--cert-validation-string",
                    # A String that we will see in the output for this cert when 'querying' the ca cert
                    # bundle
                    "inttest-ca",
                ]
            )

            self.setup_sub_test_and_run(args)

            # To validate this task we will get the newly created cert bundle from the VM and then
            # verify that the cert that we have expected to be added to the bundle is present.

            # Get the newly updated certs bundle from the test vm
            local_actual_certs_bundle_path = os.path.join(temp_dir.name, "actual_ca_bundle.crt")
            self.VAGRANT_BOX_FAB_CONNECTION.get(
                remote=ca_certs_bundle_path,
                local=local_actual_certs_bundle_path,
            )

            # Validate that there is a cert in the bundle that contains the expected string.
            is_cert_present = IntegrationTestUtils.is_cert_in_bundle(
                cert_path=local_actual_certs_bundle_path, search_string="inttest-ca"
            )
            self.assertTrue(is_cert_present, "Did not find expected cert in cert bundle")

        except Exception as e:
            logger.error(e)
            raise (e)
        finally:
            if temp_dir:
                temp_dir.cleanup()

    def _test_install_cert_into_jvm(self):
        cert_file_path = None
        temp_dir = None
        try:
            # Create a test CA cert that we will use for the test
            temp_dir = TemporaryDirectory()
            cert_file_path = ITBase.create_test_ca_cert(temp_dir)
            args = self.get_test_program_args(
                [
                    "install-cert-into-jvm",
                    "--cert-path",
                    cert_file_path,
                    "--cert-alias",
                    ITBase.TEST_CERT_ALIAS,
                ]
            )
            self.setup_sub_test_and_run(args)

            # Ensure that the cert can now be found in the JVM keystore
            r = self.VAGRANT_BOX_FAB_CONNECTION.run(
                f"keytool -cacerts -list -storepass changeit | grep -i {ITBase.TEST_CERT_ALIAS}"
            )
            logger.info(f"Output from checking of cert is present in JVM keystore={r.stdout}")
            self.assertEqual(0, r.return_code)

        except Exception as e:
            logger.error(e)
            raise (e)
        finally:
            if temp_dir:
                temp_dir.cleanup()

    def _test_install_chrome(self):
        """
        Create an test instance of an invoke Program, and then build the set of argv arguments that
        we will pass to it to execute the test.
        """
        args = self.get_test_program_args(["install-chrome"])
        self.setup_sub_test_and_run(args)
        expected_packages = {"google-chrome-stable"}
        self._validate_installed_packages(expected_packages)

    def _test_install_docker(self):
        # We will pass in argumens to override all of the docker daemon.json configs and then
        # validate the daemon.json after we execute the task.
        args = self.get_test_program_args(
            [
                "install-docker",
                "--docker-user",
                self.TEST_USER,
                "--docker-bip",
                "10.28.0.1/24",
                "--docker-fixed-cidr",
                "10.28.0.1/25",
                "--docker-default-addr-pools-base",
                "10.29.0.0/16",
                "--docker-default-addr-pools-size",
                "23",
                "--docker-insecure-registries",
                "git.example.com:8443,git.exmple.org:8443",
            ]
        )
        expected_daemon_json = {
            "insecure-registries": ["git.example.com:8443", "git.exmple.org:8443"],
            "bip": "10.28.0.1/24",
            "fixed-cidr": "10.28.0.1/25",
            "default-address-pools": [{"base": "10.29.0.0/16", "size": 23}],
        }
        self.setup_sub_test_and_run(args)
        expected_packages = {"docker-ce", "docker-ce-cli", "containerd.io"}
        self._validate_installed_packages(expected_packages)

        temp_dir = TemporaryDirectory()

        # Create a docker-compose.yml file and run it to validate that docker is working, that we were
        # able to install docker-compose, and that the test user was added to the docker group.
        docker_compose_yaml = {
            "version": "'3'",
            "services": {"hello-world": {"image": "hello-world:latest"}},
        }
        docker_compose_file_name = "docker-compose.yml"
        docker_compose_yaml_local_file_path = os.path.join(temp_dir.name, docker_compose_file_name)
        IntegrationTestUtils.write_yaml_file(
            docker_compose_yaml_local_file_path, docker_compose_yaml
        )
        docker_compose_yaml_remote_file_path = os.path.join("/var/tmp/", docker_compose_file_name)
        self.VAGRANT_BOX_FAB_CONNECTION.put(
            docker_compose_yaml_local_file_path, docker_compose_yaml_remote_file_path
        )
        # TODO capture this as an article to detail how to run a multiple stage command via fabric 2.x
        r = self.VAGRANT_BOX_FAB_CONNECTION.sudo(
            'bash -c "cd /var/tmp/ && docker-compose up"', user=self.TEST_USER
        )
        self.assertEquals(0, r.return_code)
        if (
            "This message shows that your installation appears to be working correctly"
            not in r.stdout
        ):
            self.fail("Unable to run docker-compose up")
        self.VAGRANT_BOX_FAB_CONNECTION.run(f"rm -f {docker_compose_yaml_remote_file_path}")

        # Download the daemon.json file and validate that it contains the expected configs.
        actual_daemon_json_local_path = os.path.join(temp_dir.name, "actual_daemon.json")
        self.VAGRANT_BOX_FAB_CONNECTION.get(
            remote="/etc/docker/daemon.json", local=actual_daemon_json_local_path
        )
        actual_daemon_json = None
        with open(actual_daemon_json_local_path, "r") as f:
            actual_daemon_json = json.load(f)
        self.assertDictEqual(expected_daemon_json, actual_daemon_json)

        temp_dir.cleanup()

    def _test_install_drawio(self, expected_packages: set):
        args = self.get_test_program_args(["install-drawio"])
        self.setup_sub_test_and_run(args)
        self._validate_installed_packages(expected_packages)

    def _test_install_google_cloud_cli(self, expected_packages: set):
        args = self.get_test_program_args(["install-google-cloud-cli"])
        self.setup_sub_test_and_run(args)
        self._validate_installed_packages(expected_packages)

    def _test_install_gradle(self, version: str = None):
        args = self.get_test_program_args(
            [
                "install-gradle",
                "--version",
                version,
            ]
        )
        self.setup_sub_test_and_run(args)
        r = self.VAGRANT_BOX_FAB_CONNECTION.run("/usr/local/gradle/bin/gradle -v")
        self._check_fab_result(
            result=r,
            print_stdout=True,
            fail_on_failure=True,
            validation_string=f"Gradle {version}",
        )

    def _test_install_helm(self):
        args = self.get_test_program_args(["install-helm"])
        self.setup_sub_test_and_run(args)
        r = self.VAGRANT_BOX_FAB_CONNECTION.run("/usr/local/bin/helm | head -n 1")
        # We should be able to execute the helm binary successfully, and get some expected output.
        expected_output = "The Kubernetes package manager"
        self.assertEquals(0, r.return_code)
        self.assertTrue(expected_output in r.stdout)

    def _test_install_intellij(self, version: str = None):
        args = ["install-intellij"]
        if version is not None:
            args = args + ["--version", version]
        args = self.get_test_program_args(args)
        self.setup_sub_test_and_run(args)

        # We don't have an XWindows session running so we will get an error when we try to fire up
        # IntelliJ.  However, we can run it and still get some expected output to verify that it is
        # installed where expected and that it will run.
        r = self.VAGRANT_BOX_FAB_CONNECTION.run("/usr/local/intellij/bin/idea.sh -v", warn=True)
        self._check_fab_result(
            result=r,
            print_stdout=True,
            print_stderr=True,
            fail_on_failure=False,
            validation_string="Unable to detect graphics environment",
            check_stderr=True,
        )

    def _test_install_java_adoptium_eclipse_temurin(self, version: str):
        args = self.get_test_program_args(
            [
                "install-java-adoptium-eclipse-temurin",
                "--version",
                version,
            ]
        )
        self.setup_sub_test_and_run(args)
        expected_packages = {f"temurin-{version}-jdk"}
        self._validate_installed_packages(expected_packages)

    def _test_install_java_openjdk(self, version: str):
        args = self.get_test_program_args(
            [
                "install-java-openjdk",
                "--version",
                version,
            ]
        )
        self.setup_sub_test_and_run(args)
        expected_packages = {
            f"openjdk-{version}-doc",
            f"openjdk-{version}-jdk",
            f"openjdk-{version}-source",
        }
        self._validate_installed_packages(expected_packages)

    def _test_install_maven(self, version: str = None):
        args = self.get_test_program_args(["install-maven"])
        self.setup_sub_test_and_run(args)

        r = self.VAGRANT_BOX_FAB_CONNECTION.run(
            "/usr/local/apache-maven/bin/mvn", warn=True, hide="both"
        )
        self._check_fab_result(
            result=r,
            print_stdout=True,
            fail_on_failure=False,
            validation_string="Scanning for projects",
        )

        if version != None:
            r = self.VAGRANT_BOX_FAB_CONNECTION.run(
                "/usr/local/apache-maven/bin/mvn --version", warn=True, hide="both"
            )
            self._check_fab_result(
                result=r,
                print_stdout=True,
                fail_on_failure=False,
                validation_string=version,
            )

    def _test_install_minikube(self):
        args = self.get_test_program_args(["install-minikube", "--minikube-user", self.TEST_USER])
        self.setup_sub_test_and_run(args)
        # The minikube dependency installation updates the initramfs so we should reboot to ensure
        # that everything works correctly after a reboot.
        self.reboot_vagrant_box()
        r = self.VAGRANT_BOX_FAB_CONNECTION.sudo(
            "minikube start --memory=2048mb", user=self.TEST_USER
        )
        self.assertTrue(r.ok)

        r = self.VAGRANT_BOX_FAB_CONNECTION.sudo("minikube status", user=self.TEST_USER)
        self.assertTrue(r.ok)
        expected_status = {
            "minikube",
            "type: Control Plane",
            "host: Running",
            "kubelet: Running",
            "apiserver: Running",
            "kubeconfig: Configured",
        }
        actual_status = set([i for i in r.stdout.split("\n") if i != ""])
        self.assertEqual(expected_status, actual_status)

        r = self.VAGRANT_BOX_FAB_CONNECTION.sudo("minikube stop", user=self.TEST_USER)
        self.assertTrue(r.ok)
        r = self.VAGRANT_BOX_FAB_CONNECTION.sudo("minikube status", user=self.TEST_USER, warn=True)
        expected_status = {
            "minikube",
            "type: Control Plane",
            "host: Stopped",
            "kubelet: Stopped",
            "apiserver: Stopped",
            "kubeconfig: Stopped",
        }
        actual_status = set([i for i in r.stdout.split("\n") if i != ""])
        self.assertEqual(expected_status, actual_status)

    def _test_install_packages(self, expected_packages: dict):
        args = self.get_test_program_args(["install-packages"])
        self.setup_sub_test_and_run(args)
        self._validate_installed_packages(expected_packages)

    def _test_pgadmin(self):
        args = self.get_test_program_args(["install-pgadmin"])
        self.setup_sub_test_and_run(args)
        expected_packages = {"pgadmin4"}
        self._validate_installed_packages(expected_packages)

    def _test_install_redshift(self):
        expected_redshift_systemd_lines = [
            "[Unit]\n",
            "Description=Runs redshift\n",
            "\n",
            "[Service]\n",
            "ExecStart=/usr/bin/redshift\n",
            "\n",
            "[Install]\n",
            "WantedBy = default.target\n",
        ]
        remote_actual_config_file_path = f"/home/{self.TEST_USER}/.config/redshift.conf"
        remote_actual_systemd_file_path = (
            f"/home/{self.TEST_USER}/.config/systemd/user/redshift.service"
        )

        def validate_redshift_results(expected_config_lines: list[str]) -> None:
            _validate_redshift_results(expected_config_lines, remote_actual_config_file_path)
            _validate_redshift_results(
                expected_redshift_systemd_lines, remote_actual_systemd_file_path
            )

        def _validate_redshift_results(expected_lines: list[str], remote_file_path: str) -> None:
            local_file_path = os.path.join(temp_dir.name, "actual_file")
            self.VAGRANT_BOX_FAB_CONNECTION.get(remote_file_path, local_file_path)
            actual_lines = None
            with open(local_file_path, "r") as f:
                actual_lines = f.readlines()
            self.assertListEqual(expected_lines, actual_lines)

        temp_dir = None
        try:
            temp_dir = TemporaryDirectory()
            # Run using the default configurations
            args = self.get_test_program_args(
                [
                    "install-redshift",
                    "--redshift-user",
                    self.TEST_USER,
                ]
            )
            self.setup_sub_test_and_run(args)
            # We called the target without overriding any of the default values so we will expect
            # that the rendered config files contain the default values
            expected_redshift_config_lines = [
                "[redshift]\n",
                "temp-day=6500K\n",
                "temp-night=2500K\n",
                "brightness-day=1.0\n",
                "brightness-night=0.9\n",
                "location-provider=geoclue2\n",
            ]
            validate_redshift_results(expected_redshift_config_lines)

            # Run overriding the default configurations
            args = self.get_test_program_args(
                [
                    "install-redshift",
                    "--redshift-user",
                    self.TEST_USER,
                    "--temp-day",
                    "6250K",
                    "--temp-night",
                    "2750K",
                    "--brightness-day",
                    "0.95",
                    "--brightness-night",
                    "0.75",
                ]
            )
            self.setup_sub_test_and_run(args)
            # We called the target without overriding any of the default values so we will expect
            # that the rendered config files contain the default values
            expected_redshift_config_lines = [
                "[redshift]\n",
                "temp-day=6250K\n",
                "temp-night=2750K\n",
                "brightness-day=0.95\n",
                "brightness-night=0.75\n",
                "location-provider=geoclue2\n",
            ]
            validate_redshift_results(expected_redshift_config_lines)

        except Exception as e:
            raise (e)
        finally:
            if temp_dir is not None:
                temp_dir.cleanup()

    def _test_install_slack(self):
        args = self.get_test_program_args(["install-slack"])
        self.setup_sub_test_and_run(args)
        expected_packages = {"slack-desktop"}
        self._validate_installed_packages(expected_packages)

    # TODO: We could DRY out these "install-package" type of tests
    def _test_install_virtualbox(self, expected_packages: set):
        args = self.get_test_program_args(["install-virtualbox"])
        self.setup_sub_test_and_run(args)
        self._validate_installed_packages(expected_packages)

    def _test_install_vscode(self):
        args = self.get_test_program_args(["install-vscode"])
        self.setup_sub_test_and_run(args)
        expected_packages = {"code"}
        self._validate_installed_packages(expected_packages)

    def _test_install_zoom(self, expected_packages: set):
        args = self.get_test_program_args(["install-zoom"])
        self.setup_sub_test_and_run(args)
        self._validate_installed_packages(expected_packages)

    def _test_setup_inotify(self):
        args = self.get_test_program_args(["setup-inotify", "--max-user-watches", "6476476"])
        self.setup_sub_test_and_run(args)
        r = self.VAGRANT_BOX_FAB_CONNECTION.run(f"sysctl -a | grep fs.inotify.max_user_watches")
        actual_sysctl_inotify_value = r.stdout.split("=")[1].strip()
        self.assertEqual("6476476", actual_sysctl_inotify_value)

    # #########################################################################

    def _validate_bootstrap(self, expected_packages: list[str]) -> None:
        pass

    def _validate_bootstrap_ssh_configs(self):
        """
        Validate that the bootstrap script has properly updated the sshd configs and restarted the
        sshd server without errors.
        """
        r = self.VAGRANT_BOX_FAB_CONNECTION.run(f'grep "PermitRootLogin yes" /etc/ssh/sshd_config')
        self._check_fab_result(r)

    def _validate_bootstrap_test_user_setup(self):
        """
        Validate that the test user was added to the test host.
        """
        r = self.VAGRANT_BOX_FAB_CONNECTION.run(f"getent passwd {self.TEST_USER}")
        self._check_fab_result(r)

    def _validate_bootstrap_test_user_added_to_sudoers(self):
        r = self.VAGRANT_BOX_FAB_CONNECTION.run(f"cat /etc/sudoers.d/{self.TEST_USER}")
        self._check_fab_result(r)
        expected_sudoers_file_contents = f"{self.TEST_USER} ALL=(ALL) NOPASSWD:ALL\n"
        actual_sudoers_file_contents = r.stdout
        self.assertEqual(expected_sudoers_file_contents, actual_sudoers_file_contents)

    def _validate_installed_packages(self, expected_packages: set[str]):
        actual_installed_packages = self.get_installed_packages()
        # Ensure that there is an entry in the actual installed packages set for every entry in the
        # expected packages set.
        for expected_package in expected_packages:
            if expected_package not in actual_installed_packages:
                self.fail(
                    f"Expected package was not installed; expected_package={expected_package}"
                )

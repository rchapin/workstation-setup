import json
import logging
import os
import sys
from tempfile import TemporaryDirectory
from pydeploy.enums import Distro, WindowManager
from workstationsetup.integration_tests.test_base import ITBase
from workstationsetup.integration_tests.int_test_utils import IntegrationTestUtils


logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


class ITDebian(ITBase):
    def get_installed_packages(self) -> set[str]:
        r = self.VAGRANT_BOX_FAB_CONNECTION.run("dpkg --get-selections")
        stdout_lines = r.stdout.split("\n")
        retval = set()
        for line in stdout_lines:
            if "install" in line:
                tab_tokens = line.split("\t")
                package_arch_tokens = tab_tokens[0].split(":")
                if package_arch_tokens[0]:
                    retval.add(package_arch_tokens[0])

        return retval

    @classmethod
    def setUpClass(cls):
        cls.setUpBaseClass("xfce4_debian_11")

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        logger.info(f"Running setup; test_id={self.id()}")
        self.setup()

        self.test_task_configs = IntegrationTestUtils.create_base_configs(
            distro=Distro.DEBIAN, version="11", window_manager=WindowManager.XFCE4
        )
        # Add some APPEND and OVERRIDE configs to the test_task_configs that will exercise the code
        # the enables users to extend the default configs.
        self.test_task_configs["task_configs"] = {
            "install-packages": {
                "packages": {
                    "mode": "APPEND",
                    "value": ["remmina", "hp-ppd", "hplip", "hplip-gui"],
                }
            },
            "install-maven": {
                "version": {
                    "mode": "OVERRIDE",
                    "value": "3.6.3",
                }
            },
        }
        self.test_task_configs_path = os.path.join(self.CONFIG_DIR, "test_tasks_debian_11.yaml")
        IntegrationTestUtils.write_yaml_file(
            output_path=self.test_task_configs_path, data=self.test_task_configs
        )

    def tearDown(self):
        self.tear_down()

    def test_debian_11(self):
        # TODO: A lot of these tests can be moved to the test_base class ultimately as they really should just be
        # testing the abstracted nature of the tasks.
        self._test_bootstrap()
        self._test_install_packages()
        self.reboot_vagrant_box()
        self._test_install_chrome()
        self._test_configure_git()
        self._test_install_slack()
        self._test_install_cert()
        self._test_install_docker()
        self._test_install_helm()
        self._test_install_vscode()
        self._test_setup_inotify()

        temurin_jdk_version = "17"
        self._test_install_java_adoptium_eclipse_temurin(version=temurin_jdk_version)
        # Uninstall java so that we can test the open-jdk task.
        self.setup_vagrant_box_fab_connection()
        self.VAGRANT_BOX_FAB_CONNECTION.run(
            f"apt-get -y --purge remove temurin-{temurin_jdk_version}-jdk"
        )

        openjdk_version = "17"
        self._test_install_java_openjdk(version=openjdk_version)

        self._test_install_cert_into_jvm()
        self._test_install_maven()
        self._test_install_gradle(version="7.5")
        self._test_install_intellij()
        self._test_install_google_cloud_cli({"google-cloud-cli"})
        self._test_install_minikube()
        self._test_install_redshift()
        self._test_pgadmin()
        self._test_install_drawio({"draw.io"})
        self._test_install_zoom({"zoom"})

    def _test_bootstrap(self):
        self.setup_vagrant_box_fab_connection()
        expected_packages = {
            "apt-transport-https",
            "build-essential",
            "curl",
            "git",
            "libbz2-dev",
            "libffi-dev",
            "libgdbm-dev",
            "libncurses5-dev",
            "libnss3-dev",
            "libreadline-dev",
            "libsqlite3-dev",
            "libssl-dev",
            "software-properties-common",
            "vim",
            "wget",
            "zlib1g-dev",
        }
        self._exec_bootstrap_test(expected_packages)

    def _test_install_cert(self):
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
                remote=self.DISTRO_CONFIGS["install-cert"]["ca_certs_bundle_path"],
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

    def _test_install_helm(self):
        args = self.get_test_program_args(["install-helm"])
        self.setup_sub_test_and_run(args)
        r = self.VAGRANT_BOX_FAB_CONNECTION.run("/usr/local/bin/helm | head -n 1")
        # We should be able to execute the helm binary successfully, and get some expected output.
        expected_output = "The Kubernetes package manager"
        self.assertEquals(0, r.return_code)
        self.assertTrue(expected_output in r.stdout)

    def _test_install_packages(self):
        args = self.get_test_program_args(["install-packages"])
        self.setup_sub_test_and_run(args)
        expected_packages = {
            "debsig-verify",
            "bind9-dnsutils",
            "bridge-utils",
            "flameshot",
            "gimp",
            "git-gui",
            "gitk",
            "gnupg",
            "jq",
            "netcat",
            "net-tools",
            "okular",
            "rsync",
            "terminator",
            "tree",
            "yadm",
            "apt-transport-https",
            "build-essential",
            "curl",
            "git",
            "libbz2-dev",
            "libffi-dev",
            "libgdbm-dev",
            "libncurses5-dev",
            "libnss3-dev",
            "libreadline-dev",
            "libsqlite3-dev",
            "libssl-dev",
            "software-properties-common",
            "vim",
            "wget",
            "zlib1g-dev",
            # Include the APPENDed packages in the assertion as well
            "remmina",
            "hp-ppd",
            "hplip",
            "hplip-gui",
        }
        self._validate_installed_packages(expected_packages)

    def _test_install_slack(self):
        args = self.get_test_program_args(["install-slack"])
        self.setup_sub_test_and_run(args)
        expected_packages = {"slack-desktop"}
        self._validate_installed_packages(expected_packages)

    def _test_install_vscode(self):
        args = self.get_test_program_args(["install-vscode"])
        self.setup_sub_test_and_run(args)
        expected_packages = {"code"}
        self._validate_installed_packages(expected_packages)

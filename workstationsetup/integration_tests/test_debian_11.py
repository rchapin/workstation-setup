import unittest
import json
import logging
import os
import sys
from tempfile import TemporaryDirectory
from pydeploy.enums import Distro, WindowManager
from workstationsetup.integration_tests.test_debian import ITDebian
from workstationsetup.integration_tests.int_test_utils import IntegrationTestUtils


logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


class ITDebian11(ITDebian):
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
                "packages": [
                    "apt-transport-https",
                    "ca-certificates",
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
                    "zip",
                    # Added packages
                    "remmina",
                    "hp-ppd",
                    "hplip",
                    "hplip-gui",
                ]
            },
            "install-maven": {"version": "3.6.3"},
        }
        self.test_task_configs_path = os.path.join(self.CONFIG_DIR, "test_tasks_debian_11.yaml")
        IntegrationTestUtils.write_yaml_file(
            output_path=self.test_task_configs_path, data=self.test_task_configs
        )

    def test_debian_11(self):
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
        self._test_bootstrap(expected_packages)

        expected_packages = {
            "apt-transport-https",
            "ca-certificates",
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
            "zip",
            # Added packages
            "remmina",
            "hp-ppd",
            "hplip",
            "hplip-gui",
        }
        self._test_install_packages(expected_packages)

        self.reboot_vagrant_box()
        self._test_install_chrome()
        self._test_configure_git()
        self._test_install_slack()
        self._test_install_cert(ca_certs_bundle_path="/etc/ssl/certs/ca-certificates.crt")
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
        self._test_install_java_openjdk(version="17")
        self._test_install_cert_into_jvm()

        # Ensure that the overridden version of maven was installed and not the default version in
        # the common configs.
        self._test_install_maven(version="3.6.3")

        self._test_install_gradle(version="7.5")
        self._test_install_intellij()
        self._test_install_google_cloud_cli({"google-cloud-cli"})
        self._test_install_minikube()
        self._test_install_redshift()
        self._test_pgadmin()
        self._test_install_drawio({"draw.io"})
        self._test_install_zoom({"zoom"})
        self._test_install_virtualbox({"virtualbox-6.1"})

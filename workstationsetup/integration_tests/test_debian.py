import json
import logging
import os
import sys
from abc import ABC
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


class ITDebian(ITBase, ABC):
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

    def tearDown(self):
        self.tear_down()

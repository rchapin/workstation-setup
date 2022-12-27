import unittest
import logging
import os
import sys
from fabric import Connection
from invoke import Context, Config
from tasks import tasks

from workstationsetup.integration_tests.it_base import ITBase


logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


class ITDebian(ITBase):
    @classmethod
    def setUpClass(cls):
        cls.setUpBaseClass("debian_11")

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        logger.info(f"Running setup; test_id={self.id()}")
        self.setup()

    def tearDown(self):
        self.tear_down()

    def test_something(self):
        logger.info("test_something")
        # self.assertTrue(True, "true")

    def test_install_chrome(self):
        print("noop")
        # tasks.install_chrome(self.INV_CONTEXT)

    def test_install_packages(self):
        print("noop")
        # tasks.install_packages(self.INV_CONTEXT)
        # r = self.INV_CONTEXT.conn.run("dpkg --get-selections")
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
            "#",
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
        print("blah")
        # LEFT OFF:  Need to validate this test and then move this whole thing into a monolithic
        # test for this distro so that we can sequence the test events similarly as to how a
        # user would run them.


# Create a debian_11 xfce, specific container

# Might be the way to do this, make a monolithic test so that I can order the tests
#
#   def step1(self):
#       ...

#   def step2(self):
#       ...

#   def _steps(self):
#     for name in dir(self): # dir() result is implicitly sorted
#       if name.startswith("step"):
#         yield name, getattr(self, name)

#   def test_steps(self):
#     for name, step in self._steps():
#       try:
#         step()
#       except Exception as e:
#         self.fail("{} failed ({}: {})".format(step, type(e), e))
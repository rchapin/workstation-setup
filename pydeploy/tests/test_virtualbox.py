import json
import os
import requests
import unittest
from pydeploy import utils
from pydeploy.virtualbox import VirtualBox
from pydeploy.utils import Utils, GitHubReleaseInfo
from unittest.mock import MagicMock, patch

EXTPACK_STDOUT_ZERO_ENTRIES = "Extension Packs: 0"
EXTPACK_STDOUT_ONE_ENTRY = """Extension Packs: 1
Pack no. 0:   Oracle VM VirtualBox Extension Pack
Version:      6.1.44
Revision:     156814
Edition:
Description:  Oracle Cloud Infrastructure integration, USB 2.0 and USB 3.0 Host Controller, Host Webcam, VirtualBox RDP, PXE ROM, Disk Encryption, NVMe.
VRDE Module:  VBoxVRDP
Usable:       true
Why unusable:
"""
EXTPACK_STDOUT_INVALID_FIRST_LINE = "invalid first line"

class VirtualBoxTest(unittest.TestCase):

    def test_parse_installed_extpacks(self):
        test_data = [
            {
                "name": "No input",
                "stdout": "",
                "expect_exception": True
            },
            {
                "name": "Invalid first line",
                "stdout": EXTPACK_STDOUT_INVALID_FIRST_LINE,
                "expect_exception": True
            },
            {
                "name": "No extension packs",
                "stdout": EXTPACK_STDOUT_ZERO_ENTRIES,
                "expected_result": {},
                "expect_exception": False
            },
            {
                "name": "One extension pack",
                "stdout": EXTPACK_STDOUT_ONE_ENTRY,
                "expected_result": {
                    "version": "6.1.44",
                    "revision": "156814",
                    "usable": True,
                },
                "expect_exception": False
            },
        ]

        for t in test_data:
            with self.subTest(f"{t['name']}"):
                if t["expect_exception"]:
                    self.assertRaises(Exception, VirtualBox.parse_installed_extpacks, t["stdout"])
                else:
                    actual_result = VirtualBox.parse_installed_extpacks(t["stdout"])
                    self.assertEqual(t["expected_result"], actual_result)

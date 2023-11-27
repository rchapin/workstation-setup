import unittest
from pydeploy.enums import Distro, WindowManager


class EnumsTest(unittest.TestCase):
    def test_get_by_name(self):
        test_data = [
            dict(
                actual=Distro.get_by_name("DEBIAN"),
                expected=Distro.DEBIAN,
            ),
            dict(
                actual=WindowManager.get_by_name("XFCE4"),
                expected=WindowManager.XFCE4,
            ),
        ]

        for t in test_data:
            self.assertEqual(t["expected"], t["actual"])

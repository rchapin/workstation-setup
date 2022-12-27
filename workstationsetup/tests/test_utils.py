import unittest
from workstationsetup import utils

class UtilsTest(unittest.TestCase):

    def test_is_string_empty(self):
        actual_result = utils.is_string_empty("  b  ")
        self.assertFalse(actual_result)
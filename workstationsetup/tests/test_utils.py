import unittest
from pydeploy.utils import Utils

class UtilsTest(unittest.TestCase):

    def test_hydrate(self):
        test_data = [
            {
                "input": {
                    "templates": [
                        "some-package-${version}-${arch}.pkg",
                        "some-other-package-${version}-${arch}.pkg",
                    ],
                    "values": {
                        "version": "1.9.1",
                        "arch": "x86_64"
                    }
                },
                "expected": [
                    "some-package-1.9.1-x86_64.pkg",
                    "some-other-package-1.9.1-x86_64.pkg",
                ],
            }
        ]

        for t in test_data:
            actual = Utils.hydrate(t["input"]["templates"], t["input"]["values"])
            self.assertCountEqual(t["expected"], actual)

    def test_is_string_empty(self):
        test_data = [
            {
                "input": "  b  ",
                "expected": False
            },
            {
                "input": "blah     Foo",
                "expected": False
            },
            {
                "input": "    b",
                "expected": False
            },
            {
                "input": "    ",
                "expected": True
            },
            {
                "input": "\t",
                "expected": True
            },
        ]
        for t in test_data:
            actual_result = Utils.is_string_empty(t["input"])
            self.assertEqual(t["expected"], actual_result)

    def test_str_to_bool(self):
        test_data = [
            {
                "input": "True",
                "expected": True,
            },
            {
                "input": "TrUe",
                "expected": True,
            },
            {
                "input": "true",
                "expected": True,
            },
            {
                "input": "False",
                "expected": False,
            },
            {
                "input": "false",
                "expected": False,
            },
            {
                "input": "faLse",
                "expected": False,
            },
        ]

        for t in test_data:
            actual = Utils.str_to_bool(t["input"])
            self.assertEqual(t["expected"], actual, f"Did not get expected output; input={t['input']}, actual={actual}")


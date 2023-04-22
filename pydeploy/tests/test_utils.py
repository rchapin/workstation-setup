import json
import os
import requests
import unittest
from pydeploy import utils
from pydeploy.utils import Utils, GitHubReleaseInfo
from unittest.mock import MagicMock, patch

UPPER = range(97, 123)
LOWER = range(65, 91)

class UtilsTest(unittest.TestCase):

    def get_test_data_file_path(self, filename) -> str:
        cwd = os.path.dirname(os.path.realpath(__file__))
        test_data_path =  os.path.join(cwd, "resources", filename)
        return test_data_path

    def test_get_lines_from_file(self):
        pattern = "draw.io-x64-.*zip.blockmap"
        expected_result = ["draw.io-x64-21.1.2.zip.blockmap  5b6a2ab55f51a992242e6930dbd74823dac0b85e0cdb8647edd8e80e795c559f"]
        self.exec_test_get_lines_from_file(pattern=pattern, expected_result=expected_result)

    def test_get_lines_from_file_no_results(self):
        pattern = "forble"
        expected_result = []
        self.exec_test_get_lines_from_file(pattern=pattern, expected_result=expected_result)

    def test_get_lines_from_file_multiple_matches(self):
        pattern = ".*zip.*"
        expected_result = [
            "draw.io-arm64-21.1.2.zip.blockmap  03d237568e9670cad58503e8b5decae690a64d5523cf4d1468e8ba1c0cb3029a",
            "draw.io-x64-21.1.2.zip.blockmap  5b6a2ab55f51a992242e6930dbd74823dac0b85e0cdb8647edd8e80e795c559f",
            "draw.io-arm64-21.1.2.zip  fa46e9168554ce0e1029f61e57a7ea8be4526d915caa90167d57dabdbce36232",
            "draw.io-x64-21.1.2.zip  6da7679d7c2ffbe438a5506c64300f861728a0c8235afd6dea2ec0b2b9b7887a",
        ]
        self.exec_test_get_lines_from_file(pattern=pattern, expected_result=expected_result)

    def exec_test_get_lines_from_file(self, pattern: str, expected_result: list[str]) -> None:
        cwd = os.path.dirname(os.path.realpath(__file__))
        test_data_path = self.get_test_data_file_path("get-line-from-file-test-data.txt")

        actual_result = Utils.get_lines_from_file(path=test_data_path, pattern=pattern)
        self.assertCountEqual(
            expected_result,
            actual_result,
        )

    @patch("pydeploy.utils.requests.get")
    def test_get_github_release_info(self, mock_get):
        # Load test json data
        cwd = os.path.dirname(os.path.realpath(__file__))
        test_data_json_path = os.path.join(cwd, "resources", "api-github-com-response.json")
        test_json_data = None
        with open(test_data_json_path, "r") as f:
            data = f.read()
            test_json_data = json.loads(data)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = test_json_data
        mock_get.return_value = mock_response

        artifact_regex = "drawio-amd64-.*.deb"
        hashes_regex = "Files-SHA256-Hashes.txt"

        actual_result = Utils.get_github_release_info(
            url="http://example.com/output.json",
            artifact_regex=artifact_regex,
            hashes_regex=hashes_regex
        )

        self.assertEqual(
            "https://github.com/jgraph/drawio-desktop/releases/download/v20.8.16/drawio-amd64-20.8.16.deb",
            actual_result.artifact_url
        )
        self.assertEqual("drawio-amd64-20.8.16.deb", actual_result.artifact_filename)
        self.assertEqual(
            "https://github.com/jgraph/drawio-desktop/releases/download/v20.8.16/Files-SHA256-Hashes.txt",
            actual_result.hashes_url
        )
        self.assertEqual("Files-SHA256-Hashes.txt", actual_result.hashes_filename)

    def test_hydrate(self):
        test_data = [
            {
                "input": {
                    "templates": [
                        "some-package-${version}-${arch}.pkg",
                        "some-other-package-${version}-${arch}.pkg",
                    ],
                    "values": {"version": "1.9.1", "arch": "x86_64"},
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
            {"input": "  b  ", "expected": False},
            {"input": "blah     Foo", "expected": False},
            {"input": "    b", "expected": False},
            {"input": "    ", "expected": True},
            {"input": "\t", "expected": True},
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
            self.assertEqual(
                t["expected"],
                actual,
                f"Did not get expected output; input={t['input']}, actual={actual}",
            )

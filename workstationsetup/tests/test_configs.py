import unittest
from pydeploy.configs import Configs
from collections import ChainMap


class ConfigsTest(unittest.TestCase):
    def test_merge_configs(self):
        test_data = [
            {
                "a": {"temp": 123},
                "b": {"height": 6},
                "expected_result": {
                    "temp": 123,
                    "height": 6,
                },
            },
            {
                "a": {"key_one": {"temp": 123}},
                "b": {"key_one": {"height": 6}},
                "expected_result": {
                    "key_one": {"temp": 123, "height": 6},
                },
            },
            {
                "a": {"key_one": {"temp": 123, "height": 3}},
                "b": {"key_one": {"packages": ["a", "b", "c"], "configs": {"ka": 1, "kb": 2}}},
                "expected_result": {
                    "key_one": {
                        "temp": 123,
                        "height": 3,
                        "packages": ["a", "b", "c"],
                        "configs": {"ka": 1, "kb": 2},
                    }
                },
            },
            {
                "a": {
                    "key_one": {
                        "temp": 123,
                        "height": 3,
                    },
                    "configs": {
                        "foo": 1,
                        "bar": 2,
                        "sub_key": {
                            "x": 1,
                            "y": 2,
                        },
                    },
                },
                "b": {
                    "key_one": {
                        "packages": ["a", "b", "c"],
                    },
                    "configs": {"foo": 2, "ka": 1, "kb": 2},
                },
                "expected_result": {
                    "key_one": {
                        "temp": 123,
                        "height": 3,
                        "packages": ["a", "b", "c"],
                    },
                    "configs": {
                        "foo": 1,
                        "bar": 2,
                        "sub_key": {
                            "x": 1,
                            "y": 2,
                        },
                        "ka": 1,
                        "kb": 2,
                    },
                },
            },
        ]

        for t in test_data:
            actual_result = Configs.merge_configs(t["a"], t["b"])
            self.assertEqual(t["expected_result"], actual_result)

    def test_apply_override_configs(self):
        test_data = [
            {
                "name": "Override scalar key",
                "a": {
                    "temp": 123,
                    "height": 6,
                },
                "b": {
                    "height": 647,
                },
                "expected_result": {
                    "temp": 123,
                    "height": 647,
                },
            },
            {
                "name": "Override list sub-key",
                "a": {
                    "temp": 123,
                    "height": 6,
                    "key_one": {
                        "packages": ["a", "b", "c"],
                    },
                },
                "b": {
                    "key_one": {
                        "packages": ["a", "b", "d"],
                    },
                },
                "expected_result": {
                    "temp": 123,
                    "height": 6,
                    "key_one": {
                        "packages": ["a", "b", "d"],
                    },
                },
            },
            {
                "name": "Override nested sub-key value",
                "a": {
                    "temp": 123,
                    "height": 6,
                    "key_one": {
                        "things": {
                            "t1": "foo",
                            "t2": "blah",
                        },
                        "packages": ["a", "b", "c"],
                        "configs": {
                            "ka": 1,
                            "kb": 2,
                        },
                    },
                },
                "b": {
                    "key_one": {
                        "configs": {
                            "ka": 1,
                            "kb": 9,
                        },
                    },
                },
                "expected_result": {
                    "temp": 123,
                    "height": 6,
                    "key_one": {
                        "things": {
                            "t1": "foo",
                            "t2": "blah",
                        },
                        "packages": ["a", "b", "c"],
                        "configs": {
                            "ka": 1,
                            "kb": 9,
                        },
                    },
                },
            },
            {
                "name": "Additional sub-key in override",
                "a": {
                    "temp": 123,
                    "height": 6,
                    "key_one": {
                        "packages": ["a", "b", "c"],
                    },
                },
                "b": {
                    "key_one": {
                        "extra_key": True,
                    },
                },
                "expected_result": {
                    "temp": 123,
                    "height": 6,
                    "key_one": {
                        "packages": ["a", "b", "c"],
                        "extra_key": True,
                    },
                },
            },
        ]

        for t in test_data:
            with self.subTest(t["name"], t=t):
                actual_result = Configs.apply_override_configs(t["a"], t["b"])
                self.assertEqual(
                    t["expected_result"], actual_result, f"test failed; name={t['name']}"
                )

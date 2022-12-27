from enum import Enum


class Distro(Enum):
    DEBIAN = 1

    @staticmethod
    def get_by_name(enum_name):
        return Distro[enum_name.upper()]


class ConfigUpdateMode(Enum):
    APPEND = 1
    OVERRIDE = 2

    @staticmethod
    def get_by_name(enum_name):
        return ConfigUpdateMode[enum_name.upper()]

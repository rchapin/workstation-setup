from enum import Enum


class PyDeployEnum(Enum):
    @classmethod
    def get_by_name(cls, enum_name):
        return cls[enum_name.upper()]


class ArchiveType(PyDeployEnum):
    TAR = 1
    TAR_GZ = 2
    ZIP = 3


class ConfigUpdateMode(PyDeployEnum):
    APPEND = 1
    OVERRIDE = 2


class Distro(PyDeployEnum):
    # The value of the enum is the name of the class for this distro
    DEBIAN = "Debian"


class PackageCommand(PyDeployEnum):
    INSTALL = 1
    REMOVE = 2


class WindowManager(PyDeployEnum):
    XFCE4 = 1

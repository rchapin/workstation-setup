from __future__ import annotations
import docker
from docker.client import DockerClient
from docker.models.containers import Container
from invoke import run
import logging
import unittest
import os
import shutil
import sys
from typing import Tuple, Type
from fabric import Connection
from invoke import Context
from testcontainers.core.container import DockerContainer
from workstationsetup import utils

os.environ["PYTHONUNBUFFERED"] = "1"

# An environment variable that can be optionally exported to enable the reuse of a test container.
# If this is set, it is possible for things to get in a weird state as the test will not
# automatically kill a container that is listening on a given port.  However, if you are in the
# middle of development and don't want to have to trudge through all of the tests, set this
# environment variable to "1"
ENV_VAR_CONTAINER_REUSE = "WS_SETUP_INTTEST_REUSE_CONTAINER"

logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)

DOCKER_SSH_WAIT_TIME = 1


class ITBase(unittest.TestCase):

    FAB_CONNECTION = None
    INV_CONTEXT = None
    CONTAINER_IMAGE_NAME = None
    CONTAINER_PORT = None
    CONTAINER = None
    CONTAINER_REUSE = False

    def __init__(self, methodName: str = ...) -> None:
        super().__init__(methodName)

        self.container = None
        self.fab_conn = None
        self.inv_ctx = None
        self.docker_client = docker.from_env()

    @classmethod
    def setUpBaseClass(cls: ITBase, distro: str) -> None:
        os.environ["WS_SETUP_DISTRO"] = distro
        container_img_name, container_port = cls.get_container_configs("debian_11")
        cls.CONTAINER_IMAGE_NAME = container_img_name
        cls.CONTAINER_PORT = container_port

        # Setup the fabric connection instance and the invoke cotext that we will pass to each of
        # the tasks that we test.
        connection, context = cls.get_connection_and_context(cls.CONTAINER_PORT)
        cls.FAB_CONNECTION = connection
        cls.INV_CONTEXT = context

        cls.CONTAINER = cls.create_container(
            cls.CONTAINER_IMAGE_NAME, cls.CONTAINER_PORT
        )

        # Determine if we should be leaving the container after we start it.
        container_reuse = os.getenv(ENV_VAR_CONTAINER_REUSE, False)
        cls.CONTAINER_REUSE = True if container_reuse else False

    @staticmethod
    def get_connection_and_context(port: int) -> Tuple[Connection, Context]:
        connection = Connection(
            host="localhost",
            user="root",
            port=port,
            connect_kwargs={
                "key_filename": os.environ["WS_SETUP_INTTEST_SSH_IDENTITY_FILE"],
            },
        )
        context = Context()
        context.config["conn"] = connection
        return (connection, context)

    @staticmethod
    def get_container_configs(distro: str) -> Tuple[str, int]:
        # Get the already exported env var configs for this distro
        distro_env_var_key = f"WS_SETUP_INTTEST_CONTAINER_INSTANCE_{distro.upper()}"
        distro_configs = os.environ[distro_env_var_key]
        distro_configs_tokens = distro_configs.split(":")
        return (distro_configs_tokens[0], distro_configs_tokens[1])

    @staticmethod
    def create_container(image: str, port: int) -> DockerContainer:
        return DockerContainer(image=image).with_bind_ports(host=port, container=22)

    @staticmethod
    def get_container() -> DockerContainer:
        return ITBase.CONTAINER

    @staticmethod
    def is_container_running_on_port(port: int) -> Tuple[bool, Container]:
        try:
            docker_client = docker.from_env()
            containers = docker_client.containers.list()
            for container in containers:
                for _, bound_ports in container.ports.items():
                    for bound_port in bound_ports:
                        for bound_port_k, bound_port_v in bound_port.items():
                            if bound_port_k == "HostPort" and bound_port_v == port:
                                logger.info(
                                    f"Found container that is already running on exposed port; bound_port_v={bound_port_v}"
                                )
                                return (True, container)
        except docker.errors.NotFound as e:
            logger.info(f"Container not found; e={e}")
        return (False, None)

    def setup(self):
        logger.info(f"Running setup; test_id={self.id()}")

        is_running, container = ITBase.is_container_running_on_port(self.CONTAINER_PORT)
        if self.CONTAINER_REUSE == True and is_running == False:
            self.CONTAINER.start()
        elif self.CONTAINER_REUSE == False and is_running == True:
            # Stop the existing container and then fire up the one we will use for the test.
            container.stop()
            self.CONTAINER.start()
            _ = self.CONTAINER.get_exposed_port(22)

        logger.info(f"Container ready; exposed_port={self.CONTAINER_PORT}")

    # @staticmethod
    # def stop_container_on_same_port(port: int) -> None:
    #     if ITBase.is_container_running_on_port(port):
    #         pass
    #     else:
    #         pass

    def tear_down(self):
        logger.info(f"Running tear_down; test_id={self.id()}")
        if self.CONTAINER_REUSE == False:
            self.CONTAINER.stop()
            logger.info("stopped container")

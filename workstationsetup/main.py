import logging
import sys
from invoke import Collection
from pydeploy.program import PyDeployProgram
from pydeploy.tasks import Tasks
from workstationsetup.workstationsetup_tasks import WorkstationSetup

logging.basicConfig(
    format="%(asctime)s,%(levelname)s,%(module)s,%(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

namespace = Collection.from_module(WorkstationSetup)
program = PyDeployProgram(namespace=namespace, version="0.1.0")
Tasks.PROGRAM = program
Tasks.NAMESPACE = namespace

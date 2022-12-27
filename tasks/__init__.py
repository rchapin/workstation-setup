# Invoke entrypoint.  Add a collection and add all of the tasks that we want available in the root
# namespace.

import os

from invoke import Collection
from fabric import Connection

from . import tasks

namespace = Collection(tasks.install_chrome)

# Define some default configuration parameters.  Export any of the following env vars to override.
#
# By default we will run the tasks against the localhost
workstation_host = os.environ.get("WS_SETUP_HOST", "localhost")

conn = Connection(host=workstation_host, user="root")

# Create a dict that we will add to the default context that is passed into any of the tasks that
# are invoked.  This will give us the ability to pass in information to each task.
#
ws_ctx = dict(
    workstation_host=workstation_host,
)

# Add the dict to the namespace's context
namespace.configure(
    {
        "ws_ctx": ws_ctx,
        "conn": conn,
    }
)

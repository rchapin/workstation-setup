#!/bin/bash

PYTHON=python3.10

# ##############################################################################
# Will create and source a virtual environment for the workstation-setup set of
# This assumes that you already have the specified version of Python installed
# on your machine and that it is already in your PATH.
# ##############################################################################

. ./ws_env_vars.sh
VIRT_ENV_NAME=workstation-setup
VIRT_ENV_PATH=~/.virtualenvs/$VIRT_ENV_NAME

# ##############################################################################
# Ensure that we are sourcing this script so that that virtual env will be
# activated once it has finished
(return 0 2>/dev/null) && sourced=1 || sourced=0
if [ "$sourced" != 1 ]
then
  >&2 echo "You must source this script instead of executing it."
  exit 1
fi

# ##############################################################################
rm -rf $VIRT_ENV_PATH
mkdir -p $VIRT_ENV_PATH
$PYTHON -mvenv $VIRT_ENV_PATH
. $VIRT_ENV_PATH/bin/activate
pip install -U setuptools pip
pip install -r ./requirements.txt
pip install .

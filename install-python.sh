#!/bin/bash

set -e

PYTHON_VERSION=3.10.8
PYTHON_URL=https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz
DOWNLOADED_PATH=~/Downloads/Python-${PYTHON_VERSION}.tgz

# Ensure that we haven't already downloaded this file, and download it
# create the appropriate dirs, unpack and compile it.

rm -f $DOWNLOADED_PATH
wget $PYTHON_URL -P ~/Downloads
PY_DIR=$(echo $DOWNLOADED_PATH | awk -F/ '{ print $NF }' | sed 's/.tgz//')
PY_PREFIX=$(echo ~/usr/local/$PY_DIR | tr [:upper:] [:lower:])
mkdir -p ~/usr/local/src ~/usr/local/bin ~/usr/local/include $PY_PREFIX
tar -xzf $DOWNLOADED_PATH -C ~/usr/local/src/
cd ~/usr/local/src/$PY_DIR
./configure --prefix=$PY_PREFIX --exec-prefix=$PY_PREFIX
make && make install


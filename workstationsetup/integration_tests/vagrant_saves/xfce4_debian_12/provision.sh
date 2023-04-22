#!/usr/bin/env bash

set -e

# Ensure that we can passwordlessly ssh to this host.
sed -i '/PermitRootLogin/d' /etc/ssh/sshd_config
echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
systemctl restart sshd

# Ensure that there is an .ssh dir for the root user and add the public key that we will use to
# connect to the box to execute the tests.
mkdir -p /root/.ssh
cat /var/tmp/id_rsa.pub >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

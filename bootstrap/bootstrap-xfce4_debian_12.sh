#!/bin/bash

set -u

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  help
#   DESCRIPTION:  Outputs help info and then exits
#    PARAMETERS:  None
#       RETURNS:  void
#-------------------------------------------------------------------------------
function usage {
   cat << EOF
Usage: run-tests.sh [OPTIONS]

Options:

  -c CONFIGURE_SSHD (optional)
     Whether or not we should configure the sshd daemon to allow root logins and
     then restart the sshd service.

  -u NON_ROOT_USER
     The non-root user to be added to the system.  If the user already exists, this is a noop.

  -h HELP
     Outputs this basic usage information.
EOF
}

#
# Here we define variables to store the input from the command line arguments as
# well as define the default values.
#
HELP=0
CONFIGURE_SSHD=0
NON_ROOT_USER=0

PARSED_OPTIONS=`getopt -o hcu: -- "$@"`

# Check to see if the getopts command failed
if [ $? -ne 0 ];
then
   echo "Failed to parse arguments"
   exit 1
fi

eval set -- "$PARSED_OPTIONS"

# Loop through all of the options with a case statement
while true; do
   case "$1" in
      -h)
         HELP=1
         shift
         ;;

      -c)
         CONFIGURE_SSHD=1
         shift
         ;;

      -u)
         NON_ROOT_USER=$2
         shift 2
         ;;

      --)
         shift
         break
         ;;
   esac
done

if [ "$HELP" -eq 1 ];
then
   usage
   exit
fi

if [ "$NON_ROOT_USER" == "0" ];
then
  >&2 echo "You must provide a non-root user id, for one that exists or one to create"
  exit
fi

echo "Executing bootstrap; CONFIGURE_SSHD=$CONFIGURE_SSHD, NON_ROOT_USER=$NON_ROOT_USER"

# ##############################################################################

# Attempt to add the user to the system, if they do not already exist this will just fail without
# any negative effect.
useradd -m -s /bin/bash $NON_ROOT_USER

set -e

echo "adding a sudoer entry for non-root user; NON_ROOT_USER=$NON_ROOT_USER"
echo "$NON_ROOT_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$NON_ROOT_USER

if [ "$CONFIGURE_SSHD" -eq 1 ]
then
  echo "Configuring sshd for passwordless root logins"
  sed -i '/PermitRootLogin/d' /etc/ssh/sshd_config
  echo "PermitRootLogin yes" >> /etc/ssh/sshd_config
  systemctl restart sshd
fi

# Ensure that sshd is configured to allow password based logins
echo "Configuring sshd to enable password authenticated logins"
sed -i '/PasswordAuthentication/d' /etc/ssh/sshd_config
echo "PasswordAuthentication yes" >> /etc/ssh/sshd_config
systemctl restart sshd

apt-get update
apt-get install -y  \
  apt-transport-https \
  build-essential \
  curl \
  git \
  libbz2-dev \
  libffi-dev \
  libgdbm-dev \
  liblzma-dev \
  libncurses5-dev \
  libnss3-dev \
  libreadline-dev \
  libsqlite3-dev \
  libssl-dev \
  software-properties-common \
  vim \
  wget \
  zlib1g-dev

apt-get upgrade -y

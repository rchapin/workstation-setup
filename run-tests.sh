#!/bin/bash

###############################################################################
# Wrapper script for setting up and running integration tests
#
# name:     run-tests.sh
# author:   Ryan Chapin
#
################################################################################
# Source common variables/values
. ./ws_env_vars.sh

################################################################################
#
#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  export_env_vars
#   DESCRIPTION:  Will export all of the required environmental varibles to run
#                 the tests
#    PARAMETERS:  None
#       RETURNS:  void
#-------------------------------------------------------------------------------
function export_env_vars {
  set -e

  local override_env_vars=$1
  if [ "$override_env_vars" != "0" ]
  then
    if [ ! -f "$override_env_vars" ]
    then
      printf "ERROR! OVERRIDE_ENV_VARS_PATH, -e argument, pointed to a non-existant file\n\n" >&2
      usage
      #
      # We don't just exit here, because we may be sourcing this script and it would
      # then close the current terminal without giving the user an opportunity to
      # see the error message.  If we were not passed in a path to a valid file for
      # the required env vars, we just fall through and exit without doing anything
      # else.
      #
    fi
    echo "Sourcing required env vars script $OVERRIDE_ENV_VARS_PATH"
    source $OVERRIDE_ENV_VARS_PATH
  fi

  # ------------------------------------------------------------------------------
  # Sane defaults.  Can be overriden by first specifying the variable you want to
  # change as an environmental variable in the calling shell.

  export WS_SETUP_INTTEST_TEST_HOST=${WS_SETUP_INTTEST_TEST_HOST:-localhost}

  # Parent directory for all of the integration test files and directories
  export WS_SETUP_INTTEST_PARENT_DIR=${WS_SETUP_INTTEST_PARENT_DIR:-/var/tmp/workstation-setup-integration-test}
  export WS_SETUP_INTTEST_CONFIG_DIR=${WS_SETUP_INTTEST_CONFIG_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/config}
  export WS_SETUP_INTTEST_TEST_DATA_DIR=${WS_SETUP_INTTEST_TEST_DATA_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/test_data}
  export WS_SETUP_INTTEST_DOCKER_DIR=${WS_SETUP_INTTEST_DOCKER_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/docker}
  export WS_SETUP_INTTEST_SSH_IDENTITY_FILE=${WS_SETUP_INTTEST_SSH_IDENTITY_FILE:-$WS_SETUP_INTTEST_DOCKER_DIR/id_rsa}
  export WS_SETUP_INTTEST_SSH_IDENTITY_FILE_PUB=${WS_SETUP_INTTEST_SSH_IDENTITY_FILE_PUB:-${WS_SETUP_INTTEST_SSH_IDENTITY_FILE}.pub}
  export WS_SETUP_INTTEST_VIRTENV_DIR=${WS_SETUP_INTTEST_VIRTENV_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/virtenv}

  # For each of the distros that we are going to test we need to build a container of a known name
  # with a unique tag
  export WS_SETUP_INTTEST_CONTAINER_NAME_PREFIX=${WS_SETUP_INTTEST_CONTAINER_NAME_PREFIX:-workstationsetup_inttest}

  # For each of the distro containers that we will build and run for the integration tests we need
  # to define a separate port on which will will have docker map the ssh connections.
  export WS_SETUP_INTTEST_CONTAINER_START_PORT=${WS_SETUP_INTTEST_CONTAINER_START_PORT:-22222}

  # When we build each container we will export env vars that indicate the name of the container
  # and the expected port to use for each

  # It doesn't really matter what this password is. We just need something
  # with which we can ssh/rsync to the container to execute the tests
  export WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD=${WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD:-password123}
  export WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD_FILE=${WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD_FILE:-$WS_SETUP_INTTEST_PARENT_DIR/test-container-root-passwd.txt}

  # For each of the distros that we are testing we will build a docker image and for each need to
  # export an env var, the key is the name of the distro/container and the value is a tuple that
  # contains the image tag and the port that will be mapped to port 22 inside the container.
  export WS_SETUP_INTTEST_CONTAINER_NAME_PREFIX=${WS_SETUP_INTTEST_CONTAINER_NAME_PREFIX:-workstationsetup_inttest}

  # After creating the configs for each container we will use and then increment the start port for
  # its initialization step.
  local port=$WS_SETUP_INTTEST_CONTAINER_START_PORT

  for distro in `ls workstationsetup/integration_tests/docker/`
  do
    # Generate the tag, and the name of the image we will use for initialization
    distro_key=$(echo $distro | tr [:lower:] [:upper:])
    image_tag="${WS_SETUP_INTTEST_CONTAINER_NAME_PREFIX}_${distro}"
    image_name="${WS_SETUP_INTTEST_CONTAINER_NAME_PREFIX}_${distro}"

    # Generate the env var key
    key="WS_SETUP_INTTEST_CONTAINER_INSTANCE_${distro_key}"

    # Tuple of values to include the image tag and the port
    val="${image_tag}:${port}"
    declare -gx "$key"="$val"

    # Bump the port for the next image
    port=$((port+1))
  done

  set +e
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  which_linux_distro
#   DESCRIPTION:  Returns the enum/name of the linux distro on which we are
#                 running the tests
#-------------------------------------------------------------------------------
function which_linux_distro {
  local retval=""

  if [ -f "/etc/debian_version" ]; then
    retval="debian"
  fi
  # TODO add RHEL

  echo $retval
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  install_dependencies
#   DESCRIPTION:  Installs required packages to setup and run the tests.
#-------------------------------------------------------------------------------
function install_dependencies {
  distro=$(which_linux_distro)
  case $distro in

    debian)
      sudo apt-get install -y openssh-server netcat-traditional rsync sshpass
      ;;

    redhat)
      echo "redhat"
      ;;

    *)
      >&2 echo "Unknown distribution"
      ;;

  esac
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  build_docker_test_image
#   DESCRIPTION:  Builds the docker image which we will use to run the tests.
#-------------------------------------------------------------------------------
function build_docker_test_image {
  local start_dir=$(pwd)

  # Generate an ssh key to be added to the docker image when we build it.
  ssh-keygen -q -t rsa -N '' -f $WS_SETUP_INTTEST_SSH_IDENTITY_FILE <<<y 2>&1 >/dev/null

  # For each of the distros that we are testing we need to copy the docker file to the "build" dir
  # and build the docker image
  for distro in `ls workstationsetup/integration_tests/docker/`
  do
    # Copy to the Dockerfile and the bootstrap script to the build dir
    distro_docker_dir=$WS_SETUP_INTTEST_DOCKER_DIR/$distro
    mkdir -p $distro_docker_dir
    cp workstationsetup/integration_tests/docker/$distro/Dockerfile $distro_docker_dir
    cp bootstrap/bootstrap-${distro}.sh $distro_docker_dir

    # We also copy the install-python.sh script into the docker container to ensure that we can run
    # and validate it during the integration testing.
    cp install-python.sh $distro_docker_dir

    # Copy the public ssh key into the build dir
    cp $WS_SETUP_INTTEST_SSH_IDENTITY_FILE_PUB $distro_docker_dir
    cd $distro_docker_dir

    # Read the already exported env var by dynamically generate the env var for which we will be
    # accessing.
    distro_key=$(echo $distro | tr [:lower:] [:upper:])
    env_var_key="WS_SETUP_INTTEST_CONTAINER_INSTANCE_${distro_key}"
    OIFS="$IFS"
    IFS=':'
    # Access the env var with the dynamic variable expansion syntax ${!<name>}
    read -r image_tag port <<< "${!env_var_key}"
    IFS="$OIFS"

    docker build \
    --build-arg root_passwd=$WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD \
    --build-arg user=$USER \
    -t $image_tag .
    initialize_docker_container $image_name $image_tag $port

    cd $start_dir
  done

  # Write out the password to a text file
  echo "$WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD" > $WS_SETUP_INTTEST_CONTAINER_ROOT_PASSWD_FILE
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  initialize_docker_container
#   DESCRIPTION:  Start the docker container to setup the entries in the known
#                 host file.
#-------------------------------------------------------------------------------
function initialize_docker_container {
  local container_name=$1
  local container_tag=$2
  local container_port=$3

  configure_firewall $container_port

  # Fire up the docker container
  docker run --rm -d --name $container_name -p ${container_port}:22 $container_tag

  # Because we are likely going to run this multiple times and idempotency is
  # king, we want to ensure that we do not already have a set of keys for
  # this docker container.
  ssh-keygen -f "/home/rchapin/.ssh/known_hosts" -R "[localhost]:$container_port"

  # Set-up a retry loop that waits until we can establish a TCP connection to the specified port
  while true
  do
    nc -v -w 1 localhost $port
    if [ "$?" == "0" ]
    then
      break
    fi
    echo "Sleeping for 1 second to wait to connect; port=$port"
    sleep 1
  done

  # ssh to the docker container automatically accepting the host keys and then stop it
  ssh -p $container_port -i $WS_SETUP_INTTEST_SSH_IDENTITY_FILE -o StrictHostKeyChecking=no root@localhost hostname
  docker stop $container_name
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  configure_firewall
#   DESCRIPTION:  Configures the firewall on the test machine if it is already
#                 installed and enabled.  If not, it is a noop.
#-------------------------------------------------------------------------------
function configure_firewall {
  local port=$1
  distro=$(which_linux_distro)
  case $distro in

    debian)
      if dpkg --get-selections | grep ufw 2>&1 > /dev/null
      then
        # Check to see if it is active
        if ! ssh root@localhost ufw status | grep inactive > /dev/null
        then
          echo "Adding $port to ufw firewall"
          ssh root@localhost ufw allow ${port}/tcp
        fi
      fi
      ;;

    redhat)
      echo "redhat"
      ;;

    *)
      >&2 echo "Unknown distribution"
      ;;

  esac
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  create_virtenv
#   DESCRIPTION:  Create the virtual environment and install the application.
#-------------------------------------------------------------------------------
function create_virtenv {
  $(which $PYTHON) -mvenv $WS_SETUP_INTTEST_VIRTENV_DIR
  source $WS_SETUP_INTTEST_VIRTENV_DIR/bin/activate
  pip install -U setuptools pip coverage
  pip install -r requirements.txt
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  setup
#   DESCRIPTION:  Cleans and creates the required test dirs based on the env
#                 vars already defined.
#-------------------------------------------------------------------------------
function setup {
  # First run teardown to remove anything left behind
  teardown

  echo "Setting up test environment"
  # Now create the directory structure needed for the tests.
  dirs=(
    "$WS_SETUP_INTTEST_PARENT_DIR"
    "$WS_SETUP_INTTEST_CONFIG_DIR"
    "$WS_SETUP_INTTEST_DOCKER_DIR"
  )
  for dir in "${dirs[@]}"
  do
    mkdir -p $dir
  done

  install_dependencies
  build_docker_test_image
  create_virtenv
  echo "Test environment setup complete"
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  teardown
#   DESCRIPTION:  Cleans up the required test dirs based on the env vars already
#                 defined.
#-------------------------------------------------------------------------------
function teardown {
  echo "Tearing down test environment"
  echo "Deleting test dirs"
  rm -rf $WS_SETUP_INTTEST_PARENT_DIR

  # # It is possible that there is no container or images in existence, but we will stop any running
  # # container and delete the image to ensure a clean slate.
  # echo "Stopping docker container and deleting test image"
  # set +e
  # docker stop $WS_SETUP_INTTEST_CONTAINER_NAME 2> /dev/null
  # docker rmi $WS_SETUP_INTTEST_IMAGE_NAME 2> /dev/null
  # set -e

  echo "Test environment clean-up complete"
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  run_tests
#   DESCRIPTION:  Runs both the unit and integration tests.
#    PARAMETERS:  None
#       RETURNS:  void
#-------------------------------------------------------------------------------
function run_tests {
  set -e
  source $WS_SETUP_INTTEST_VIRTENV_DIR/bin/activate

  # FIXME:  This needs to get sorted out better.  Right now to avoid having to specify the distro on
  # each call we are using an env var.  I don't think that is going to work because there are more than
  # a few places, this included, that we have to define one so that we don't throw an exception that it
  # is missing.  Once we figure that out, we can remove this.
  export WS_SETUP_DISTRO=debian_11

  # Run the unit tests
  echo "======================================================================="
  echo "Running the unit tests"
  coverage run -m unittest discover -s workstationsetup/tests # add -k $test_name

  if [ "$OMIT_INTEGRATION_TESTS" -ne 1 ]
  then
    echo "======================================================================="
    echo "Running the integration tests"
    coverage run --append -m unittest discover -s workstationsetup/integration_tests --failfast # add -k $test_name
  fi

  coverage report workstationsetup/*.py
  set +e
}

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

  -e OVERRIDE_ENV_VARS_PATH
     Path to the file that contains the any overriding env vars.

  -i OMIT_INTEGRATION_TESTS
     Ommit running the integration tests and just run the unit tests.

  -l LEAVE
     Do not clean any existing environment previously setup.  By default the
     environment is cleaned and re-installed with each invocation of this
     script.

  -t TEARDOWN
     Teardown the test environment on the configured test host

  --setup-only Only run the setup without running the tests.

  --export-env-vars-only
    Only export the require environmental variables for the test, overriding
    the defaults with those env vars defined in the -e file, but do not run the
    test.  To achieve this goal, you must source this script instead of running
    it as an executable script.

    Example:

    $ source ./run-tests.sh -e /path/to/required-env-vars.sh --export-env-vars-only

    Alternatively, you can omit the -e arg to use the defaults.

  -h HELP
     Outputs this basic usage information.
EOF
}

################################################################################
#
# Here we define variables to store the input from the command line arguments as
# well as define the default values.
#
HELP=0
LEAVE=0
TEARDOWN=0
TEARDOWN_ONLY=0
SETUP_ONLY=0
EXPORT_ENV_VARS_ONLY=0
OVERRIDE_ENV_VARS_PATH=0
OMIT_INTEGRATION_TESTS=0

PARSED_OPTIONS=`getopt -o hltie: -l export-env-vars-only,setup-only,teardown-only -- "$@"`

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

      -e)
         OVERRIDE_ENV_VARS_PATH=$2
         shift 2
         ;;

      -i)
         OMIT_INTEGRATION_TESTS=1
         shift
         ;;

      -l)
         LEAVE=1
         shift
         ;;

      -t)
         TEARDOWN=1
         shift
         ;;

      --export-env-vars-only)
         EXPORT_ENV_VARS_ONLY=1
         shift
         ;;

      --setup-only)
         SETUP_ONLY=1
         shift
         ;;

      --teardown-only)
         TEARDOWN_ONLY=1
         shift
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

################################################################################

export_env_vars $OVERRIDE_ENV_VARS_PATH
run_script_dir=$(cd $(dirname $0) && pwd)

if [ "$EXPORT_ENV_VARS_ONLY" -eq 1 ]
then
  #
  # Check to make sure that the user actually sourced this script otherwise we
  # can give them a warning so that they won't be confused when they do not
  # see any of the expected env vars.
  #
  current_dirname=`dirname "$0"`
  if [[ "$current_dirname" != *"/bin"* ]]
  then
    cat << EOF

!!!!! WARNING !!!!!
You are trying to just export the env vars, however, it seems as though you did not source this script, but were attempting to execute it.
EOF
    usage
  fi

else
  #
  # If we are to do more than export env vars, continue processing
  #
  if [ "$TEARDOWN_ONLY" -eq 1 ]
  then
    teardown
    exit
  fi

  if [ "$SETUP_ONLY" -eq 1 ]
  then
    setup
    exit
  fi

  if [ "$LEAVE" -eq 0 ]
  then
    # We are to run setup which will clean any existing test environment
    setup
  fi

  time run_tests

  if [ "$TEARDOWN" -eq 1 ]
  then
    #
    # We should teardown the test setup environment
    #
    teardown
  fi
fi


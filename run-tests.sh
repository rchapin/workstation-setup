#!/bin/bash

###############################################################################
# Wrapper script for setting up and running integration tests
#
# name:     run-tests
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
  export WS_SETUP_INTTEST_TEST_USER=${WS_SETUP_INTTEST_TEST_USER:-$USER}

  # Parent directory for all of the integration test files and directories
  export WS_SETUP_INTTEST_PARENT_DIR=${WS_SETUP_INTTEST_PARENT_DIR:-/var/tmp/workstation-setup-integration-test}
  export WS_SETUP_INTTEST_CONFIG_DIR=${WS_SETUP_INTTEST_CONFIG_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/config}
  export WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_DIR=${WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/pydeploy-configs}
  export WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_REFSPEC=${WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_REFSPEC:-main}
  export WS_SETUP_INTTEST_VAGRANT_DIR=${WS_SETUP_INTTEST_VAGRANT_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/vagrant}
  export WS_SETUP_INTTEST_SSH_IDENTITY_FILE=${WS_SETUP_INTTEST_SSH_IDENTITY_FILE:-$WS_SETUP_INTTEST_VAGRANT_DIR/id_rsa}
  export WS_SETUP_INTTEST_SSH_IDENTITY_FILE_PUB=${WS_SETUP_INTTEST_SSH_IDENTITY_FILE_PUB:-${WS_SETUP_INTTEST_SSH_IDENTITY_FILE}.pub}
  export WS_SETUP_INTTEST_VIRTENV_DIR=${WS_SETUP_INTTEST_VIRTENV_DIR:-$WS_SETUP_INTTEST_PARENT_DIR/virtenv}

  # For each of the distro boxes that we will build and run for the integration tests we need to
  # define a separate port on which will map the ssh connections.
  export WS_SETUP_INTTEST_VAGRANT_BOX_START_PORT=${WS_SETUP_INTTEST_VAGRANT_BOX_START_PORT:-22222}

  # When we build each container we will export env vars that indicate the name of the container
  # and the expected port to use for each

  # It doesn't really matter what this password is. We just need something
  # with which we can ssh/rsync to the container to execute the tests
  export WS_SETUP_INTTEST_VAGRANT_BOX_ROOT_PASSWD=${WS_SETUP_INTTEST_VAGRANT_BOX_ROOT_PASSWD:-password123}
  export WS_SETUP_INTTEST_VAGRANT_BOX_ROOT_PASSWD_FILE=${WS_SETUP_INTTEST_VAGRANT_BOX_ROOT_PASSWD_FILE:-$WS_SETUP_INTTEST_PARENT_DIR/test-container-root-passwd.txt}

  # Whether or not we are going to reuse vagrant boxes between test runs.  By default this is false.
  # The only use-case for this is when you are actually developing new tasks and do not want to spin
  # up the box between test runs.
  export WS_SETUP_INTTEST_VAGRANT_BOX_REUSE=${WS_SETUP_INTTEST_VAGRANT_BOX_REUSE:-False}

  # For each of the distros that we are testing we will create a vagrant box and for each need to
  # export an env var, the key is the name of the distro directory and the value is
  # a tuple which is the name of the box to be created and the the port that will be
  # mapped to port 22 inside the container. After creating the configs for each container we will
  # use and then increment the start port for its initialization step.
  local port=$WS_SETUP_INTTEST_VAGRANT_BOX_START_PORT

  for distro in `ls workstationsetup/integration_tests/vagrant/`
  do
    # Generate the name of the env var key for this box.
    distro_key=$(echo $distro | tr [:lower:] [:upper:])
    box_name=$distro

    # Generate the env var key
    key="WS_SETUP_INTTEST_VAGRANT_BOX_INSTANCE_${distro_key}"

    # Tuple of values to include the image tag and the port
    val="${box_name}:${port}"
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

  # TODO: add installation of virtual box
  # https://linuxiac.com/how-to-install-virtualbox-on-debian-11-bullseye/

  case $distro in

    debian)
      sudo apt-get install -y openssh-server packer netcat-traditional sshpass vagrant apt-transport-https ca-certificates gnupg
      ;;

    redhat)
      # TODO
      echo "redhat"
      ;;

    *)
      >&2 echo "Unknown distribution"
      ;;

  esac
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  setup_vagrant_boxes
#   DESCRIPTION:  Builds and configures the vagrant boxes with which we will use
#                 to run the tests.
#-------------------------------------------------------------------------------
function setup_vagrant_boxes {
  local start_dir=$(pwd)

  # Generate an ssh key to be added to the box when we build it.
  ssh-keygen -q -t rsa -N '' -f $WS_SETUP_INTTEST_SSH_IDENTITY_FILE <<<y 2>&1 >/dev/null

  # For each of the distros that we are testing we need to copy the Vagrant file and its configs to
  # the "build" dir and build VM and then package the box.
  local repo_vagrant_dir="workstationsetup/integration_tests/vagrant"
  for distro in `ls $repo_vagrant_dir`
  do
    distro_vagrant_dir=$WS_SETUP_INTTEST_VAGRANT_DIR/$distro

    # Copy the vagrant dir and the required files that we will use to build the box
    cp -Rpf $repo_vagrant_dir/$distro $WS_SETUP_INTTEST_VAGRANT_DIR/

    # Copy the public ssh key into the build dir
    cp $WS_SETUP_INTTEST_SSH_IDENTITY_FILE_PUB $distro_vagrant_dir

    # Read the already exported env var by dynamically generating the env var that we will read.
    distro_key=$(echo $distro | tr [:lower:] [:upper:])
    env_var_key="WS_SETUP_INTTEST_VAGRANT_BOX_INSTANCE_${distro_key}"
    OIFS="$IFS"
    IFS=':'
    # Access the env var with the dynamic variable expansion syntax ${!<name>}
    read -r box_name port <<< "${!env_var_key}"
    IFS="$OIFS"

    echo "Building Vagrant box; start_dir=$start_dir, build_vagrant_dir=$distro_vagrant_dir, box_name=$box_name, port=$port"
    box_path=$(build_vagrant_box $start_dir $distro_vagrant_dir $box_name $port)

    echo "Initializing Vagrant box; start_dir=$start_dir, build_vagrant_dir=$distro_vagrant_dir, box_name=$box_name, port=$port, box_path=$box_path"
    initialize_vagrant_box $start_dir $distro_vagrant_dir $box_name $port $box_path

  done

  # Write out the password to a text file
  echo "$WS_SETUP_INTTEST_VAGRANT_BOX_ROOT_PASSWD" > $WS_SETUP_INTTEST_VAGRANT_BOX_ROOT_PASSWD_FILE
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  build_vagrant_box
#   DESCRIPTION:  Build the vagrant box based on the provided packer file
#        RETURN:  The path to the newly built box file
#-------------------------------------------------------------------------------
function build_vagrant_box {
  local start_dir=$1
  local build_vagrant_dir=$2
  local box_name=$3
  local port=$4

  cd $build_vagrant_dir
  packer_file=${box_name}.pkr.hcl
  packer build $packer_file 1>&2

  cd $start_dir
  echo "$build_vagrant_dir/output-${box_name}/package.box"
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  initialize_vagrant_box
#   DESCRIPTION:
#-------------------------------------------------------------------------------
function initialize_vagrant_box {
  local start_dir=$1
  local build_vagrant_dir=$2
  local box_name=$3
  local box_port=$4
  local box_path=$5

  cd $build_vagrant_dir

  # Create an instance of the box
  vagrant init $box_name
  vagrant box add --force $box_name $box_path

  # Update the Vagrant file configs to add the proper forwarded port
  sed -i '/^end/d' Vagrantfile
  # TODO, clean this up with a heredoc
  echo "  config.vm.network \"forwarded_port\", guest: 22, host: $box_port" >> Vagrantfile
  echo "  config.vm.provider \"virtualbox\" do |v|" >> Vagrantfile
  echo "    v.memory = 2816" >> Vagrantfile
  echo "  end" >> Vagrantfile
  echo "end" >> Vagrantfile

  # Because we are likely going to run this multiple times and idempotency is king, we want to
  # ensure that we do not already have a set of keys for this docker box.
  ssh-keygen -f "/home/rchapin/.ssh/known_hosts" -R "[localhost]:$box_port"

  vagrant up

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

  # ssh to the vm automatically accepting the host keys and then stop it
  ssh -p $box_port -i $WS_SETUP_INTTEST_SSH_IDENTITY_FILE -o StrictHostKeyChecking=no root@localhost hostname
  vagrant halt

  # Configure the firewall on the test machine to enable connections to this forwarded port
  configure_firewall $box_port

  cd $start_dir
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
  pip install -r requirements_test-dev.txt
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  create_pytest_ini
#   DESCRIPTION:  Create the pytest.ini file required for running tests via VSCode
#-------------------------------------------------------------------------------
function create_pytest_ini {
  OUTFILE=pytest.ini
  cat << EOF > $OUTFILE
[pytest]
log_cli = 1
log_cli_level = INFO
log_cli_format = %(asctime)s,%(levelname)s,%(module)s:%(lineno)s,%(message)s
log_cli_date_format=%Y-%m-%d %H:%M:%S
env =
EOF
  env | grep WS_ | sort | sed 's/^/    /' >> $OUTFILE
}

#---  FUNCTION  ----------------------------------------------------------------
#          NAME:  clone_pydeploy_configs_repo
#   DESCRIPTION:  Clones the pydeploy-configs repo
#-------------------------------------------------------------------------------
function clone_pydeploy_configs_repo {
  # Ensure that the target repo dir does not already exist
  rm -rf $WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_DIR
  git clone https://github.com/rchapin/pydeploy-configs.git $WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_DIR
  start_dir=$(pwd)
  cd $WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_DIR && git checkout $WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_REFSPEC
  cd $start_dir
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
    "$WS_SETUP_INTTEST_VAGRANT_DIR"
  )
  for dir in "${dirs[@]}"
  do
    mkdir -p $dir
  done

  create_pytest_ini
  install_dependencies
  clone_pydeploy_configs_repo
  setup_vagrant_boxes
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

  # TODO: figure out if we can clean-up any vagrant vms
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

  coverage report -m --omit *__init__*,workstationsetup/tests/*.py,workstationsetup/integration_tests/*.py
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
     script and then torn down after the test completes.

  --setup-only Only run the setup without running the tests.

  --export-env-vars-only
    Only export the require environmental variables for the test, overriding
    the defaults with those env vars defined in the -e file, but do not run the
    test.  To achieve this goal, you must source this script instead of running
    it as an executable script.

  --teardown-only
    Only tear down the test environment.  Do not exectute any setup or run any
    of the tests.

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
TEARDOWN_ONLY=0
SETUP_ONLY=0
EXPORT_ENV_VARS_ONLY=0
OVERRIDE_ENV_VARS_PATH=0
OMIT_INTEGRATION_TESTS=0

PARSED_OPTIONS=`getopt -o hlie: -l export-env-vars-only,setup-only,teardown-only -- "$@"`

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

if [ "$HELP" -eq 1 ]
then
   usage
   exit
fi

if [ "$LEAVE" -eq 1 ]
then
  # Ensure that we pass through the intention to leave the test scaffolding in place to the test
  # code itself.
  export WS_SETUP_INTTEST_VAGRANT_BOX_REUSE=True
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
  # If we are to do more than export env vars, continue processing.
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
    # We are to run setup which will clean any existing test environment.
    setup
  fi

  time run_tests

  if [ "$LEAVE" -eq 0 ]
  then
    # We should not leave the test environment and should tear it down.
    teardown
  fi
fi

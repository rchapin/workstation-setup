# Workstation Setup

The following is a Python `invoke` and `fabric 2.x` based project for automatically configuring a Debian 11 Linux workstation for "on-prem", bare-metal hosts or VMs.
> It can be fairly easily extended for RedHat based, or any other Linux distro.  If someone is interested and wants to collaborate with me on it, just [get in touch with me](https://www.linkedin.com/in/ryanchapin/).

Part of the impetus for this project was that I wanted to come up with a solution to a couple of problems that I had encountered building similar deployment automation applications.

1. **Make the code distribution agnostic**, or at least provide a framework for abstracting operations that were not distro specific and provide the ability to properly encapsulate distro specific commands.

2. **Make it testable** and develop a framework for integration testing deployment automation tasks.  Because this is (headed in the direction of) a bare-metal deployment framework and requires interactions with a complete computer and not just a container I opted for using Vagrant to orchestrate VirtualBox VMs.

The following is a how-to and a set of automated tools for setting up a Linux, developer workstation.

- [Usage](#usage)
- [Task List](#task-list)
- [Developing and Debugging](#developing-and-debugging)
- [Using on a Linux VM on a Windows 11 Host](#using-on-a-linux-vm-on-a-windows-11-host)

## Usage

At a high level, the way it works is:
1. Create a config file that defines
    1. The Linux distro and version
    1. The Window Manager
1. Clone the default set of configs from the [PyDeploy Configs](https://github.com/rchapin/pydeploy-configs) repo
1. Run the program, pointing to the config file and the PyDeploy Configs directory specifying the task that you want to execute and the program will execute the configuration commands over an SSH connection to the host in question.
### Setup

> The following is analgous to setting up a **deployment server** from which you would manage a set of on-prem servers.  In this case, since you are only setting up a workstation, we will setup the deployment tools on the same machine that we are configuring.

1. Copy the bootstrap script from this repo to the host that you want to setup and run it as `root`, passing it the name of the non-root user that you want created on the workstation.  If the user already exists, this is a noop.  The bootstrap script will
    - create the non-root user if it does not yet exist
    - add your user name to sudoers
    - configure sshd to allow root logins
    - install a base set of packages
    ```
    ./bootstrap-xfce4_debian_11.sh -c -u <your-user-name>
    ```
1. Set a password for your non-root user and then logout as root
1. Login to the workstation as the your non-root user and create directories and export environment variables
    ```
    mkdir -p ~/Documents/workspace && export REPO_DIR=~/Documents/workspace && cd $REPO_DIR
    ```
1. Clone the PyDeploy Config repo and the Workstation Setup repo to the workstation
    ```
    git clone https://github.com/rchapin/pydeploy-configs.git && git clone https://github.com/rchapin/workstation-setup.git
    ```
1. Change directories into the top level directory of the cloned `workstation-setup` repo
    ```
    cd $REPO_DIR/workstation-setup
    ```
1. Run the `install-python.sh` script (as the non-root user) to install and compile the current version of 3.10.x into your home directory.
1. Add the following to your `~/.bashrc` to add python3.10 to your `PATH`
    ```
    cat << EOF >> ~/.bashrc
    PYTHON_HOME=~/usr/local/python-3.10.8
    export PATH=\$PATH:\$PYTHON_HOME/bin
    EOF
    ```
1. Source the `setup.sh` script to setup a Python virtual environment.  It will automatically clean and setup a virtual environment.  This virtual environment will enable you to run the `workstationsetup` tasks to setup your workstation.
    ```
    . ./setup.sh
    ```
1. Create a set of passphrase-less SSH keys for your non-root user and then setup password-less SSH connections to `root@localhost` on the workstation to enable execution of the deployment tasks
    ```
    ssh-keygen && ssh-copy-id root@localhost
    ```
1. Create a `yaml` config file that tells the `workstationsetup` program which Linux distro and window manager you are using on the host that you want to configure.
    ```
    cat << EOF >> /var/tmp/ws-setup.yaml
    distro:
        name: debian
        version: '11'
        window_manager: xfce4

    # Optional, overriding task configs.  See
    # task_configs:
    #     install-maven:
    #     version:
    #         mode: OVERRIDE
    #         value: 3.6.3
    #     install-packages:
    #         packages:
    #             mode: APPEND
    #             value:
    #                 - remmina
    #                 - hp-ppd
    #                 - hplip
    #                 - hplip-gui
    EOF
    ```
1. Export environment variables pointing to the config file and the PyDeploy Config repo
    ```
    export WS_CONF=/var/tmp/ws-setup.yaml && export PYDEPLOY_CONF=$REPO_DIR/pydeploy-configs
    ```

### Workstation Setup

Once you have gone through the [setup](#setup) steps you can run the `workstation-setup` tasks to configure your workstation.
> All of the tasks are idempotent so it does not matter how many times you run them.

Run `workstationsetup` to see all of the available tasks.  To see details for any given task run the following
```
workstationsetup -h <task>
```

#### Required and Optional Arguments
```
--hosts[=STRING] - CSV of host names against which to run the specified task

-u [STRING], --hosts-connection-user[=STRING] - The username for the fabric/ssh connections for the hosts on which we will run the tasks, default=root

-c STRING, --config-path=STRING - Fully qualified path to the PyDeploy config yaml file

--pydeploy-config-dir[=STRING] - Fully qualified path to the PyDeploy base config directory. You should clone this directory prior to running these tasks.

--ssh-identity-file[=STRING] - The ssh identity file to use for connecting to hosts for deployment operations

--ssh-port[=INT] - The ssh port to use for connecting to hosts for deployment operations

-r, --requests-disable-warnings - Configure the requests lib such that it will disable SSL warnings, default=False
```

#### Running Tasks

To run a task execute it with the following arguments
```
workstationsetup --pydeploy-config-dir $PYDEPLOY_CONF --config-path $WS_CONF --hosts localhost <task> [task-args]
```

**Run the `install-packages` task first** as most of the other tasks require a base set of packages already installed.  Once that task has been executed you can run any of the other tasks in whatever order that you would like.
```
workstationsetup --pydeploy-config-dir $PYDEPLOY_CONF --config-path $WS_CONF --hosts=localhost <task> [task-args]
```

From there, any of the other tasks can be run to setup your workstation.  The full list is as follows:
##### Task List
```
configure-git                           Configures git for the given user with the provided user information.
install-cert                            Installs an additional ca cert, in PEM format, into the os ca certificates bundle.
install-cert-into-jvm                   Installs the provided CA cert, in pem format, into the jvm for which java-alternatives is currently configured.
install-chrome                          Installs the Google Chrome browser.
install-docker                          Installs docker and docker-compose, and adds the provided user to the docker group.
install-drawio                          Installs the Drawio desktop application.
install-google-cloud-cli                Installs the google-cloud-cli program suite.
install-gradle                          Install the gradle build tool.
install-helm                            Install the helm client.
install-intellij                        Install the IntelliJ community addition IDE.
install-java-adoptium-eclipse-temurin   Installs the Adoptium OpenJDK package.
install-java-openjdk                    Installs Oracle’s free, GPL-licensed, production-ready OpenJDK package.
install-maven                           Installs the Apache Maven build tool.
install-minikube                        Installs Minikube; a lightweight Kubernetes implementation that creates a K8s cluster on a VM on your local machine.
install-packages                        Installs the base set of packages.
install-pgadmin                         Installs PostgreSQL pgAdmin
install-redshift                        Installs redshift, the configs, and the user-level systemd configurations
install-slack                           Installs the Slack clent.
install-zoom                            Installs the Zoom client.
install-vscode                          Installs the Visual Studio Code IDE.
print-feedback                          A utility task to print all collected feedback during an invocation.  Running this task directly will have no result.
setup-inotify                           Increase the maximum user file watches for inotify.
```
### Overriding and Extending PyDeploy Configurations

The PyDeploy Configs repo defines a default set of configurations for all of the deployment tasks on a per distro basis.

These configurations can be overridden or extended based on the type of configuration that is being mutated.

Each task has a top-level config black that is the exact same name as the task evoked on the command-line.  The `install-docker` task has a `install-docker` top-level config entry in the PyDeploy Configs yaml file.

Config keys that have a single value can be overridden and configs keys with list values can either be overridden or extended.

An example config file:
```
task_configs:
    # Indicate that we want to override the install-maven configs in
    # the PyDeploy Config file
    install-maven:

        # Indicate which of the config elements of the install-maven
        # config we want to override
        version:

            # Indicate the mode [OVERRIDE|APPEND]
            # OVERRIDE will completely replace the targeted config
            mode: OVERRIDE

            # Define the value that we want to use to override the
            # install-maven.version config
            value: 3.6.3

    # Indicate that we want to override the install-packages configs in
    # the PyDeploy Config file
    install-packages:

        # Indicate which of the config elements of the install-maven
        # config we want to override
        packages:

            # Indicate the mode [OVERRIDE|APPEND]
            # APPEND will add any elements defined here to the existing
            # list of configuration elements.
            mode: APPEND

            # Define a list of elements that we want appended to the
            # install-packages.packages configuration list.
            value:
                - remmina
                - hp-ppd
                - hplip
                - hplip-gui
```

## Developing and Debugging

> Currently all of the scaffolding is not completely automated.  You will need to install `virtualbox 6.1` or greater to run the tests

### Running the Tests

All of the unit and integration tests can be run by executing the `run-test.sh` script at the root of the repository.

> If you are running the tests against a `pydeploy` development branch ensure that you first export the following environment variable
```
export WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_REFSPEC=<refspec>
```


#### Debugging Task Execution


Use the following sample launch config to run and debug tasks in VSCode
```
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "invoke",
      "type": "python",
      "request": "launch",
      // The complete path to the invoke python script in your virtual environment
      "program": "/my/virtualenv/path/bin/invoke",
      "justMyCode": false,
      // The args that you would otherwise enter on the command line
      // when invoking your task
      "args": [
        "do-something",
        "--some-path",
        "/var/tmp/a/",
        "--some-other-path",
        "/var/tmp/b/"
      ],
      "cwd": "/the/path/to/the/dir/that/contains/your/tasks/script",
    }
  ]
}
```

## Developing and Debugging in VSCode

1. Run the following to setup the integration test scaffolding.  This will create temp directories and build the Vagrant boxes needed for the tests.
    ```
    ./run-tests.sh --setup-only
    ```

    The setup will also create a `pytest.ini` file at the root of the repository that VSCode will read in and set required environment variables to run the tests in the IDE.

1. If you are working with a PyDeploy Configs branch other than `main` branch, edit the `pytest.ini` file and set the `WS_SETUP_INTTEST_PYDEPLOY_CONFIGS_REPO_REFSPEC` environment variable to the refspec for the branch that you want to use for your tests.
1. In order to reduce the cycle time when running the integration tests to a minimum, set `WS_SETUP_INTTEST_VAGRANT_BOX_REUSE=True` in `pytest.ini`.  This will keep the vagrant test vm running between tests.
1. There is already a `.vscode/settings.json` file in the repo with the base configs required.
1. Discover the test by pressing `CTRL+SHIFT+P` and type **Python: Configure Tests**
1. Select the workspace/project and then select **pytest pytest framework**
1. Then select the directory that contains the tests, `workstationsetup`, and it will discover all of the tests. **NOTE** if it is unable to discover the tests check the **OUTPUT** console and select **Python** from the drop-down tab to see the details of any errors.
1. Once that completes you will be able to run any of the tests discovered under the `Testing` side-bar.

> If you are also making changes to the `pydeploy` repo you will need to make sure that you push your changes to the `pydeploy` branch and pull them in the integration test directory where `pydeploy` is cloned unless you are doing a complete teardown with each run iteration while developing which is not recommended.

### Running and Debugging Tasks from VSCode

If you want to run and debug the task (not running it via an integration test) do the following:

1. In the virtual environment that you are using for development pip install the project.  Change directories to the root of the repository and run the following
    ```
    pip install -e .
    ```
1. Create a base config file in /var/tmp/ws-setup.yaml
    ```
    cat << EOF >> /var/tmp/ws-setup.yaml
    distro:
        name: debian
        version: '11'
        window_manager: xfce4
    EOF
    ```
1. Add the following entry to your launch.json `configurations`
    ```
    {
      "name": "inotify",
      "type": "python",
      "request": "launch",
      "program": "<path-to-your-home-dir>/.virtualenvs/workstation-setup/bin/workstationsetup",
      "console": "integratedTerminal",
      "justMyCode": false,
      "cwd": "<path-to-your-repo-dir>/workstation-setup",
      "args": [
        "--pydeploy-config-dir",
        "<path-to-your-repo-dir>/workspace/pydeploy-configs",
        "--config-path",
        "/var/tmp/ws-setup.yaml",
        "--hosts",
        "localhost",
        "<task-name>",
        "--optional-arg-name",
        "<optional-arg-val>"
      ],
    },
    ```
    Where `<task-name>` is the task you want to execute.  If the task required any arguments, add them as additional elements to the `args` key in the launch config.
## Using on a Linux VM on a Windows 11 Host

### VM Setup

The following are directions for setting up a VMWare VM on a Windows 11 host.

#### Create the VM

The following are instructions for setting up your VM on a Windows 11 host running on an x86_64 architecture.

1. **Setup your host OS**
    1. You will likely have virtualization enabled in your BIOS settings.  If not boot to your bios and enable the setting(s).  It will likely be one or both of the following, your settings may vary depending on your hardware.
        1. Virtualization Technology (VTx)
        1. Virtualization Technology for Directed I/O (VTd)
1. **Configurations for running minikube/nested VMs**:  If you want to install minikube you must ensure that Windows Hyper-V and a memory configuration are disabled.  If you make changes you will need to restart your machine.
    1. **Disable Hyper-V**
        1. Open the `Control Panel` and search for "program"
        1. Click on **Turn Windows features on or off** which will open another modal
        1. Ensure that **Hyper-V** and all of its child check-boxes are de-selected
        1. Ensure that **Virtual Machine Platform** is deselected
    1. **Disable Core Isolation/Memory integrity**
        1. Open Settings and click on **Privacy & Security** in the left-hand nav
        1. Click on **Windows Security**
        1. Click on **Device Security**
        1. Click on **Core isolation details** under the **Core isolation** heading
        1. Toggle the **Memory integrity** setting to **Off** and restart your machine
1. Install VMWare and download an iso for the distro of your choice
1. Create a VM with the following settings:
    1. Hardware:
        1. Memory: As much as your machine can spare
        1. Processors:
            1. Number of processors: As much as your machine can spare
            1. Virtualization engine (if you want to run minikube): Select **Virtualize Intel VT-x/EPT or AMD-V/RVI**
        1. Network Adapter: NAT
        1. Display:
            1. 3D graphics: Check **Accelerate 3D graphics**
            1. Monitors: Select **Use host settings for monitors**
            1. Graphics memory:  Max setting: 8GB
            1. Display scaling: Uncheck
    1. VMware Tools:
        1. VMWare Tools features:
            1. Synchronize guest time with host: check
        1. VMWare Tools updates:
            1. Use application default
    1. Disable side channel mitigations for Hyper-V enabled hosts by going to Virtual Machine Settings/Options/Advanced and then check the disable "side channel mitigations" checkbox.
1. Decide on the size of the virtual disck and create it.  I used the "giant file" instead of splitting up the disk into smaller chunks.
1. Disk Partitioning: Following is a suggested LVM partitioning setup
    1. swap: 8GB
    1. /boot: (default) ~500MB ext2
    1. /: 75GB ext4
    1. /var: 200GB ext4
    1. /home: remainder ext4
1. VMWare networking configurations: NAT
1. Install your operating system
1. Copy the bootstrap.sh script from the


#### Shared Folders Configuration

If you would like to setup shared folders first add the shared folder via the VirtuaBox VM configuration settings.

`vmhgfs-fuse`, depending on how it is invoked, will automatically map any shares defined as mountpoints under a specified directory.  For example:  If you configured two shares

- `C:\Users\rchapin\Documents` as Documents
- `D:\` as Data

Then create a mount point and mount an alias to all of the shares defined for the host as follows:

```
mkdir -p ~/shares
/usr/bin/vmhgfs-fuse .host:/ /home/<your-uid>/shares -o subtype=vmhgfs-fuse,allow_other -o uid=1000 -o gid=1000
```

(Assuming your uid and gid are 1000) the aforementioned command will create the following mount points
```
/home/<your-uid>/shares/Documents
/home/<your-uid>/shares/Data
```

To make this persistent, add the following to `/etc/fstab`.  This method will mount all of the shares advertized on the host as a "remote" file system mount.  This assumes your uid is `jdoe`, uid and gid ids are `1000`, and that you already have a directory created that is `~/shares` for your user.
```
# <server>:</remote/export> </local/directory> <fuse-type> <options> <dump> <pass>
host:/ /home/jdoe/shares  fuse.vmhgfs-fuse  defaults,allow_other,uid=1000,gid=1000  0  0
```


## Optional Configurations

### IntelliJ Setup

There is a task that will enable you to install and configure IntelliJ, if that is your IDE of choice.

### Additional Extensions

#### IdeaVim
If you install this extension you will want to create a `~/.ideavimrc` file with the following contents turn turn off the vim bell.
```
set visualbell
set noerrorbells
```

Update the VIM shortcuts as follows by going to Settings/Editor/VIM
- CTRL+H: set Handler to IDE

### Google Chrome

If you choose to run the `install-chrome` task and you need to use a custom CA cert you will need to add the CA cert to chrome.

> NOTE: Do this before signing in and syncing to Google account

1. Go to Settings in the top-right (three vertical dots)
1. Search for "Privacy" and click on the **Security** section
1. Scroll down to **Manage Certificates**
1. Click on the **Authorities** tab and then click the **Import** button
1. Import the pem file and click the checkboxes for
  - Trust this certificate for identifying websites
  - Trust this certificate for identifying email users
  - Trust this certificate for identifying software makers

## VSCode Setup

You may will need to turn off a VPN to be able to install Extensions.

Extensions:
- Eclipse Keymap
- Python (by Microsoft)
- Vim (by vscodevim)
- Extension Pack for Java
- Debugger for Java
- Git Lens
- Git Graph
- Gradle for Java
- HashiCorp HCL
- HCL Format
- Spring Boot Extension Pack
- Spring Boot Tools
- Spring Initializer
- Spring Boot Dashboard
- Go (by Go Team at Google)
- Rewrap (by stkb)

### General Configs

For most of the following this requires opening the settings by typing `[CTRL+,]`.

1. View Whitespace: Settings and search for "whitespace".  Select your choice from the **Editor: Render Whitespace** dropdown.
1. Autosave: Settings and search for "auto save".  for **Files: Auto Save** select **afterDelay** and then set your desired **Files: Auto Save Delay** time.

### Python

1. Setting black as the default formatter
    1. Go to Settings and search for "format on save" and ensure that that checkbox is ticked.
    1. Then search for "python formatting provider" and select "black" from the dropdown.
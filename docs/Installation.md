# Vortex Installation Guide

It is recommended that Vortex is isntalled in a
dedicated Python virtual environment in order to ensure
that all required dependecies are installed without
affecting the rest of the system.

## Installing Pre-requisites
In order to create a Python virtual environment, the `virtualenv` utility should be installed on the system.

### Fedora
Use the following command to install `virtualenv` using
official Fedora packages:
```
sudo dnf install python3-virtualenv
```

### Ubuntu
Use the following commands to install `virtualenv` using
official Ubuntu packages:
```
sudo apt-get update
sudo apt-get install python3-virtualenv
```

### PIP
`virtualenv` can also be installed using PIP. To do
this, use the following commands:
```
python -m pip install --user virtualenv
```

## Cloning The Repository
To clone the Vortex emulator repository, use the
following command:
```
git clone http://github.com/... <destination>/vortex
```
This clone the repository in the directory
`<directory>/vortex`. From now on, `VORTEX` will be
used to refer to that directory.

## Creating The Virtual Environment
Create a new Python virtual environment using the
following command:
```
virtualenv <destination>
```
where `<destination>` is the directory where you want
your virtual environment to be setup. From this point
on `VIRTDIR` will be used to indicate the path to the
virtual environment.

## Installing Vortex Requirements
Once the virtual environment has been setup, all of
required package should be installed within the
virtual environemtn using the following command:
```
VIRTDIR/bin/pip install -r virtualenv.txt
```

## Building And Installing The Vortex Wheel
The Vortex emulator can be installed within the
virtual environment by building it as a Python
wheel package and installing that package in the
virtual environment.

To build the Python wheel, use the following commands:
```
cd VORTEX
VIRTDIR/bin/python -m build -w .
```
The above commands will build the package in
`VORTEX/dest/vortex-<VERSION>-cp311-cp311-linux_x86_64.whl` where `<VERSION>` is the version of the Vortex
emulator.

Once the Python wheel has been build, install it with:
```
VIRTDIR/bin/pip install VORTEX/dest/vortex-<VERSION>-cp311-cp311-linux_x86_64.whl
```

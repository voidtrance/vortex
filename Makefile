# vortex - GCode machine emulator
# Copyright (C) 2024-2025 Mitko Haralanov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# This project uses Meson and meson-python as the build system.
# However, to simplify development, this Makefile is here for
# convinience and to record the require build commands.
PYTHON ?= $(shell which python3)
PYTHON_DEBUG ?= $(shell which python3-debug)
GDB := $(shell which gdb)
VENV ?=
VENV_PYTHON := $(VENV)/bin/python3
DEBUG_OPTS :=
MESON_DEBUG_OPTS :=
GCC_BUILD_OPTS :=
VERSION=$(shell git describe --tags --abbrev=0)

PYTHON_VERSION=$(shell $(PYTHON) -c "import platform; print(platform.python_version())")
PYTHON_VERSION_NUMS = $(subst ., ,$(PYTHON_VERSION))

ifeq ($(DEBUG),1)
	GCC_BUILD_OPTS=CFLAGS='-DVORTEX_DEBUG -g'
	MESON_BUILD_OPTS=--config-settings=setup-args="-Dbuildtype=debug"
endif

all: version
	$(GCC_BUILD_OPTS) $(PYTHON) -m pip install --no-build-isolation \
		--editable . $(MESON_BUILD_OPTS)
	@if [ ! -L compile_commands.json ]; then \
		ln -s build/cp$(word 1,$(PYTHON_VERSION_NUMS))$(word 2,$(PYTHON_VERSION_NUMS))/compile_commands.json \
			compile_commands.json; \
	fi

version:
	@echo $(VERSION) > version.txt

venv:
	@if [ -z "$(VENV)" ]; then \
		echo "ERROR: Virtual environment path not set"; \
		exit 1; \
	fi
	@echo "Creating virtual environment in $(VENV)..."
	@if [ ! -d $(VENV) ]; then \
		virtualenv $(VENV); \
	fi
	@echo "Installing dependencies..."
	$(VENV)/bin/pip install -r ./virtualenv.txt

wheel: venv version
	$(VENV_PYTHON) -m build -w .

install: wheel
	$(VENV_PYTHON) -m pip install --force-reinstall dist/vortex-*.whl

gdb:
	$(GDB) $(PYTHON_DEBUG) -ex 'r ./vortex_run.py $(GDB_OPTS)'

clean:
	rm -rf build dist builddir
	rm -f compile_commands.json version.txt

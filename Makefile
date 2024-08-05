# vortex - GCode machine emulator
# Copyright (C) 2024  Mitko Haralanov
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

DEBUG_OPTS :=
ifeq ($(DEBUG),1)
	DEBUG_OPTS=--config-settings=setup-args=-Dbuildtype=debug
endif

all:
	$(PYTHON) -m pip install --no-build-isolation \
		--editable . $(DEBUG_OPTS)

wheel:
	$(PYTHON) -m build -w .
	$(PYTHON) -m pip install --force-reinstall dist/vortex-*.whl

clean:
	rm -rf build dist

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
import io
from logging import *
from logging import _levelToName, _nameToLevel, Manager

VERBOSE = 15

_levelToName[VERBOSE] = 'VERBOSE'
_nameToLevel['VERBOSE'] = VERBOSE

def _verbose(self, message, *args, **kwargs):
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs)

Logger.verbose = _verbose
logger = getLogger("vortex")

root = logger
Logger.root = logger
Logger.manager = Manager(Logger.root)

def setup_vortex_logging(level=INFO, logfile=None, extended=False):
    fmt = "%(created)f %(levelname)s"
    if extended:
        fmt += " [%(pathname)s:%(lineno)d]"
    fmt += ": %(message)s"
    basicConfig(filename=logfile, level=level, format=fmt)
    
def verbose(msg, *args, **kwargs):
    root.verbose(msg, *args, **kwargs)
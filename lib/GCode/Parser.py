# vortex - GCode machine emulator
# Copyright (C) 2026 Mitko Haralanov
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
from . import GCode
from typing import *

class GCodeParser:
    def __init__(self):
        return

    def parse(self, gcode : str) -> GCode.GCodeCommand:
        parsed = None
        if gcode.strip() and not gcode.startswith((';', '/', '#')):
            parsed = GCode.GCodeCommand(gcode)
        return parsed

    def parse_file(self, filename : str) -> Generator[GCode.GCodeCommand]:
        with open(filename, 'r') as fd:
            for line in fd:
                yield self.parse(line)

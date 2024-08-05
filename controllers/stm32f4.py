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
from vortex.controllers.objects import *
from vortex.controllers import Pins
from vortex.controllers import Controller

class STM32F446(Controller):
    PINS = [Pins("PA", 0, 15), Pins("PB", 0, 15),
            Pins("PC", 0, 15), Pins("PD", 0, 15),
            Pins("PE", 0, 15), Pins("PF", 0, 15),
            Pins("PG", 0, 15), Pins("PH", 0, 15)]
    FREQUENCY = 12000000
    def __init__(self, config):
        super().__init__(config)

__controller__ = STM32F446
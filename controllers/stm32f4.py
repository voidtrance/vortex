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
from vortex.controllers import Pins
from vortex.controllers import Controller

class STM32F446(Controller):
    ARCH = 32
    PINS = [Pins("PA", 0, 15), Pins("PB", 0, 15),
            Pins("PC", 0, 15), Pins("PD", 0, 15),
            Pins("PE", 0, 15), Pins("PF", 0, 15),
            Pins("PG", 0, 15), Pins("PH", 0, 15)]
    SPI = [["PA6", "PA7", "PA5"],
           ["PB4", "PB5", "PB3"],
           ["PB14", "PB15", "PB13"],
           ["PC2", "PC3", "PB10"],
           ["PC11", "PC12", "PC10"],
           ["PE13", "PE14", "PE12"]]
    FREQUENCY = 12000000
    MOTOR_COUNT = 8
    PWM_COUNT = 8
    HEATER_COUNT = 2
    PROBE_COUNT = 1
    ENDSTOP_COUNT = 5
    THERMISTOR_COUNT = 5
    ADC_MAX = 4095
    PWM_MAX = 255
    def __init__(self, config):
        super().__init__(config)

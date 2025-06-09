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
import inspect
import vortex.core.lib.logging as logging
from re import search
from vortex.lib.constants import *

class Counter():
    def __init__(self, start=0):
        self._start = self._value = start
    def next(self):
        value, self._value = self._value, self._value + 1
        return value
    def reset(self):
        self._value = self._start
    def __setattr__(self, name, value):
        stack = inspect.stack()
        caller = stack[1].frame.f_locals.get("self", None)
        if not caller or not isinstance(caller, Counter):
            raise AttributeError('Class attributes cannot be set')
        function = getattr(caller, stack[1].frame.f_code.co_name)
        if function not in (self.__init__, self.next, self.reset):
            raise KeyError('Class attributes cannot be set')
        super().__setattr__(name, value)

def parse_frequency(frequency):
    if isinstance(frequency, str):
        i = search(r'[^\d\.]', frequency)
        if i is None:
            return int(frequency)
        i = i.end() - 1
        frequency, order = float(frequency[:i]), frequency[i:].upper()
        if order and order != "HZ":
            logging.debug(f"{frequency} {order}, {order}2HZ, {eval(f"{order}2HZ")}")
            frequency = int(frequency * eval(f"{order}2HZ"))
    elif not isinstance(frequency, (int, float)):
        logging.error("Invalid frequency format")
        raise ValueError("Invalid frequency format")
    return frequency

def div_round_up(x, y):
    return (x + y - 1) // y

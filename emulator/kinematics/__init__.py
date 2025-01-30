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
from typing import Any
import vortex.core.kinematics._vortex_kinematics as core_kinematics
from vortex.lib.ext_enum import ExtIntEnum
from argparse import Namespace

class AxisType(ExtIntEnum):
    X = (core_kinematics.lib.AXIS_TYPE_X, "X")
    Y = (core_kinematics.lib.AXIS_TYPE_Y, "Y")
    Z = (core_kinematics.lib.AXIS_TYPE_Z, "Z")
    A = (core_kinematics.lib.AXIS_TYPE_A, "A")
    B = (core_kinematics.lib.AXIS_TYPE_B, "B")
    C = (core_kinematics.lib.AXIS_TYPE_C, "C")
    E = (core_kinematics.lib.AXIS_TYPE_E, "E")

class Coordinate(Namespace):
    def __init__(self, **kwargs):
        self._verify_axes(kwargs.keys())
        self.__dict__.update(kwargs)
    def __iter__(self):
        for axis in self.__dict__:
            yield axis
    def __setattr__(self, name, value):
        self._verify_axes([name])
        return super().__setattr__(name, value)
    def _verify_axes(self, axes):
        for axis in axes:
            if axis.upper() not in AxisType:
                raise AttributeError(f"Axis of type '{axis}' is invalid")

class Kinematics:
    def __init__(self, type, controller):
        self._ffi = core_kinematics.ffi
        self._lib = core_kinematics.lib
        self._controller = controller
        if isinstance(type, str):
            self._kinematics_type = getattr(self._lib,
                                       f"KINEMATICS_{type.upper()}",
                                       self._lib.KINEMATICS_NONE)
        if self._kinematics_type == self._lib.KINEMATICS_NONE:
            raise AttributeError("Invalid machine kinematics type")
        self._lib.kinematics_type_set(self._kinematics_type)

    def get_move(self, cur_position, new_position):
        current = Coordinate()
        new = Coordinate()
        if self._kinematics_type == self._lib.KINEMATICS_COREXY:
            if len(cur_position) != 2 or len(new_position) != 2:
                raise ValueError("Invalid postion values length")
            current.x = cur_position[0]
            current.y = cur_position[1]
            new.x = new_position[0]
            new.y = new_position[1]
        elif self._kinematics_type == self._lib.KINEMATICS_COREXY:
            if len(cur_position) != 2 or len(new_position) != 2:
                raise ValueError("Invalid postion values length")
            current.x = cur_position[0]
            current.z = cur_position[1]
            new.x = new_position[0]
            new.z = new_position[1]
        else:
            current.x = cur_position[0]
            new.x = new_position[0]
        movement = self.compute_motor_movement(current, new)
        movement = [getattr(movement, str(x).lower()) for x in AxisType]
        return movement[:len(new_position)]
    def compute_motor_movement(self, cur_position, new_position):
        distance = {x: getattr(new_position, x) - getattr(cur_position, x) \
                    for x in cur_position}
        delta = self._ffi.new("coordinates_t *", distance)
        movement = self._ffi.new("coordinates_t *")
        ret = self._lib.compute_motor_movement(delta, movement)
        return movement

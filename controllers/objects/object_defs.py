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
from argparse import Namespace
from ..types import ModuleTypes, ModuleEvents
import ctypes

class ObjectDef(Namespace):
    def __init__(self, type=ModuleTypes.NONE):
        self.type = type
        self.config = getattr(self, str(type).capitalize() + "Config", None)
        self.state = getattr(self, str(type).capitalize() + "Status", None)
        self.commands = []
        self.events = {}

class Stepper(ObjectDef):
    class StepperConfig(ctypes.Structure):
        _fields_ = [("steps_per_rotation", ctypes.c_uint32),
                    ("microsteps", ctypes.c_uint32),
                    ("clock_speed", ctypes.c_char * 64),
                    ("driver", ctypes.c_char * 16)]
    class StepperEnableCommandOpts(ctypes.Structure):
        _fields_ = [("enable", ctypes.c_bool)]
    class StepperSetSpeedCommandOpts(ctypes.Structure):
        _fields_ = [("steps_per_second", ctypes.c_double)]
    class StepperMoveCommandOpts(ctypes.Structure):
        _fields_ = [("direction", ctypes.c_uint8),
                    ("steps", ctypes.c_uint32)]
    class StepperStatus(ctypes.Structure):
        _fields_ = [("enabled", ctypes.c_bool),
                    ("steps", ctypes.c_int64),
                    ("spr", ctypes.c_uint16),
                    ("microsteps", ctypes.c_uint8)]
    class StepperMoveCompleteEvent(ctypes.Structure):
        _fields_ = [("steps", ctypes.c_uint64)]
    def __init__(self):
        super().__init__(ModuleTypes.STEPPER)
        self.commands = [(0, "enable", self.StepperEnableCommandOpts, (False,)),
                         (1, "set_speed", self.StepperSetSpeedCommandOpts, (0., )),
                         (2, "move", self.StepperMoveCommandOpts, (0, 0))]
        self.events = {ModuleEvents.STEPPER_MOVE_COMPLETE: self.StepperMoveCompleteEvent}
        
class Thermistor(ObjectDef):
    class ThermistorConfig(ctypes.Structure):
        _fields_ = [("sensor_type", ctypes.c_char * 64),
                    ("heater", ctypes.c_char * 64),
                    ("beta", ctypes.c_uint32)]
    class ThermistorStatus(ctypes.Structure):
        _fields_ = [("resistance", ctypes.c_double)]
    def __init__(self):
        super().__init__(ModuleTypes.THERMISTOR)
class Heater(ObjectDef):
    class HeaterConfig(ctypes.Structure):
        _fields_ = [("power", ctypes.c_uint16)]
    class HeaterSetTempCommandOpts(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_uint32)]
    class HeaterStatus(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_uint32)]
    class HeaterEventTempReached(ctypes.Structure):
        _fields_ = [("temp", ctypes.c_float)]
    def __init__(self):
        super().__init__(ModuleTypes.HEATER)
        self.commands = [(0, "set_temperature", self.HeaterSetTempCommandOpts, (0,))]
        self.events = {ModuleEvents.HEATER_TEMP_REACHED: self.HeaterEventTempReached}

class Endstop(ObjectDef):
    class EndstopConfig(ctypes.Structure):
        _fields_ = [("type", ctypes.c_char * 4),
                    ("axis", ctypes.c_char * 64)]
    class EndstopStatus(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool)]
    class EndstopTriggerEvent(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool)]
    def __init__(self):
        super().__init__()
        self.type = ModuleTypes.ENDSTOP
        self.config = self.EndstopConfig
        self.events = {ModuleEvents.ENDSTOP_TRIGGER: self.EndstopTriggerEvent}
        self.state = self.EndstopStatus

class Axis(ObjectDef):
    class AxisConfig(ctypes.Structure):
        _fields_ = [("length", ctypes.c_float),
                    ("mm_per_step", ctypes.c_double),
                    ("stepper", ctypes.POINTER(ctypes.c_char_p)),
                    ("endstop", ctypes.c_char * 64)]
    class AxisMoveCommandOpts(ctypes.Structure):
        _fields_ = [("distance", ctypes.c_double)]
    class AxisStatus(ctypes.Structure):
        _fields_ = [("homed", ctypes.c_bool),
                    ("length", ctypes.c_float),
                    ("position", ctypes.c_double),
                    ("ratio", ctypes.c_float),
                    ("motors", (ctypes.c_char * 64) * 8)]
    class AxisEventHomed(ctypes.Structure):
        _fields_ = [("axis", ctypes.c_char_p)]
    def __init__(self):
        super().__init__(ModuleTypes.AXIS)
        self.commands = [(0, "move", self.AxisMoveCommandOpts, (0., )),
                         (1, "home", None, None)]
        self.events = {ModuleEvents.AXIS_HOMED : self.AxisEventHomed}

class Probe(ObjectDef):
    class ProbeConfig(ctypes.Structure):
        _fields_ = [("z_offset", ctypes.c_float),
                    ("range", ctypes.c_float)]
    class ProbeStatus(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool),
                    ("position", ctypes.c_double)]
    class ProbeEventTriggered(ctypes.Structure):
        _fields_ = [("position", ctypes.c_double)]
    def __init__(self):
        super().__init__(ModuleTypes.PROBE)
        self.events = {ModuleEvents.PROBE_TRIGGERED: self.ProbeEventTriggered}

__objects__ = [Stepper, Thermistor, Heater, Endstop,
               Axis, Probe]

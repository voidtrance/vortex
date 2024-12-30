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
from vortex.emulator.kinematics import AxisType
import ctypes

class ObjectDef(Namespace):
    virtual = False
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
                    ("start_speed", ctypes.c_uint32),
                    ("steps_per_mm", ctypes.c_uint32),
                    ("driver", ctypes.c_char * 16),
                    ("enable_pin", ctypes.c_char * 8),
                    ("dir_pin", ctypes.c_char * 8),
                    ("step_pin", ctypes.c_char * 8)]
    class StepperEnableCommandOpts(ctypes.Structure):
        _fields_ = [("enable", ctypes.c_bool)]
    class StepperSetSpeedCommandOpts(ctypes.Structure):
        _fields_ = [("steps_per_second", ctypes.c_double)]
    class StepperSetAccelCommandOpts(ctypes.Structure):
        _fields_ = [("accel", ctypes.c_uint32),
                    ("decel", ctypes.c_uint32)]
    class StepperMoveCommandOpts(ctypes.Structure):
        _fields_ = [("direction", ctypes.c_uint8),
                    ("steps", ctypes.c_uint32)]
    class StepperUsePinsCommandOpts(ctypes.Structure):
        _fields_ = [("enable", ctypes.c_bool)]
    class StepperStatus(ctypes.Structure):
        _fields_ = [("enabled", ctypes.c_bool),
                    ("use_pins", ctypes.c_bool),
                    ("steps", ctypes.c_int64),
                    ("spr", ctypes.c_uint16),
                    ("microsteps", ctypes.c_uint8),
                    ("speed", ctypes.c_double),
                    ("accel", ctypes.c_double),
                    ("decel", ctypes.c_double),
                    ("steps_per_mm", ctypes.c_uint),
                    ("enable_pin", ctypes.c_char * 8),
                    ("dir_pin", ctypes.c_char * 8),
                    ("step_pin", ctypes.c_char * 8),
                    ("pin_addr", ctypes.c_ulong)]
    class StepperMoveCompleteEvent(ctypes.Structure):
        _fields_ = [("steps", ctypes.c_uint64)]
    def __init__(self):
        super().__init__(ModuleTypes.STEPPER)
        self.commands = [(0, "enable", self.StepperEnableCommandOpts, (False,)),
                         (1, "set_speed", self.StepperSetSpeedCommandOpts, (0.,)),
                         (2, "set_accel", self.StepperSetAccelCommandOpts, (0.,)),
                         (3, "move", self.StepperMoveCommandOpts, (0, 0)),
                         (4, "use_pins", self.StepperUsePinsCommandOpts, (False,))]
        self.events = {ModuleEvents.STEPPER_MOVE_COMPLETE: self.StepperMoveCompleteEvent}

class ThermistorValueBeta(ctypes.Structure):
    _fields_ = [("beta", ctypes.c_uint16)]

class ThermistorValueCoeff(ctypes.Structure):
    _fields_ = [("temp", ctypes.c_uint16),
                ("resistance", ctypes.c_uint32)]

class ThermistorValueConfig(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int),
                ("resistor", ctypes.c_uint16),
                ("beta", ThermistorValueBeta),
                ("coeff", ThermistorValueCoeff * 3)]

class Thermistor(ObjectDef):
    class ThermistorConfig(ctypes.Structure):
        _fields_ = [("sensor_type", ctypes.c_char * 64),
                    ("heater", ctypes.c_char * 64),
                    ("pin", ctypes.c_char * 8),
                    ("adc_max", ctypes.c_uint16),
                    ("config", ThermistorValueConfig)]
    class ThermistorStatus(ctypes.Structure):
        _fields_ = [("resistance", ctypes.c_float),
                    ("adc", ctypes.c_uint16),
                    ("pin", ctypes.c_char * 8)]
    def __init__(self):
        super().__init__(ModuleTypes.THERMISTOR)

class HeaterLayer(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int),
                ("density", ctypes.c_double),
                ("capacity", ctypes.c_double),
                ("conductivity", ctypes.c_double),
                ("emissivity", ctypes.c_double),
                ("convection", ctypes.c_float * 2),
                ("size", ctypes.c_double * 3)]

class Heater(ObjectDef):
    class HeaterConfig(ctypes.Structure):
        _fields_ = [("power", ctypes.c_uint16),
                    ("pin", ctypes.c_char * 8),
                    ("max_temp", ctypes.c_float),
                    ("layers", HeaterLayer * 8)]
    class HeaterSetTempCommandOpts(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_float)]
    class HeaterStatus(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_float),
                    ("max_temp", ctypes.c_float),
                    ("pin", ctypes.c_char * 8)]
    class HeaterEventTempReached(ctypes.Structure):
        _fields_ = [("temp", ctypes.c_float)]
    def __init__(self):
        super().__init__(ModuleTypes.HEATER)
        self.commands = [(0, "set_temperature", self.HeaterSetTempCommandOpts, (0,))]
        self.events = {ModuleEvents.HEATER_TEMP_REACHED: self.HeaterEventTempReached}

class Endstop(ObjectDef):
    class EndstopConfig(ctypes.Structure):
        _fields_ = [("type", ctypes.c_char * 4),
                    ("axis", ctypes.c_char),
                    ("pin", ctypes.c_char * 8)]
    class EndstopStatus(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool),
                    ("type", ctypes.c_char * 4),
                    ("axis", ctypes.c_int),
                    ("pin", ctypes.c_char * 8),
                    ("pin_addr", ctypes.c_ulong)]
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
                    ("type", ctypes.c_char),
                    ("stepper", ctypes.POINTER(ctypes.c_char_p)),
                    ("endstop", ctypes.c_char * 64)]
    class AxisMoveCommandOpts(ctypes.Structure):
        _fields_ = [("position", ctypes.c_double)]
    class AxisStatus(ctypes.Structure):
        _fields_ = [("homed", ctypes.c_bool),
                    ("length", ctypes.c_float),
                    ("type", ctypes.c_int),
                    ("position", ctypes.c_double),
                    ("motors", (ctypes.c_char * 64) * 8),
                    ("endstop", ctypes.c_char * 64)]
    class AxisEventHomed(ctypes.Structure):
        _fields_ = [("axis", ctypes.c_char_p)]
    def __init__(self):
        super().__init__(ModuleTypes.AXIS)
        self.commands = [(0, "move", self.AxisMoveCommandOpts, (0., )),
                         (1, "home", None, None)]
        self.events = {ModuleEvents.AXIS_HOMED : self.AxisEventHomed}

class Probe(ObjectDef):
    class ProbeConfig(ctypes.Structure):
        _fields_ = [("toolhead", ctypes.c_char * 64),
                    ("offsets", ctypes.c_float * len(AxisType)),
                    ("axes", ctypes.POINTER(ctypes.c_char_p)),
                    ("range", ctypes.c_float),
                    ("pin", ctypes.c_char * 8)]
    class ProbeStatus(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool),
                    ("offsets", ctypes.c_float * len(AxisType)),
                    ("position", ctypes.c_double * len(AxisType)),
                    ("pin", ctypes.c_char * 8),
                    ("pin_addr", ctypes.c_ulong)]
    class ProbeEventTriggered(ctypes.Structure):
        _fields_ = [("position", ctypes.c_double * len(AxisType))]
    def __init__(self):
        super().__init__(ModuleTypes.PROBE)
        self.events = {ModuleEvents.PROBE_TRIGGERED: self.ProbeEventTriggered}

class Toolhead(ObjectDef):
    class ToolheadConfig(ctypes.Structure):
        _fields_ = [("axes", ctypes.POINTER(ctypes.c_char_p))]
    class ToolheadStatus(ctypes.Structure):
        _fields_ = [("axes", ctypes.c_int * len(AxisType)),
                    ("position", ctypes.c_double * len(AxisType))]
    class ToolheadEventOrigin(ctypes.Structure):
        _fields_ = [("position", ctypes.c_double * len(AxisType))]
    def __init__(self):
        super().__init__(ModuleTypes.TOOLHEAD)
        self.events = {ModuleEvents.TOOLHEAD_ORIGIN: self.ToolheadEventOrigin}

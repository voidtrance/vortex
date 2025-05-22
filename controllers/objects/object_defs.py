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
from argparse import Namespace
from vortex.core import ObjectTypes, ObjectEvents
from vortex.core import PIN_NAME_SIZE, OBJECT_NAME_SIZE, ENDSTOP_NAME_SIZE, MOTOR_NAME_SIZE, \
                        TOOLHEAD_NAME_SIZE, HEATER_NAME_SIZE, \
                        HEAT_SENSOR_NAME_SIZE
from vortex.emulator.kinematics import AxisType
import ctypes

class ObjectDef(Namespace):
    virtual = False
    def __init__(self, type=ObjectTypes.NONE):
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
                    ("enable_pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("dir_pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("step_pin", ctypes.c_char * PIN_NAME_SIZE)]
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
                    ("enable_pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("dir_pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("step_pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("pin_addr", ctypes.c_ulong)]
    class StepperMoveCompleteEvent(ctypes.Structure):
        _fields_ = [("steps", ctypes.c_uint64)]
    def __init__(self):
        super().__init__(ObjectTypes.STEPPER)
        self.commands = [(0, "enable", self.StepperEnableCommandOpts, (False,)),
                         (1, "set_speed", self.StepperSetSpeedCommandOpts, (0.,)),
                         (2, "set_accel", self.StepperSetAccelCommandOpts, (0.,)),
                         (3, "move", self.StepperMoveCommandOpts, (0, 0)),
                         (4, "use_pins", self.StepperUsePinsCommandOpts, (False,))]
        self.events = {ObjectEvents.STEPPER_MOVE_COMPLETE: self.StepperMoveCompleteEvent}

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
        _fields_ = [("sensor_type", ctypes.c_char * HEAT_SENSOR_NAME_SIZE),
                    ("heater", ctypes.c_char * HEATER_NAME_SIZE),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("adc_max", ctypes.c_uint16),
                    ("config", ThermistorValueConfig)]
    class ThermistorStatus(ctypes.Structure):
        _fields_ = [("resistance", ctypes.c_float),
                    ("adc", ctypes.c_uint16),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE)]
    def __init__(self):
        super().__init__(ObjectTypes.THERMISTOR)

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
                    ("pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("max_temp", ctypes.c_float),
                    ("layers", HeaterLayer * 8)]
    class HeaterSetTempCommandOpts(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_float)]
    class HeaterUsePinsCommandOpts(ctypes.Structure):
        _fields_ = [("enable", ctypes.c_bool)]
    class HeaterStatus(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_float),
                    ("max_temp", ctypes.c_float),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("pin_addr", ctypes.c_ulong)]
    class HeaterEventTempReached(ctypes.Structure):
        _fields_ = [("temp", ctypes.c_float)]
    def __init__(self):
        super().__init__(ObjectTypes.HEATER)
        self.commands = [(0, "set_temperature", self.HeaterSetTempCommandOpts, (0,)),
                         (1, "use_pins", self.HeaterUsePinsCommandOpts, (False,))]
        self.events = {ObjectEvents.HEATER_TEMP_REACHED: self.HeaterEventTempReached}

class Endstop(ObjectDef):
    class EndstopConfig(ctypes.Structure):
        _fields_ = [("type", ctypes.c_char * 4),
                    ("axis", ctypes.c_char),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE)]
    class EndstopStatus(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool),
                    ("type", ctypes.c_char * 4),
                    ("axis", ctypes.c_int),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("pin_addr", ctypes.c_ulong)]
    class EndstopTriggerEvent(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool)]
    def __init__(self):
        super().__init__()
        self.type = ObjectTypes.ENDSTOP
        self.config = self.EndstopConfig
        self.events = {ObjectEvents.ENDSTOP_TRIGGER: self.EndstopTriggerEvent}
        self.state = self.EndstopStatus

class Axis(ObjectDef):
    class AxisConfig(ctypes.Structure):
        _fields_ = [("length", ctypes.c_float),
                    ("type", ctypes.c_char),
                    ("stepper", ctypes.POINTER(ctypes.c_char_p)),
                    ("endstop", ctypes.c_char * ENDSTOP_NAME_SIZE)]
    class AxisStatus(ctypes.Structure):
        _fields_ = [("homed", ctypes.c_bool),
                    ("min", ctypes.c_float),
                    ("max", ctypes.c_float),
                    ("type", ctypes.c_int),
                    ("position", ctypes.c_double),
                    ("motors", (ctypes.c_char * MOTOR_NAME_SIZE) * 8),
                    ("endstop", ctypes.c_char * ENDSTOP_NAME_SIZE)]
    class AxisEventHomed(ctypes.Structure):
        _fields_ = [("axis", ctypes.c_char_p)]
    def __init__(self):
        super().__init__(ObjectTypes.AXIS)
        self.events = {ObjectEvents.AXIS_HOMED : self.AxisEventHomed}

class Probe(ObjectDef):
    class ProbeConfig(ctypes.Structure):
        _fields_ = [("toolhead", ctypes.c_char * TOOLHEAD_NAME_SIZE),
                    ("offsets", ctypes.c_float * len(AxisType)),
                    ("axes", ctypes.POINTER(ctypes.c_char_p)),
                    ("range", ctypes.c_float),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE)]
    class ProbeStatus(ctypes.Structure):
        _fields_ = [("triggered", ctypes.c_bool),
                    ("offsets", ctypes.c_float * len(AxisType)),
                    ("position", ctypes.c_double * len(AxisType)),
                    ("pin", ctypes.c_char * PIN_NAME_SIZE),
                    ("pin_addr", ctypes.c_ulong)]
    class ProbeEventTriggered(ctypes.Structure):
        _fields_ = [("position", ctypes.c_double * len(AxisType))]
    def __init__(self):
        super().__init__(ObjectTypes.PROBE)
        self.events = {ObjectEvents.PROBE_TRIGGERED: self.ProbeEventTriggered}

class Toolhead(ObjectDef):
    class ToolheadConfig(ctypes.Structure):
        _fields_ = [("axes", ctypes.POINTER(ctypes.c_char_p))]
    class ToolheadStatus(ctypes.Structure):
        _fields_ = [("axes", ctypes.c_int * len(AxisType)),
                    ("position", ctypes.c_double * len(AxisType))]
    class ToolheadEventOrigin(ctypes.Structure):
        _fields_ = [("position", ctypes.c_double * len(AxisType))]
    def __init__(self):
        super().__init__(ObjectTypes.TOOLHEAD)
        self.events = {ObjectEvents.TOOLHEAD_ORIGIN: self.ToolheadEventOrigin}

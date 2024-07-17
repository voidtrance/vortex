from argparse import Namespace
from ..types import ModuleTypes, ModuleEvents
import ctypes

class ObjectDef(Namespace):
    def __init__(self):
        self.config = None
        self.commands = []
        self.state = None
        self.events = {}
        self.type = ModuleTypes.NONE

class Stepper(ObjectDef):
    class StepperConfig(ctypes.Structure):
        _fields_ = [("steps_per_rotation", ctypes.c_uint32),
                    ("microsteps", ctypes.c_uint32),
                    ("clock_speed", ctypes.c_char * 64),
                     ("driver", ctypes.c_char * 16)]
    class StepperEnableCommandOpts(ctypes.Structure):
        _fields_ = [("enable", ctypes.c_bool)]
    class StepperMoveCommandOpts(ctypes.Structure):
        _fields_ = [("direction", ctypes.c_uint8),
                    ("steps", ctypes.c_uint32)]
    class StepperStatus(ctypes.Structure):
        _fields_ = [("enabled", ctypes.c_uint8),
                    ("steps", ctypes.c_uint64)]
    class StepperMoveCompleteEvent(ctypes.Structure):
        _fields_ = [("steps", ctypes.c_uint64)]
    def __init__(self):
        super().__init__()
        self.type = ModuleTypes.STEPPER
        self.config = self.StepperConfig
        self.commands = [(0, "enable", self.StepperEnableCommandOpts, (False,)),
                         (1, "move", self.StepperMoveCommandOpts, (0, 0))]
        self.events = {ModuleEvents.STEPPER_MOVE_COMPLETE: self.StepperMoveCompleteEvent}
        
class Thermistor(ObjectDef):
    class ThermistorConfig(ctypes.Structure):
        _fields_ = [("sensor_type", ctypes.c_char * 64),
                    ("beta", ctypes.c_uint32)]
    class ThermistorStatus(ctypes.Structure):
        _fields_ = [("resistance", ctypes.c_float)]
    def __init__(self):
        super().__init__()
        self.type = ModuleTypes.THERMISTOR
        self.config = self.ThermistorConfig
        self.state = self.ThermistorStatus
class Heater(ObjectDef):
    class HeaterConfig(ctypes.Structure):
        _fields_ = [("sensor_type", ctypes.c_char * 64),
                    ("beta", ctypes.c_uint32),
                    ("power", ctypes.c_uint16)]
    class HeaterSetTempCommandOpts(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_uint32)]
    class HeaterStatus(ctypes.Structure):
        _fields_ = [("temperature", ctypes.c_uint32),
                    ("power", ctypes.c_uint16)]
    class HeaterEventTempReached(ctypes.Structure):
        _fields_ = [("temp", ctypes.c_float)]
    def __init__(self):
        super().__init__()
        self.type = ModuleTypes.HEATER
        self.config = self.HeaterConfig
        self.commands = [(0, "set_temperature", self.HeaterSetTempCommandOpts, (0,))]
        self.events = {ModuleEvents.HEATER_TEMP_REACHED: self.HeaterEventTempReached}

__objects__ = [Stepper, Heater]

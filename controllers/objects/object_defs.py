from argparse import Namespace
import ctypes

class ObjectDef(Namespace):
    def __init__(self):
        self.config = None
        self.commands = []
        self.sources = []


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
    def __init__(self):
        super().__init__()
        self.config = self.StepperConfig
        self.commands = [(0, "enable", self.StepperEnableCommandOpts, (False,)),
                         (1, "move", self.StepperMoveCommandOpts, (0, 0))]
        self.sources = ["controllers/objects/stepper.c"]
        

__objects__ = [Stepper]

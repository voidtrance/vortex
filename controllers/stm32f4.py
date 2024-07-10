from controllers.objects import *
from controllers import Pins
from controllers import Controller

class STM32F4(Controller):
    PINS = [Pins("PA", 0, 15), Pins("PB", 0, 15),
            Pins("PC", 0, 15), Pins("PD", 0, 15),
            Pins("PE", 0, 15), Pins("PF", 0, 15),
            Pins("PG", 0, 15), Pins("PH", 0, 15)]
    def __init__(self, config):
        super().__init__(config)

__controller__ = STM32F4
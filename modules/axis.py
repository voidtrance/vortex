from controllers.objects import BaseModule, CmdOptionSet
import lib.events as events
from controllers.objects.endstop import Direction

class Axis(BaseModule):
    _class = "axis"
    def __init__(self, name, config):
        super().__init__(name, config)
        self._motor = self.config.controller.lookup_object("stepper", self.config.stepper)
        assert self._motor is not None
        self._length = self.config.length
        self._mm_per_step = self.config.mm_per_step
        min_endstop = self.config.controller.lookup_object("endstop", self.config.min_endstop)
        if min_endstop:
            min_endstop.set_trigger_motor_steps(Direction.MIN, 0)
        max_endstop = self.config.controller.lookup_object("endstop", self.config.max_endstop)
        if max_endstop:
            max_endstop.set_trigger_motor_steps(Direction.MAX, self._length * (1 / self._mm_per_step))
        self._motor.enable()

    def move(self, distance):
        assert distance != 0
        dir = int(distance > 0.)
        distance = abs(distance)
        print(f"Moving axis {distance} mm")
        self._motor.move(dir, int(distance * (1 / self._mm_per_step)))
        
    def get_cmd_set(self):
        return {"move" : (self.move, CmdOptionSet(distance=float))}
    
    def update(self, timestamp):
        return
    
__module_objects__ = {
    "axis" : Axis
}
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
import select
import os
import time
import logging
import vortex.frontends.lib
import vortex.frontends.gcode.gcmd as gcmd
import vortex.lib.constants as constants
import vortex.lib.ext_enum as enum
from vortex.frontends import BaseFrontend
from vortex.controllers.types import ModuleTypes, ModuleEvents

@enum.unique
class CoordinateType(enum.ExtIntEnum):
    ABSOLUTE = enum.auto()
    RELATIVE = enum.auto()
class GCodeFrontend(BaseFrontend):
    FIFO = "/tmp/gcode_frontend_fifo"
    def __init__(self):
        super().__init__()
        try:
            os.mkfifo(self.FIFO)
        except FileExistsError:
            pass
        mfd, sfd = vortex.frontends.lib.create_pty(self.FIFO)
        self._fd = os.fdopen(mfd, 'r')
        self._poll = select.poll()
        self._poll.register(self._fd, select.POLLIN|select.POLLHUP)
        self._command_id_queue = []
        self.current_feed_rate = 0.
        self.coordinates = CoordinateType.ABSOLUTE

    def _process_commands(self, *args):
        while self._run:
            events = self._poll.poll(0.1)
            if not events or self._fd.fileno() not in [e[0] for e in events]:
                continue
            event = [e for e in events if e[0] == self._fd.fileno()]
            if not (event[0][1] & select.POLLIN):
                continue
            cmd = self._fd.readline()
            logging.debug(f"Received command: {cmd.strip()}")
            cmd = gcmd.GCodeCommand(cmd)
            handler = getattr(self, cmd.command, None)
            logging.debug(f"Command {cmd} handler {handler}")
            if not handler:
                logging.error(f"No handler for command {cmd.command}")
                continue
            handler(cmd)

    def __del__(self):
        self._fd.close()
        os.unlink(self.FIFO)

    def complete_command(self, id, result):
        logging.debug(f"Command {id} complete: {result}")
        super().complete_command(id, result)

    def event_handler(self, event, owner, timestamp, *args):
        super().event_handler(event, owner, timestamp, *args)
        print(event, owner, timestamp, args)
        if event == "move_complete":
            print(owner.get_status())

    # GCode command implementation
    def G0(self, cmd):
        axis_ids = self._obj_name_2_id[ModuleTypes.AXIS].values()
        axes_status = self.query_object(list(axis_ids))
        klass = ModuleTypes.AXIS
        if cmd.has_param("F"):
            mm_per_min = cmd.get_param("F")
            speed = mm_per_min.value / 60
            for status in axes_status.values():
                logging.debug(f"axis ratio: {status['travel_per_step']}")
                for motor in [x for x in status['motors'] if x]:
                    self.queue_command(
                        ModuleTypes.STEPPER, motor, "set_speed",
                        f"steps_per_second={speed / status['travel_per_step']}",
                                        0)
        for axis in cmd.get_params(["F"]):
            if self.coordinates == CoordinateType.RELATIVE:
                axis_id = self._obj_name_2_id[ModuleTypes.AXIS][axis]
                axis_position = axes_status[axis_id]["position"] + axis.value
            else:
                axis_position = axis.value
            self.queue_command(klass, axis.name.lower(), "move",
                               f"position={axis_position}", 0)
    def G1(self, cmd):
        self.G0(cmd)
    def G4(self, cmd):
        if not cmd.has_params():
            while self._command_completion:
                time.sleep(0.1)
        else:
            dwell = cmd.get_param("S") or cmd.get_param("P")
            time.sleep(dwell / constants.SEC2MSEC)
    def G28(self, cmd):
        klass = ModuleTypes.AXIS
        if not cmd.has_params():
            for axis in self._obj_name_2_id[klass]:
                # Do axis homing one-by-one.
                while self._command_completion:
                    print(self._command_completion)
                    time.sleep(0.2)
                logging.debug(f"Sending command 'home' to {axis}")
                if not self.queue_command(klass, axis, "home", None, 0):
                    logging.error(f"Failed to queue command 'home' for axis {axis}")
        else:
            for axis in cmd.get_params():
                if not self.queue_command(klass, axis.name.lower(), "home", None, 0):
                    logging.error(f"Failed to queue command 'home' for {axis}")
    def G90(self, cmd):
        self.coordinates = CoordinateType.ABSOLUTE
    def G91(self, cmd):
        self.coordinates = CoordinateType.RELATIVE
    def M0(self, cmd):
        self.M400(None)
        wait_time = 0.
        if cmd.has_param("P"):
            wait_time = cmd.get_param("P").value / constants.SEC2MSEC
        elif cmd.has_param("S"):
            wait_time = cmd.get_param("S").value
        if wait_time:
            time.sleep(wait_time)
        self.reset()
        self.is_reset = True
    def M1(self, cmd):
        self.M400(None)
        reset_objects = []
        for object_id in self._obj_id_2_name[ModuleTypes.STEPPERS] + \
            self._obj_id_2_name[ModuleTypes.HEATER]:
            reset_objects.append(object_id)
        wait_time = 0.
        if cmd.has_param("P"):
            wait_time = cmd.get_param("P").value / constants.SEC2MSEC
        elif cmd.has_param("S"):
            wait_time = cmd.get_param("S").value
        if wait_time:
            time.sleep(wait_time)
        self.reset(reset_objects)
    def M104(self, cmd):
        object = self.find_object(ModuleTypes.HEATER, "extruder", "hotend")
        if object:
            if cmd.command_code == 109:
                self.event_register(ModuleTypes.HEATER,
                                    ModuleEvents.HEATER_TEMP_REACHED,
                                    object, self.event_handler)
                self._default_sequential = self._run_sequential
                self._run_sequential = True
            temp = cmd.get_param("S")
            if not self.queue_command(ModuleTypes.HEATER, object,
                                      "set_temperature",
                                      f"temperature={temp.value}", 0):
                logging.error("Failed to queue command")
    def M106(self, cmd):
        object = self.find_object(ModuleTypes.FAN, "fan1", "fan", "extruder", "hostend")
        if object:
            speed = cmd.get_param("S")
            if not self.queue_command(ModuleTypes.FAN, object,
                                      "set_speed", f"speed={speed.value}", 0):
                logging.error("Failed to queue command")
    def M107(self, cmd):
        cmd = gcmd.GCodeCommand("M106 S0")
        self.M106(cmd)
    def M109(self, cmd):
        self.M104(cmd)
    def M112(self, cmd):
        self.reset()
        self.is_reset = True
    def M140(self, cmd):
        object = self.find_object(ModuleTypes.HEATER, "bed", "surface")
        if object:
            #index = cmd.get_param("I")
            temp = cmd.get_param("S")
            if not self.queue_command(ModuleTypes.HEATER, object,
                                      "set_temperature",
                                      f"temperature={temp.value}", 0):
                logging.error("Failed to queue command")
    def M190(self, cmd):
        self.G140(cmd)
    def M204(self, cmd):
        accel = cmd.get_param("S")
        axes = self.get_object_set(ModuleTypes.AXIS)
        if "e" in axes:
            axes.remove("e")
        axes_ids = [self.get_object_id(ModuleTypes.AXIS, x) for x in axes]
        status = self.query_object(axes_ids)
        for axis in status:
            for motor in status[axis]["motors"]:
                if not motor:
                    continue
                if not self.queue_command(ModuleTypes.STEPPER, motor,
                                          "set_accel",
                                          f"accel={accel.value},decel=0", 0):
                    logging.error("Failed to queue command")
    def M400(self, cmd):
        while self._command_completion:
            time.sleep(0.1)
    def M999(self, cmd):
        object = self._obj_name_2_id[ModuleTypes.TOOLHEAD]['tool1']
        print(self.query_object([object]))

def create():
    return GCodeFrontend()
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
from vortex.frontends import BaseFrontend
from vortex.controllers.types import ModuleTypes, ModuleEvents

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
        self._cmd_map = {
            "g":
            {
                0: self.move,
                1: self.move,
                4: self.dwell,
                28: self.home
                },
            "m": {
                104: self.heat_tool,
                109: self.heat_tool,
                140: self.head_bed,
                190: self.head_bed,
                400: self.empty_queue
                },
            "t": {},
            "d": {},
        }

    def home(self, cmd):
        klass = ModuleTypes.AXIS
        if not cmd.has_params():
            for axis in self._obj_name_2_id[klass]:
                logging.debug(f"Sending command 'home' to {axis}")
                if not self.queue_command(klass, axis, "home", None, 0):
                    logging.error(f"Failed to queue command 'home' for axis {axis}")
        else:
            for axis in cmd.get_params():
                if not self.queue_command(klass, axis.name.lower(), "home", None, 0):
                    logging.error(f"Failed to queue command 'home' for {axis}")
    
    def move(self, cmd):
        klass = ModuleTypes.AXIS
        for axis in cmd.get_params():
            self.queue_command(klass, axis.name.lower(), "move",
                               f"distance={axis.value}", 0)
    
    def dwell(self, cmd):
        if not cmd.has_params():
            while self._command_completion:
                time.sleep(0.1)
        else:
            dwell = cmd.get_param("S") or cmd.get_param("P")
            time.sleep(dwell / constants.SEC2MSEC)
    
    def heat_tool(self, cmd):
        object = self._find_object(ModuleTypes.HEATER, "extruder", "hotend")
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

    def head_bed(self, cmd):
        object = self._find_object(ModuleTypes.HEATER, "bed", "surface")
        if object:
            #index = cmd.get_param("I")
            temp = cmd.get_param("S")
            if not self.queue_command(ModuleTypes.HEATER, object,
                                      "set_temperature",
                                      f"temperature={temp.value}", 0):
                logging.error("Failed to queue command")

    def empty_queue(self, cmd):
        while self._command_completion:
            time.sleep(0.1)
    
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
            self._cmd_map[cmd.command_class.lower()][cmd.command_code](cmd)

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


def create():
    return GCodeFrontend()
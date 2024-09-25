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
import queue
import logging
import importlib
import time
from os import strerror
from collections import OrderedDict
from vortex.lib.constants import *
from vortex.core import VortexCoreError
from vortex.controllers.types import ModuleTypes, ModuleEvents
import vortex.emulator.monitor as monitor
import vortex.emulator.kinematics as kinematics

__all__ = ["Emulator"]

class Command:
    def __init__(self, obj_id, cmd_id, opts, timestamp=None):
        self.obj_id, self.cmd_id, self.opts, self.time = \
            obj_id, cmd_id, opts, timestamp
        self.id = id(self)
    def __str__(self):
        return f"Command({self.id}, {self.obj_id}:{self.cmd_id}@{self.time})"
        
class CommandQueue(queue.Queue):
    def put(self, command):
        if not isinstance(command, Command):
            raise ValueError("'command' is not a Command instance")
        super().put(command)
        return command.id
    def queue_command(self, obj_id, cmd_id, opts, timestamp=None):
        cmd = Command(obj_id, cmd_id, opts, timestamp)
        return (self.put(cmd), cmd)

class ScheduleQueue:
    class TimeDict(OrderedDict):
        def __setitem__(self, timestamp, value):
            super().__setitem__(timestamp, queue.Queue())
            self[timestamp].put(value)
            if timestamp < list(self.keys())[-1]:
                self.clear()
                self.update(dict(sorted(self.items()))) 

    def __init__(self):
        # Queue of commands that are not scheduled at a specific
        # time. These commands can be executed on the next emulator
        # cycle.
        self._now = queue.Queue()

        # Command queues indexed by execution timestamp. These
        # commands need to be executed at or before the specified
        # time.
        self._timeslots = self.TimeDict()

    def put(self, command):
        if command.time is None:
            self._now.put(command)
        else:
            self._timeslots[command.time] = command

    def get(self, timestamp):
        # Return the first available command. If the non-scheduled
        # queue has pending commands, return those first.
        if not self._now.empty():
            return self._now.get()
        if self._timeslots:
            # Get all timestamps on or before 'timestamp'.
            stamps = [x for x in self._timeslots if x <= timestamp]
            if not stamps:
                return None
            first = stamps[0]
            command = self._timeslots[first].get()
            if self._timeslots[first].empty():
                self._timeslots.popitem(first)
            return command
        return None

    def get_all(self, timestamp):
        # Iterate over all commands scheduled on or before 'timestamp'
        command = self.get(timestamp)
        while command is not None:
            yield command
            command = self.get(timestamp)
        return None

def load_mcu(name, config):
    try:
        module = importlib.import_module(f"vortex.controllers.{name}")
    except ImportError as e:
        logging.error(f"Failed to create {name} controller: {str(e)}")
        return None
    module_object = getattr(module, "__controller__", None)
    if module_object:
        return module_object(config)
    return None

class Emulator:
    def __init__(self, controller, frontend, machine_config):
        self._command_queue = CommandQueue()
        self._kinematics = kinematics.Kinematics(machine_config.kinematics,
                                                 controller)
        self._frontend = frontend
        self._frontend.set_command_queue(self._command_queue)
        self._frontend.set_kinematics_model(self._kinematics)
        controller_params = controller.get_params()
        self._frontend.set_controller_data(controller_params)
        self._frontend.set_controller_functions(
            {"reset": controller.reset,
             "query": controller.query_objects,
             "event_register": controller.event_register,
             "event_unregister": controller.event_unregister})
        self._controller = controller
        self._scheduled_queue = ScheduleQueue()
        self._run_emulation = True
        self._frequency = 0
        self._monitor = None

    def set_frequency(self, frequency=0):
        if (frequency / MHZ2HZ) > 10:
            logging.warning("Frequency greater than 10MHz may result in inaccurate timing")
        self._frequency = frequency or self._controller.FREQUENCY

    def start_monitor(self):
        self._monitor = monitor.MonitorServer(self._controller, self._command_queue)
        self._monitor.start()

    def register_event(self, object_type, event_type, object_name, handler):
        return self._controller.event_register(object_type, event_type,
                                               object_name, handler)
    
    def unregister_event(self, object_type, event_type, object_name):
        return self._controller.event_unregister(object_type, event_type, object_name)
    
    def run(self):
        try:
           self._controller.start(self._frequency, self._command_complete)
        except VortexCoreError as e:
            print(str(e))
            self._controller.stop()
            return
        self._frontend.run()
        while self._run_emulation:
            timestep = self._controller.get_clock_ticks()
            self._schedule_commands(timestep)
            self._process_schedule(timestep)
    
    def stop(self):
        if self._monitor is not None:
            self._monitor.stop()
        self._frontend.stop()
        self._controller.stop()

    def _schedule_commands(self, timestep):
        if not self._command_queue.empty():
            cmd = self._command_queue.get()
            cmd.time = timestep
            self._scheduled_queue.put(cmd)

    def _command_complete(self, command_id, result):
        self._frontend.complete_command(command_id, result)

    def _process_schedule(self, timestamp):
        for command in self._scheduled_queue.get_all(timestamp):
            ret = self._controller.exec_command(command.id, command.obj_id,
                                                command.cmd_id, command.opts)
            if ret:
                logging.error(f"Failed to execute command: {strerror(abs(ret))}")
                self._frontend.complete_command(command.id, ret)
            time.sleep(0.001)
            

        
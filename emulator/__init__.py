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
import logging
import inspect
import importlib
import time
from os import strerror
from re import search
from vortex.lib.constants import *
from vortex.core import VortexCoreError
import vortex.emulator.monitor as monitor
import vortex.emulator.kinematics as kinematics

__all__ = ["Emulator"]


class EmulatorError(Exception): pass

def load_mcu(name, config):
    # Get base controller class
    base_module = importlib.import_module("vortex.controllers")
    base_class = getattr(base_module, "Controller")
    try:
        module = importlib.import_module(f"vortex.controllers.{name}")
    except ImportError as e:
        logging.error(f"Failed to create {name} controller: {str(e)}")
        return None
    members = inspect.getmembers(module, inspect.isclass)
    controllers = [x[1] for x in members if issubclass(x[1], base_class) and \
                   x[1] is not base_class]
    if len(controllers) == 0:
        raise EmulatorError(f"Controller '{name}' not found")
    if len(controllers) > 1:
        raise EmulatorError(f"Too many controller objects in '{name}'")
    return controllers[0](config)

class Emulator:
    def __init__(self, frontend, config):
        self._command_queue = frontend.get_queue()
        machine = config.get_machine_config()
        self._controller = load_mcu(machine.controller, config)
        self._kinematics = kinematics.Kinematics(machine.kinematics,
                                                 self._controller)
        self._frontend = frontend
        self._frontend.set_kinematics_model(self._kinematics)
        controller_params = self._controller.get_params()
        self._frontend.set_controller_data(controller_params)
        self._frontend.set_controller_interface(interface)

        self._run_emulation = True
        self._frequency = 0
        self._monitor = None

    def set_frequency(self, frequency=0):
        if isinstance(frequency, str):
            i = search(r'\d*', frequency).end()
            frequency, order = int(frequency[:i]), frequency[i:].upper()
            if order.lower() != "hz":
                logging.debug(f"{frequency} {order}, {order}2HZ, {eval(f"{order}2HZ")}")
                frequency = frequency * eval(f"{order}2HZ")
        if (frequency / MHZ2HZ) > 10:
            logging.warning("Frequency greater than 10MHz may result in inaccurate timing")
        self._frequency = frequency

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
        self._frontend.set_emulation_frequency(self._controller.get_frequency())
        self._frontend.run()
        while self._run_emulation:
            command = self._command_queue.get()
            ret = self._controller.exec_command(command.id, command.obj_id,
                                                command.cmd_id, command.opts)
            if ret:
                logging.error(f"Failed to execute command: {strerror(abs(ret))}")
                self._frontend.complete_command(command.id, ret)
    
    def stop(self):
        if self._monitor is not None:
            self._monitor.stop()
        self._frontend.stop()
        self._controller.stop()

    def _command_complete(self, command_id, result):
        self._frontend.complete_command(command_id, result)
        
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
import fcntl
import inspect
import importlib
from os import strerror, getpid, unlink
from queue import ShutDown
import vortex.core.lib.logging as logging
from vortex.lib.utils import parse_frequency
from vortex.core import VortexCoreError
import vortex.emulator.remote.server as remote_server
import vortex.core.kinematics as kinematics
import vortex.frontends as frontends

__all__ = ["Emulator", "EmulatorError"]

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
    PID_LOCK_PATH = "/tmp/vortex.pid.lock"

    def __init__(self, config, frontend, sequential=False):
        self.lock_fd = open(self.PID_LOCK_PATH, 'w')
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise EmulatorError(f"Emulator already running, PID lock file exists: {self.PID_LOCK_PATH}")
        self.lock_fd.write(str(getpid()))

        machine = config.get_machine_config()
        kin = config.get_kinematics_config()
        self._kinematics = kinematics.Kinematics(kin)
        self._controller = load_mcu(machine.controller, config)
        self._frontend = frontends.create_frontend(frontend)
        if self._frontend is None:
            raise EmulatorError(f"Failed to create frontend '{frontend}'")
        self._frontend.set_sequential_mode(sequential)
        self._frontend.set_kinematics_model(self._kinematics)
        self._frontend.set_controller(self._controller)
        self._command_queue = self._frontend.get_queue()
        self._run_emulation = True
        self._timer_frequency = 0
        self._update_frequency = 0
        self._controller_thread_priority = False
        self._server = None

    def set_frequency(self, timer_frequency=0, update_frequency=0):
        self._timer_frequency = parse_frequency(timer_frequency)
        self._update_frequency = parse_frequency(update_frequency)

    def set_thread_priority_change(self, priority):
        self._controller_thread_priority = priority

    def get_controller(self):
        return self._controller

    def get_frontend(self):
        return self._frontend

    def start_remote_server(self):
        self._server = remote_server.RemoteServer(self)
        self._server.start()

    def register_event(self, object_type, event_type, object_name, handler):
        return self._controller.event_register(object_type, event_type,
                                               object_name, handler)
    
    def unregister_event(self, object_type, event_type, object_name):
        return self._controller.event_unregister(object_type, event_type, object_name)
    
    def run(self):
        try:
           self._controller.start(self._timer_frequency, self._update_frequency,
                                  self._controller_thread_priority,
                                  self._frontend.queue_virtual_object_command,
                                  self._frontend.complete_command)
        except VortexCoreError as e:
            logging.error(str(e))
            self._controller.stop()
            return
        self._frontend.set_emulation_frequency(self._timer_frequency)
        self._frontend.run()
        while self._run_emulation:
            try:
                command = self._command_queue.get()
            except ShutDown:
                continue
            ret = self._controller.exec_command(command.id, command.obj_id,
                                                command.cmd_id, command.opts)
            if ret:
                logging.error(f"Failed to execute command: {strerror(abs(ret))}")
                self._frontend.complete_command(command.id, ret)
    
    def stop(self):
        if self._server is not None:
            self._server.stop()
        self._frontend.stop()
        self._controller.stop()
        fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        self.lock_fd.close()
        unlink(self.PID_LOCK_PATH)

    def __del__(self):
        if hasattr(self, "_controller") and self._controller:
            self._controller.cleanup()
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
import threading
import os
import importlib
import logging
from lib import ctypes_helpers
from controllers.types import ModuleTypes

class BaseFrontend:
    def __init__(self, event_register=None, event_unregister=None):
        self._raw_controller_params = {}
        self._cmd_id_2_cmd = {x: {} for x in ModuleTypes}
        self._cmd_name_2_id = {x: {} for x in ModuleTypes}
        self._obj_name_2_id = {x: {} for x in ModuleTypes}
        self._obj_id_2_name = {x: {} for x in ModuleTypes}
        self._command_completion = {}
        self._run = True
        self._run_sequential = False
        if event_register:
            self.event_register = event_register
        else:
            self.event_register = lambda a, b, c, d: False
        if event_unregister:
            self.event_unregister = event_unregister
        else:
            self.event_unregister = lambda a, b, c, d: False

    def _find_object(self, klass, *seq):
        for s in seq:
            if s in self._obj_name_2_id[klass]:
                return s
        return None

    def set_command_queue(self, queue):
        self._queue = queue

    def set_controller_data(self, data):
        self._raw_controller_params = data
        commands = data.get("commands", None)
        if commands:
            for klass in commands:
                for cmd in commands[klass]:
                    self._cmd_name_2_id[klass][cmd[1]] = (cmd[0], cmd[2], cmd[3])
                    self._cmd_id_2_cmd[klass][cmd[0]] = (cmd[1], cmd[2], cmd[3])
        objects = data.get("objects", None)
        if objects:
            for klass in objects:
                for obj in objects[klass]:
                    self._obj_name_2_id[klass][obj[0]] = obj[1]
                    self._obj_id_2_name[klass][obj[1]] = obj[0]

    def get_object_id(self, klass, name):
        return self._obj_name_2_id[klass].get(name, None)

    def get_object_name(self, klass, id):
        return self._obj_id_2_name[klass].get(id, None)

    def get_object_command(self, klass, name):
        cmd = self._cmd_name_2_id[klass].get(name, None)
        if cmd is None:
            return self._cmd_id_2_cmd[klass].get(name, None)

    def run(self):
        self._thread = threading.Thread(None, self._process_commands, "frontend")
        self._run = True
        self._thread.start()
    
    def stop(self):
        self._run = False
        self._thread.join()

    def set_sequential_mode(self, mode):
        self._run_sequential = mode

    def _process_commands(self):
        while self._run:
            continue

    def convert_opts(self, klass, cmd_id, opts):
        if not self._cmd_id_2_cmd[klass][cmd_id][1]:
            return None
        opts_struct = self._cmd_id_2_cmd[klass][cmd_id][1]()
        opts_defaults = self._cmd_id_2_cmd[klass][cmd_id][2]
        try:
            ctypes_helpers.fill_ctypes_struct(opts_struct, opts)
        except TypeError as e:
            logging.error(f"Failed to convert command options: {str(e)}")
        return opts_struct
    
    def queue_command(self, klass, object, cmd, opts, timestamp):
        if isinstance(cmd, str):
            cmd_id = self._cmd_name_2_id[klass].get(cmd, (None,))[0]
            if cmd_id is None:
                return False
        obj_id = self._obj_name_2_id[klass].get(object, None)
        if obj_id is None:
            return False
        opts = {_o:_v for _o, _v in (s.split('=') for s in opts.split(','))} if opts else {}
        opts = self.convert_opts(klass, cmd_id, opts)
        if not self._run_sequential or not self._command_completion:
            cmd_id, cmd = self._queue.queue_command(obj_id, cmd_id, opts, timestamp)
            self._command_completion[cmd_id] = cmd
            return True
        return False

    def complete_command(self, id, result):
        self._command_completion.pop(id)

    def event_handler(self, event, owner, timestamp, *args):
        pass
    
def create_frontend(name):
    if not os.path.isdir(f"./frontends/{name}"):
        return None
    module = importlib.import_module(f"frontends.{name}")
    if hasattr(module, "create") and callable(module.create):
        frontend = module.create()
        return frontend
    return None
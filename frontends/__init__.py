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
import threading
import importlib
import select
import os
import time
import pickle
import threading
import vortex.lib.logging as logging
from vortex.core import ObjectTypes
from vortex.frontends.lib import create_pty
from vortex.frontends.queues import CommandQueue
from vortex.frontends.proto import *

class BaseFrontend:
    PIPE_PATH = "/tmp/vortex"
    def __init__(self, queue_size=0):
        self._raw_controller_params = {}
        self._cmd_id_2_cmd = {x: {} for x in ObjectTypes}
        self._cmd_name_2_id = {x: {} for x in ObjectTypes}
        self._obj_name_2_id = {x: {} for x in ObjectTypes}
        self._obj_id_2_name = {x: {} for x in ObjectTypes}
        self._command_completion = {}
        self._command_completion_lock = threading.Lock()
        self._command_results = {}
        self._run = True
        self._run_sequential = False
        self._queue = CommandQueue(queue_size)
        self._thread = None
        self.is_reset = False
        self.event_register = lambda a, b, c, d: False
        self.event_unregister = lambda a, b, c, d: False
        self.emulation_frequency = 0
        try:
            os.mkfifo(self.PIPE_PATH)
        except FileExistsError:
            pass
        mfd, sfd = create_pty(self.PIPE_PATH)
        self._fd = os.fdopen(mfd, 'wb+', buffering=0)
        self._poll = select.poll()
        self._poll.register(self._fd, select.POLLIN|select.POLLHUP)
        self._command_id_queue = []
        self.log = logging.getLogger("vortex.frontend")

    def set_controller(self, controller):
        self._controller = controller
        self.timers = self._controller.timers
        self._set_controller_data()

    # Implement these as class methods so subclasses can
    # override them. If they they are implemented as class
    # attributes, any subclass lookup of those methods will
    # return the base class method instead of the overriden
    # one.
    def reset(self, *args, **kwargs):
        return self._controller.reset(*args, **kwargs)

    def query(self, *args, **kwargs):
        return self._controller.query_objects(*args, **kwargs)

    def query_hw(self, *args, **kwargs):
        return self._controller.get_hw_param(*args, **kwargs)

    def get_controller_clock_ticks(self, *args, **kwargs):
        return self._controller.get_clock_ticks(*args, **kwargs)

    def get_controller_runtime(self, *args, **kwargs):
        return self._controller.get_runtime(*args, **kwargs)

    def event_register(self, *args, **kwargs):
        return self._controller.event_register(*args, **kwargs)

    def event_unregister(self, *args, **kwargs):
        return self._controller.event_unregister(*args, **kwargs)

    def _set_controller_data(self):
        commands = self._controller.get_param("commands")
        if commands:
            for klass in commands:
                for cmd in commands[klass]:
                    self._cmd_name_2_id[klass][cmd[1]] = cmd[0]
                    self._cmd_id_2_cmd[klass][cmd[0]] = cmd[1]
        objects = self._controller.get_param("objects")
        if objects:
            for klass in objects:
                for obj in objects[klass]:
                    self._obj_name_2_id[klass][obj[0]] = obj[1]
                    self._obj_id_2_name[klass][obj[1]] = obj[0]

    def set_emulation_frequency(self, frequency):
        self.emulation_frequency = frequency

    def set_kinematics_model(self, model):
        self.kinematics = model

    def get_queue(self):
        return self._queue
    
    def find_object(self, klass, *seq):
        '''Find object ID for object of type klass.
        The object name can be any of the values in seq.'''
        if len(seq) == 0:
            return self._obj_name_2_id[klass]
        for s in seq:
            if s in self._obj_name_2_id[klass]:
                return s
        return None

    def query_object(self, objects):
        return self.query(objects)

    def get_object_id(self, klass, name):
        return self._obj_name_2_id[klass].get(name, None)

    def get_object_name(self, klass, id):
        return self._obj_id_2_name[klass].get(id, None)

    def get_object_command(self, klass, name):
        cmd = self._cmd_name_2_id[klass].get(name, None)
        if cmd is None:
            return self._cmd_id_2_cmd[klass].get(name, None)

    def get_object_name_set(self, klass):
        return list(self._obj_id_2_name[klass].values())

    def get_object_id_set(self, klass):
        return list(self._obj_name_2_id[klass].values())

    def run(self):
        self._thread = threading.Thread(None, self._run_command_loop,
                                         "frontend")
        self._run = True
        self._thread.start()
    
    def stop(self):
        if self._thread:
            self._run = False
            self._thread.join()
        cmds = list(self._command_completion.keys())
        for cmd in cmds:
            self.complete_command(cmd, -1)

    def set_sequential_mode(self, mode):
        self._run_sequential = mode

    def _process_command(self, cmd):
        return

    def _run_command_loop(self):
        while self._run:
            events = self._poll.poll(0.1)
            if not events or self._fd.fileno() not in [e[0] for e in events]:
                continue
            event = [e for e in events if e[0] == self._fd.fileno()]
            if not (event[0][1] & select.POLLIN):
                continue
            data = self._fd.read()
            self._process_command(data)

    def wait_for_command(self, cmd_set):
        if isinstance(cmd_set, int):
            cmd_set = [cmd_set]
        if not isinstance(cmd_set, (list, tuple, set)):
            cmd_set = list(cmd_set)
        cmd_set = set(cmd_set)
        with self._command_completion_lock:
            completed = set(self._command_results.keys())
        while not cmd_set & completed:
            time.sleep(0.01)
            with self._command_completion_lock:
                completed = set(self._command_results.keys())
        return [self._command_results[i] for i in cmd_set]

    def queue_command(self, klass, object, cmd, opts, callback=None):
        if self.is_reset:
            return False
        if isinstance(object, int):
            if object not in self._obj_id_2_name[klass]:
                return False
            obj_id = object
        elif isinstance(object, str):
            obj_id = self._obj_name_2_id[klass].get(object, None)
            if obj_id is None:
                return False
        else:
            return False
        if isinstance(cmd, int):
            if cmd not in self._cmd_id_2_cmd[klass]:
                return False
            cmd_id = cmd
        elif isinstance(cmd, str):
            cmd_id = self._cmd_name_2_id[klass].get(cmd, None)
            if cmd_id is None:
                return False
        else:
            return False
        if isinstance(opts, str):
            opts = {_o:_v for _o, _v in (s.split('=') for s in opts.split(','))} if opts else {}
        elif not isinstance(opts, dict):
            return False
        self.log.debug(f"Submitting command: {self.get_object_name(klass, obj_id)} {cmd_id} {opts}")
        with self._command_completion_lock:
            cmd_id, cmd = self._queue.queue_command(obj_id, cmd_id, opts)
            self.log.debug(f"Command ID:{cmd_id}")
            self._command_completion[cmd_id] = (cmd, callback)
        if self._run_sequential:
            self.wait_for_command(cmd_id)
        return cmd_id

    def complete_command(self, id, result):
        with self._command_completion_lock:
            self.log.debug(f"Completing command: {id} {result}")
            cmd, callback = self._command_completion.pop(id)
            if callback is not None:
                callback(id, result)
            else:
                self._command_results[id] = result

    def respond(self, code, data):
        response = Response(code, data)
        response = pickle.dumps(response)
        self._fd.write(b'#$' + response + b'$#')
        
    def __del__(self):
        self._fd.close()
        os.unlink(self.PIPE_PATH)
    
def create_frontend(name):
    try:
        module = importlib.import_module(f"vortex.frontends.{name}")
        if hasattr(module, "create") and callable(module.create):
            frontend = module.create()
            return frontend
    except ImportError as e:
        logging.error(f"Failed to create frontend '{name}': {str(e)}")
    return None
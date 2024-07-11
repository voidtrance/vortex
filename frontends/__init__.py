import threading
import os
import importlib
from controllers.types import ModuleTypes

class BaseFrontend:
    def __init__(self):
        self._raw_controller_params = {}
        self._cmd_id_2_cmd = {x: {} for x in ModuleTypes}
        self._cmd_name_2_id = {x: {} for x in ModuleTypes}
        self._obj_name_2_id = {x: {} for x in ModuleTypes}
        self._run = True

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
    
    def run(self):
        self._thread = threading.Thread(None, self._process_commands, "frontend")
        self._run = True
        self._thread.start()
    
    def stop(self):
        self._run = False
        self._thread.join()

    def _process_commands(self):
        while self._run:
            continue

    def convert_opts(self, klass, cmd_id, opts):
        opts_struct = self._cmd_id_2_cmd[klass][cmd_id][1]()
        opts_defaults = self._cmd_id_2_cmd[klass][cmd_id][2]
        for i, (name, ftype) in enumerate(opts_struct._fields_):
            value = opts.get(name, opts_defaults[i])
            value_type = type(opts_defaults[i])
            if value_type == str:
                value = bytes(value, "ascii")
            else:
                value = value_type(value)
            setattr(opts_struct, name, value)
        return opts_struct
    
    def queue_command(self, klass, cmd, name, opts, timestamp):
        cmd_id = self._cmd_name_2_id[klass].get(cmd, (None,))[0]
        if cmd_id is None:
            return
        obj_id = self._obj_name_2_id[klass].get(name, None)
        if obj_id is None:
            return
        klass_cmds = self._cmd_name_2_id.get(klass, {})
        if cmd not in klass_cmds:
            return
        opts = {_o:_v for _o, _v in (s.split('=') for s in opts.split(','))} if opts else {}
        opts = self.convert_opts(klass, cmd_id, opts)
        self._command_id_queue.append(self._queue.queue_command(obj_id, cmd_id,
                                                                opts, timestamp))

    def complete_command(self, id, result):
        pass

    def event_handler(self, event, owner, timestamp, *args):
        print(event, owner.config.name, timestamp)
    
def create_frontend(name):
    if not os.path.isfile(f"./frontends/{name}.py"):
        return None
    module = importlib.import_module(f"frontends.{name}")
    if hasattr(module, "create") and callable(module.create):
        frontend = module.create()
        return frontend
    return None
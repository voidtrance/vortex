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
import importlib
import pathlib
import logging
import ctypes
import vortex.core as core
import inspect
from collections import namedtuple
from vortex.controllers.types import ModuleTypes
import vortex.lib.ctypes_helpers

class Counter:
    def __init__(self):
        self.x = 0
    def count(self):
        y = self.x
        self.x += 1
        return y
    
class Pins:
    __c = Counter()
    def __init__(self, name, start, end=None):
        self._name = name
        if isinstance(start, (tuple, list)):
            self._start = range[0]
            self._end = range[1]
        else:
            if end is None:
                raise ValueError("'end' is None")
            self._start = start
            self._end = end
    @property
    def name(self):
        return self._name
    def __iter__(self):
        for pin in range(self._start, self._end+1):
            yield (f"{self._name}{pin}", self.__c.count())

class _Objects:
    _frozen = False
    def __init__(self):
        self.__objects = {type: [] for type in ModuleTypes}
        self._frozen = True
    def __setattr__(self, name, value):
        if not self._frozen:
            super().__setattr__(name, value)
        else:
            raise TypeError(f"{self:r} is a frozen class")
    def __iter__(self):
        for klass, objects in self.__objects.items():
            for name, id in objects:
                yield klass, name, id
    def iter_klass(self, klass):
        for name, id in self.__objects[klass]:
            yield klass, name, id
    def add_object(self, klass, name, id):
        if id in self.__objects[klass]:
            raise ValueError("Object ID already present")
        self.__objects[klass].append((name, id))

class ObjectLookUp:
    def __init__(self, object_list):
        self.__dict__.update({"__objects": object_list})
    def __setattr__(self, name, value):
        raise TypeError(f"{self:r} is a frozen class")
    def __iter__(self):
        for klass, name, id in getattr(self, "__objects"):
            yield klass, name, id
    def object_by_id(self, obj_id):
        for klass, name, id in getattr(self, "__objects"):
            if id == obj_id:
                return klass, name
        return None, None
    def object_by_name(self, name, klass=None):
        generator = getattr(self, "__objects").iter_klass(klass) \
            if klass is not None else getattr(self, "__objects")
        for k, n, i in generator:
            if name == n:
                return k, n, i

class Controller(core.VortexCore):
    PINS = []
    _libc = ctypes.CDLL("libc.so.6")
    _Command = namedtuple("Command", ['id', 'name', 'opts', 'defaults'])
    def __init__(self, config):
        root = logging.getLogger()
        debug_level = root.getEffectiveLevel()
        if debug_level <= logging.DEBUG:
            logging.warning("With DEBUG and higher logging levels")
            logging.warning("controller timing will be imprecise!")
        super().__init__(debug=debug_level)
        self._objects = _Objects()
        self.objects = ObjectLookUp(self._objects)
        self.object_defs = {x: None for x in ModuleTypes}
        self._virtual_objects = {}
        self._completion_callback = None
        self._load_objects(config)
        if not self.init_objects():
            raise core.VortexCoreError("Failed to initialize objects.")
    def _load_virtual_objects(self):
        vobjs = []
        mod_base = "vortex.controllers.objects"
        vobj_base = importlib.import_module(f"{mod_base}.vobj_base")
        base_class = getattr(vobj_base, "VirtualObjectBase")
        vobj_path = pathlib.Path(__file__).parent / "objects"
        for filename in vobj_path.glob("*.py"):
            vobj_module = importlib.import_module(f"{mod_base}.{filename.stem}")
            members = inspect.getmembers(vobj_module, inspect.isclass)
            for name, member in members:
                if issubclass(member, base_class) and member is not base_class:
                    vobjs.append(member)
        return vobjs
    def _load_objects(self, config):
        module = importlib.import_module("vortex.controllers.objects.object_defs")
        base = getattr(module, "ObjectDef")
        members = inspect.getmembers(module, inspect.isclass)
        members = [x for x in members if x[1] is not base]
        object_defs = [klass for name, klass in members \
                       if issubclass(klass, base)]
        available_objects = [x() for x in object_defs]
        self.object_defs.update({ModuleTypes[x.__class__.__name__.lower()]: (False, x) \
                                    for x in available_objects})
        available_objects = self._load_virtual_objects()
        self.object_defs.update({x.type: (True, x) for x in available_objects})
        for klass, name, options in config:
            if klass not in self.object_defs or \
                self.object_defs[klass] is None:
                logging.error(f"No definitions for klass '{klass}'")
                continue
            if self.object_defs[klass][0] is True:
                obj = self.object_defs[klass][1](options, self.objects, self.query_objects)
                self._virtual_objects[id(obj)] = obj
                self._objects.add_object(klass, name, id(obj))
                continue
            obj_conf = self.object_defs[klass][1].config()
            try:
                vortex.lib.ctypes_helpers.fill_ctypes_struct(obj_conf, vars(options))
            except TypeError as e:
                logging.error("Could not create object configuration!")
                logging.error(f"   klass={klass}, name={name}: {str(e)}")
                continue
            object_id = self.create_object(klass, name, ctypes.addressof(obj_conf))
            self._objects.add_object(klass, name, object_id)
    def get_params(self):
        params = {'commands': [], 'pins': [], "objects": [], "events": {}}
        cmds = {x: [] for x in ModuleTypes}
        for klass in ModuleTypes:
            if self.object_defs[klass] is not None:
                cmds[klass] += self.object_defs[klass][1].commands
        params["commands"] = cmds
        pins = []
        for pin_set in self.PINS:
            pins += [x for x in pin_set]
        params["pins"] = pins
        objects = {x: [] for x in ModuleTypes}
        for klass, name, id in self.objects:
            objects[klass].append((name, id))
        params["objects"] = objects
        events = {x: {} for x in ModuleTypes}
        for klass in ModuleTypes:
            if self.object_defs[klass] is not None:
                events[klass] = {e: s for e, s in self.object_defs[klass][1].events.items()}
        params["events"] = events
        return params
    def query_objects(self, objects):
        virtual_objects = []
        for id in objects:
            klass, name = self.objects.object_by_id(id)
            if klass and self.object_defs[klass][0]:
                virtual_objects.append(id)
        objects = [x for x in objects if x not in virtual_objects]
        _status = self.get_status(objects)
        object_status = dict.fromkeys(objects, None)
        for i, id  in enumerate(objects):
            klass, name = self.objects.object_by_id(id)
            if not klass:
                logging.error(f"Could not find klass for object id {id}")
                continue
            if _status[i]:
                status_struct = self.object_defs[klass][1].state
                status = ctypes.cast(_status[i], ctypes.POINTER(status_struct)).contents
                object_status[id] = vortex.lib.ctypes_helpers.parse_ctypes_struct(status)
                self._libc.free(ctypes.c_void_p(_status[i]))
            else:
                object_status[id] = None
        for id in virtual_objects:
            object_status[id] = self._virtual_objects[id].get_status()
        return object_status
    def _convert_opts(self, klass, cmd_id, opts):
        klass_def = self.object_defs[klass]
        if klass_def[0] is False:
            commands = klass_def[1].commands
            # The presence of cmd_id in the list of commands should
            # have been verified by now in the frontend.
            command = self._Command(*[x for x in commands if x[0] == cmd_id][0])
            if command.opts is None:
                return None
            opts_struct = command.opts()
            # TODO: Use the default values to initial the structs
            opts_defaults = command.defaults
            try:
                vortex.lib.ctypes_helpers.fill_ctypes_struct(opts_struct, opts)
            except TypeError as e:
                logging.error(f"Failed to convert command options: {str(e)}")
            return opts_struct
        return opts
    def exec_command(self, command_id, object_id, subcommand_id, opts=None):
        klass, name = self.objects.object_by_id(object_id)
        args = 0
        if self.object_defs[klass][0] is False:
            if opts is not None:
                opts = self._convert_opts(klass, subcommand_id, opts)
                if opts is not None:
                    args = ctypes.addressof(opts)
                return super().exec_command(command_id, object_id, subcommand_id, args)
        else:
            return self._virtual_objects[object_id].exec_command(command_id,
                                                                 subcommand_id, opts)
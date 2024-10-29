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
import vortex.core
import vortex.lib.ctypes_helpers
from vortex.lib.utils import Counter

class PinError(Exception): pass
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
        self._value = self._start
    @property
    def name(self):
        return self._name
    @property
    def min(self):
        return self._start
    @property
    def max(self):
        return self._end
    def next(self):
        if self._value >= self._end:
            raise PinError("Value exceeds pin range")
        pin = f"{self.name}{self._value}"
        self._value = self.__c.next()
        return pin
    def __len__(self):
        return self._end - self._start + 1
    def __iter__(self):
        self.__c.reset()
        for pin in range(self._start, self._end+1):
            yield (f"{self._name}{pin}", self.__c.next())

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
                yield Object(klass, name, id)
    def iter_klass(self, klass):
        for name, id in self.__objects[klass]:
            yield Object(klass, name, id)
    def add_object(self, klass, name, id):
        if id in self.__objects[klass]:
            raise ValueError("Object ID already present")
        self.__objects[klass].append((name, id))

Object = namedtuple("Object", ["klass", "name", "id"])
class ObjectKlassInvalid(Exception): pass
class ObjectNotFound(Exception): pass
class ObjectLookUp:
    def __init__(self, object_list):
        self.__dict__.update({"__objects": object_list})
    def __setattr__(self, name, value):
        raise TypeError(f"{self:r} is a frozen class")
    def __iter__(self):
        for klass, name, id in getattr(self, "__objects"):
            yield Object(klass, name, id)
    def object_by_klass(self, klass):
        return list(getattr(self, "__objects").iter_klass(klass))
    def object_by_id(self, obj_id):
        for klass, name, id in getattr(self, "__objects"):
            if id == obj_id:
                return Object(klass, name, id)
        return Object(None, None, None)
    def object_by_name(self, name, klass=None):
        if klass and klass in ModuleTypes:
            generator = getattr(self, "__objects").iter_klass(klass)
        elif klass is not None:
            generator = getattr(self, "__objects")
        else:
            raise ObjectKlassInvalid(f"Klass '{klass}' is invalid")
        for k, n, i in generator:
            if name == n:
                return Object(k, n, i)
        raise ObjectNotFound(f"Object '{name}' of klass '{klass}' not found")

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
        self._pin_index = 0
        self._objects = _Objects()
        self.objects = ObjectLookUp(self._objects)
        self.object_defs = {x: None for x in ModuleTypes}
        self.frequency = self.FREQUENCY
        self._virtual_objects = {}
        self._completion_callback = None
        self._event_handlers = {}
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
        self.object_defs.update({ModuleTypes[x.__class__.__name__.lower()]: x \
                                    for x in available_objects})
        available_objects = self._load_virtual_objects()
        self.object_defs.update({x.type: x for x in available_objects})
        for klass, name, options in config:
            if klass not in self.object_defs or \
                self.object_defs[klass] is None:
                logging.error(f"No definitions for klass '{klass}'")
                continue
            self._assign_pins(klass, options)
            if self.object_defs[klass].virtual:
                obj = self.object_defs[klass](options, self.objects,
                                              self.query_objects,
                                              self.virtual_command_complete,
                                              self.event_submit)
                object_id = self.register_virtual_object(klass, name)
                obj._id = object_id
                self._virtual_objects[object_id] = obj
            else:
                obj_conf = self.object_defs[klass].config()
                if klass == ModuleTypes.THERMISTOR:
                    options.adc_max = self.ADC_MAX
                try:
                    vortex.lib.ctypes_helpers.fill_ctypes_struct(obj_conf, vars(options))
                except TypeError as e:
                    logging.error("Could not create object configuration!")
                    logging.error(f"   klass={klass}, name={name}: {str(e)}")
                    continue
                object_id = self.create_object(klass, name, ctypes.addressof(obj_conf))
            self._objects.add_object(klass, name, object_id)
    def _get_next_pin(self):
        pin_set = self.PINS[self._pin_index]
        try:
            pin = pin_set.next()
        except PinError:
            self._pin_index += 1
            if self._pin_index >= len(self.PINS):
                return None
            pin = self._get_next_pin()
        return pin
    def _assign_pins(self, klass, options):
        if klass == ModuleTypes.STEPPER:
            options.enable_pin = self._get_next_pin()
            options.dir_pin = self._get_next_pin()
            options.step_pin = self._get_next_pin()
        elif klass in (ModuleTypes.THERMISTOR, ModuleTypes.HEATER,
                       ModuleTypes.ENDSTOP, ModuleTypes.PROBE,
                       ModuleTypes.DIGITAL_PIN, ModuleTypes.PWM_PIN):
            options.pin = self._get_next_pin()
    def start(self, update_frequency, completion_cb):
        self._completion_callback = completion_cb
        super().start(self.FREQUENCY, update_frequency, self._completion_callback)
    def get_frequency(self):
        return self.FREQUENCY
    def virtual_command_complete(self, cmd_id, status):
        self._completion_callback(cmd_id, status)
    def get_params(self):
        params = {'commands': [], 'pins': [], "objects": [], "events": {}}
        cmds = {x: [] for x in ModuleTypes}
        for klass in ModuleTypes:
            if self.object_defs[klass] is not None:
                cmds[klass] += self.object_defs[klass].commands
        params["commands"] = cmds
        params["pins"] = self.PINS
        objects = {x: [] for x in ModuleTypes}
        for klass, name, id in self.objects:
            objects[klass].append((name, id))
        params["objects"] = objects
        events = {x: {} for x in ModuleTypes}
        for klass in ModuleTypes:
            if self.object_defs[klass] is not None:
                if not self.object_defs[klass].virtual:
                    events[klass] = \
                        {e: s for e, s in self.object_defs[klass].events.items()}
                else:
                    events[klass] = \
                        {e: None for e in self.object_defs[klass].events}
        params["events"] = events
        return params
    def lookup_object(self, klass, name):
        return self.objects.object_by_name(name, klass)
    def lookup_objects(self, klass):
        return self.objects.object_by_klass(klass)
    def query_objects(self, objects):
        virtual_objects = []
        for id in objects:
            object = self.objects.object_by_id(id)
            if object.klass and self.object_defs[object.klass].virtual:
                virtual_objects.append(id)
        objects = [x for x in objects if x not in virtual_objects]
        _status = self.get_status(objects)
        object_status = dict.fromkeys(objects, None)
        for i, id  in enumerate(objects):
            object = self.objects.object_by_id(id)
            if not object.klass:
                logging.error(f"Could not find klass for object id {id}")
                continue
            if _status[i]:
                status_struct = self.object_defs[object.klass].state
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
        if not klass_def.virtual:
            commands = klass_def.commands
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
        for opt, value in opts.items():
            if value.lower() in ("true", "false"):
                value = True if value.lower() == "true" else False
            else:
                try:
                    value = float(value)
                except ValueError:
                    try:
                        value = int(value)
                    except ValueError:
                        pass
            opts[opt] = value
        return opts
    def exec_command(self, command_id, object_id, subcommand_id, opts=None):
        object = self.objects.object_by_id(object_id)
        if opts is not None:
            opts = self._convert_opts(object.klass, subcommand_id, opts)
        if not self.object_defs[object.klass].virtual:
            args = 0
            if opts is not None:
                args = ctypes.addressof(opts)
            return super().exec_command(command_id, object_id, subcommand_id, args)
        else:
            return self._virtual_objects[object_id].exec_command(command_id,
                                                                 subcommand_id, opts)
    def event_register(self, object_type, event_type, object_name, handler):
        if not super().event_register(object_type, event_type, object_name,
                                      self._event_handler):
            return False
        self._event_handlers[(object_type, event_type, object_name)] = handler
        return True
    def event_unregister(self, object_type, event_type, object_name):
        self._event_handlers.pop((object_type, event_type, object_name))
        return super().event_unregister(object_type, event_type, object_name)
    def _find_event_data(self, klass, event):
        for e, s in self.object_defs[klass].events.items():
            if e == event:
                return s
        return None
    def _event_handler(self, klass, object_name, event_type, data):
        handler = self._event_handlers.get((klass, event_type, object_name),
                                            None)
        if handler is None:
            return
        if self.object_defs[klass].virtual:
            handler(klass, event_type, object_name, data)
            return
        event_data_def = self._find_event_data(klass, event_type)
        if event_data_def is None:
            raise vortex.core.VortexCoreError(f"Unknown event type {event_type}")
        pointer = ctypes.cast(data, ctypes.POINTER(event_data_def))
        content = vortex.lib.ctypes_helpers.parse_ctypes_struct(pointer.contents)
        handler(klass, event_type, object_name, content)

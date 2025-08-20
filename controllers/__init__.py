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
import importlib
import pathlib
import ctypes
import vortex.core as core
import inspect
from pathlib import PosixPath
from collections import namedtuple
import vortex.lib.ctypes_helpers
from vortex.lib.utils import Counter, parse_frequency
from vortex.lib.constants import hz_to_nsec, khz_to_hz
from vortex.controllers.objects.virtual.base import VirtualObjectError
import vortex.core.lib.logging as logging
import vortex.controllers.timers as timers

class PinError(Exception): pass

class Pins:
    def __init__(self, name, start, end=None):
        self._name = name
        if isinstance(start, (tuple, list)):
            self._start = start[0]
            self._end = start[1]
        else:
            if end is None:
                raise ValueError("'end' is None")
            self._start = start
            self._end = end
        self.__c = Counter(self._start)
        self.__used = []
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
        value = self.__c.next()
        while value in self.__used:
            value = self.__c.next()
        if value > self._end:
            raise PinError("Value exceeds pin range")
        return f"{self.name}{value}"
    def use(self, pin):
        if not pin.startswith(self._name):
            raise PinError("Pin does not belong to set")
        if pin not in self:
            raise PinError("Pin not in set")
        if pin in self.__used:
            raise PinError(f"Pin {pin} already used")
        self.__used.append(pin)
    def __len__(self):
        return self._end - self._start + 1
    def __iter__(self):
        self.__c.reset()
        for _ in range(len(self)):
            yield self.next()
        self.__c.reset()
    def __contains__(self, item):
        return item in list(self)
    def __str__(self):
        return f"{self._name}({self._start}-{self._end})"
    def __repr__(self):
        return str(self)

class _Objects:
    _frozen = False
    def __init__(self):
        self.__objects = {type: [] for type in core.ObjectKlass}
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
        if klass and klass in core.ObjectKlass:
            generator = getattr(self, "__objects").iter_klass(klass)
        elif klass is not None:
            generator = getattr(self, "__objects")
        else:
            raise ObjectKlassInvalid(f"Klass '{klass}' is invalid")
        for k, n, i in generator:
            if name == n:
                return Object(k, n, i)
        raise ObjectNotFound(f"Object '{name}' of klass '{klass}' not found")

def get_host_cpu_frequency(type="cur"):
    if type not in ("cur", "min", "max"):
        raise ValueError("CPU frequency type should be 'cur', 'min', or 'max'")
    frequency = 0
    path = PosixPath(f'/sys/devices/system/cpu/cpu0/cpufreq')
    if type == "cur":
        filename = path / "scaling_cur_freq"
    else:
        filename = path / f"cpuinfo_{type}_freq"
    if filename.exists():
        with open(filename, 'r') as fd:
            frequency = int(fd.read().strip())
        frequency = khz_to_hz(frequency)
    if frequency == 0:
        # Try getting the frequency from sysfs
        filename = PosixPath('/proc/cpuinfo')
        with open(filename, 'r') as fd:
            for line in fd:
                if line.startswith("cpu MHz"):
                    freq = line.split(':')[-1].strip() + 'MHZ'
                    try:
                        frequency = parse_frequency(freq)
                    except NameError:
                        pass
                    break
    return frequency


class Controller(core.VortexCore):
    PINS = []
    SPI = []
    STEPPER_COUNT = 0
    THERMISTOR_COUNT = 0
    PWM_PIN_COUNT = 0
    DIGITAL_PIN_COUNT = 0
    ENDSTOP_COUNT = 0
    PROBE_COUNT = 0
    HEATER_COUNT = 0
    FAN_COUNT = 0
    DISPLAY_COUNT = 0
    ENCODER_COUNT = 0
    DIGITAL_PIN_COUNT = 0
    FREQUENCY = 0
    ARCH = 0
    _libc = ctypes.CDLL("libc.so.6")
    _Command = namedtuple("Command", ['id', 'name', 'opts', 'data', 'defaults'])

    def __init__(self, config):
        self.log = logging.getLogger("vortex.core")
        debug_level = logging.get_level()
        if debug_level <= logging.DEBUG:
            self.log.warning("With DEBUG and higher logging levels")
            self.log.warning("controller timing will be imprecise!")
        super().__init__(debug=debug_level)
        self._pin_index = 0
        self._objects = _Objects()
        self.objects = ObjectLookUp(self._objects)
        self.object_defs = {x: None for x in core.ObjectKlass}
        self.object_factory = {x: None for x in core.ObjectKlass}
        self._virtual_objects = {}
        self._completion_callback = None
        self._event_handlers = {}
        self._timer_factory = timers.Factory(self)
        self._exec_cmd_map = {}
        self._free_object_counts = dict.fromkeys(core.ObjectKlass, 0)
        for klass in (core.ObjectKlass.AXIS, core.ObjectKlass.TOOLHEAD):
            self._free_object_counts.pop(klass)
        for klass in core.ObjectKlass:
            if hasattr(self, f"{klass}_COUNT"):
                self._free_object_counts[klass] = getattr(self, f"{klass}_COUNT")
        self._load_objects(config)
        if not self.init_objects():
            raise core.VortexCoreError("Failed to initialize objects.")

    @property
    def timers(self):
        return self._timer_factory

    def _load_virtual_objects(self):
        vobjs = {}
        mod_base = "vortex.controllers.objects.virtual"
        vobj_base = importlib.import_module(f"{mod_base}.base")
        base_class = getattr(vobj_base, "VirtualObjectBase")
        vobj_path = pathlib.Path(__file__).parent / "objects/virtual"
        for filename in vobj_path.glob("*.py"):
            vobj_module = importlib.import_module(f"{mod_base}.{filename.stem}")
            members = inspect.getmembers(vobj_module, inspect.isclass)
            for name, member in members:
                if issubclass(member, base_class) and member is not base_class:
                    if member.type in vobjs:
                        funcs = inspect.getmembers(vobj_module, inspect.isfunction)
                        match = [f for n, f in funcs if n.lower() == f"{member.type}factory".lower()]
                        if match:
                            vobjs[member.type] = match[0]
                        else:
                            raise core.VortexCoreError(f"Duplicate virtual object type '{member.type}'")
                    else:
                        vobjs[member.type] = member
        return vobjs

    def _load_objects(self, config):
        module = importlib.import_module("vortex.controllers.objects.object_defs")
        base = getattr(module, "ObjectDef")
        members = inspect.getmembers(module, inspect.isclass)
        members = [x for x in members if x[1] is not base]
        object_factory = [klass for name, klass in members \
                       if issubclass(klass, base)]
        available_objects = [x() for x in object_factory]
        self.object_factory.update({core.ObjectKlass[x.__class__.__name__.upper()]: x \
                                    for x in available_objects})
        available_objects = self._load_virtual_objects()
        self.object_factory.update(available_objects)
        for klass, name, options in config:
            if klass not in self.object_factory or \
                self.object_factory[klass] is None:
                self.log.error(f"No definitions for klass '{klass}'")
                continue
            self.log.verbose(f"Creating object {klass}:{name}")
            res, pin = self._verify_pins(options)
            if res != True:
                raise core.VortexCoreError(f"Unknown pin {pin} for object {name}")
            if klass in self._free_object_counts:
                if not self._free_object_counts[klass]:
                    raise core.VortexCoreError(f"Cannot create object {name} of type {klass}."
                                                " Object count exceeded.")
                self._free_object_counts[klass] -= 1
            if getattr(self.object_factory[klass], "virtual", False) or \
                inspect.isfunction(self.object_factory[klass]):
                try:
                    obj = self.object_factory[klass](options, self.objects,
                                                     self.query_objects,
                                                     self.virtual_command_complete,
                                                     self.event_submit)
                except VirtualObjectError as error:
                    self.log.error(f"Failed to create virtual object {klass}:{name}: {error}")
                    continue
                self.object_defs[klass] = obj.__class__
                object_id = self.register_virtual_object(klass, name, self.vobj_cmd_exec,
                                                         self.vobj_get_state)
                if object_id == vortex.core.INVALID_OBJECT_ID:
                    self.log.error(f"Failed to register virtual object {klass}:{name}")
                    continue
                obj._id = object_id
                self._virtual_objects[object_id] = obj
            else:
                self.object_defs[klass] = self.object_factory[klass]
                obj_conf = self.object_factory[klass].config()
                if klass == core.ObjectKlass.THERMISTOR:
                    options.adc_max = self.ADC_MAX
                if klass == core.ObjectKlass.PWM:
                    options.pwm_max = self.PWM_MAX
                options = vortex.lib.ctypes_helpers.expand_substruct_config(options,
                                                                            obj_conf)
                try:
                    vortex.lib.ctypes_helpers.fill_ctypes_struct(obj_conf, options)
                except TypeError as e:
                    self.log.error("Could not create object configuration!")
                    self.log.error(f"   klass={klass}, name={name}: {str(e)}")
                    continue
                if logging.get_level() == logging.DEBUG:
                    vortex.lib.ctypes_helpers.show_struct(obj_conf, self.log.debug)
                object_id = self.create_object(klass, name, ctypes.addressof(obj_conf))
            self.log.debug(f"Object {klass}:{name} created: {object_id}")
            self._objects.add_object(klass, name, object_id)

    def _verify_pins(self, config):
        for name, value in vars(config).items():
            if "pin" in name:
                pin_set = [p for p in self.PINS if value in p]
                if not pin_set or len(pin_set) > 1:
                    return False, value
                try:
                    pin_set[0].use(value)
                except PinError as e:
                    raise core.VortexCoreError(e)
        return True, None

    def start(self, timer_frequency, update_frequency, set_priority, vobj_exec_cb, completion_cb):
        self._virtual_object_exec_command = vobj_exec_cb
        self._completion_callback = completion_cb
        cur_freq = get_host_cpu_frequency()
        max_freq = get_host_cpu_frequency("max")
        tick_ns = hz_to_nsec(self.FREQUENCY)
        timer_frequency = int(timer_frequency)
        self.log.info(f"Controller frequency: {self.FREQUENCY} Hz, tick is {round(tick_ns, 3)} ns")
        self.log.info(f"Current CPU frequency: {cur_freq} Hz, max {max_freq} Hz")
        self.log.info(f"Emulation running at {timer_frequency} Hz ({hz_to_nsec(timer_frequency)} ns / tick)")
        super().start(self.ARCH, self.FREQUENCY, timer_frequency, update_frequency,
                      self.command_complete, set_priority)

    def get_frequency(self):
        return self.FREQUENCY

    def command_complete(self, cmd_id, status, data_addr):
        self.log.debug(f"controller complete {cmd_id}={status}, data_addr={data_addr}")
        obj_id, obj_cmd = self._exec_cmd_map.pop(cmd_id, (None, None))
        obj = self.objects.object_by_id(obj_id)
        data = None
        if data_addr:
            cmd = [x for x in self.object_factory[obj.klass].commands if x[0] == obj_cmd]
            if not cmd or len(cmd) != 1:
                self._completion_callback(cmd_id, -255)
            cmd_data = cmd[0][3]
            if cmd_data is not None and issubclass(cmd_data, ctypes.Structure):
                data = ctypes.cast(data_addr, ctypes.POINTER(cmd_data)).contents
                data = vortex.lib.ctypes_helpers.parse_ctypes_struct(data)
        self._completion_callback(cmd_id, status, data)

    def virtual_command_complete(self, cmd_id, status, data=None):
        self.log.debug(f"controller virtual complete: {cmd_id}={status}, data={data}")
        self._completion_callback(cmd_id, status, data)

    def virtual_object_opts_convert(self, obj_id, obj_cmd_id, opts):
        if obj_id not in self._virtual_objects:
            return -1
        vobj = self._virtual_objects[obj_id]
        args_struct = [cmd[2] for cmd in vobj.commands if cmd[0] == obj_cmd_id]
        if not args_struct:
            raise -1
        args_ptr = ctypes.cast(opts, ctypes.POINTER(args_struct[0])).contents
        args = vortex.lib.ctypes_helpers.parse_ctypes_struct(args_ptr)
        return args

    def vobj_cmd_exec(self, klass, obj_id, cmd_id, cmd, opts):
        return self._virtual_object_exec_command(klass, obj_id, cmd_id, cmd, opts)

    def vobj_get_state(self, klass, obj_id):
        if obj_id not in self._virtual_objects:
            return 0
        state = self._virtual_objects[obj_id].get_status()
        struct = self._virtual_objects[obj_id].state()
        vortex.lib.ctypes_helpers.fill_ctypes_struct(struct, state)
        return struct

    def get_param(self, param):
        if param == "commands":
            cmds = {x: [] for x in core.ObjectKlass}
            for klass in core.ObjectKlass:
                if self.object_defs[klass] is not None:
                    cmds[klass] += self.object_defs[klass].commands
            return cmds
        elif param == "objects":
            objects = {x: [] for x in core.ObjectKlass}
            for klass, name, id in self.objects:
                status = self.query_objects([id])
                pins = {}
                for key, value in status[id].items():
                    if "pin" in key:
                        pins[key] = value
                objects[klass].append((name, id, pins))
            return objects
        elif param == "events":
            events = {x: {} for x in core.ObjectKlass}
            for klass in core.ObjectKlass:
                if self.object_defs[klass] is not None:
                    if not self.object_defs[klass].virtual:
                        events[klass] = \
                            {e: s for e, s in self.object_defs[klass].events.items()}
                    else:
                        events[klass] = \
                            {e: None for e in self.object_defs[klass].events}
            return events
        else:
            raise core.VortexCoreError(f"Unknown parameter '{param}'")

    def get_hw_param(self, param):
        if hasattr(self, param):
            return getattr(self, param)
        raise core.VortexCoreError(f"Unknown HW parameter '{param}'")

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
                self.log.error(f"Could not find klass for object id {id}")
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
        commands = klass_def.commands
        # The presence of cmd_id in the list of commands should
        # have been verified by now in the frontend.
        command = self._Command(*[x for x in commands if x[0] == cmd_id][0])
        if command.opts is None:
            return None
        opts_struct = command.opts()
        # Set command options default values
        opts_defaults = command.defaults
        opts_dict = {}
        for i, option in enumerate(opts_struct._fields_):
            opts_dict[option[0]] = opts_defaults[i]
        opts_dict.update(opts)
        try:
            vortex.lib.ctypes_helpers.fill_ctypes_struct(opts_struct, opts_dict)
        except TypeError as e:
            self.log.error(f"Failed to convert command options: {str(e)}")
        if not klass_def.virtual:
            return opts_struct
        else:
            return vortex.lib.ctypes_helpers.parse_ctypes_struct(opts_struct)

    def exec_command(self, command_id, object_id, subcommand_id, opts=None):
        object = self.objects.object_by_id(object_id)
        self.log.debug(f"controller executing command {command_id}: {object.id} {object.klass} {object.name}")
        if opts is not None:
            opts = self._convert_opts(object.klass, subcommand_id, opts)
        if not self.object_defs[object.klass].virtual:
            args = 0
            if opts is not None:
                args = ctypes.addressof(opts)
            # Store the command into the command map so if the object
            # completes the command quickly (before it is stored if it were
            # stored after), the complete callback can successfully find it.
            #
            # this thread                      core completion thread
            # -------------------------------------------------------
            # self.exec_command()
            #    object->exec_command()
            #       CORE_CMD_COMPLETE()
            #                                  core_process_completions()
            #                                     complete_cm()
            #                                        self.command_complete()
            #       return
            #    return
            self._exec_cmd_map[command_id] = (object_id, subcommand_id)
            ret = super().exec_command(command_id, object_id, subcommand_id, args)
            self.log.debug(f"result: {command_id}={ret}")
            if ret:
                self._exec_cmd_map.pop(command_id)
            return ret
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

    def reset(self, objects=[]):
        if not objects:
            objects = list(self.objects)
        _objects = objects[:]
        for obj in objects:
            if obj.id in self._virtual_objects:
                self.log.debug(f"Resetting virtual object {obj.name} ({obj.id})")
                self._virtual_objects[obj.id].reset()
                _objects.remove(obj)
        return super().reset([obj.id for obj in _objects])

    def cleanup(self):
        for obj in self._virtual_objects.values():
            del obj
        self._virtual_objects.clear()
        for klass in core.ObjectKlass:
            for obj in self.objects.object_by_klass(klass):
                self.destory_object(obj.id)

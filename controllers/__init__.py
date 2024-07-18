# gEmulator - GCode machine emulator
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
import controllers.core
import importlib
import logging
import ctypes
from controllers.types import ModuleTypes

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

class Objects:
    def __init__(self):
        self.__objects = {type: [] for type in ModuleTypes}
    def add_object(self, klass, name, id):
        if id in self.__objects[klass]:
            raise ValueError("Object ID already present")
        self.__objects[klass].append((name, id))
    def __iter__(self):
        for klass in self.__objects:
            for name, id in self.__objects[klass]:
                yield klass, name, id
    def iter_klass(self, klass):
        for name, id in self.__objects[klass]:
            yield klass, name, id

class Controller(controllers.core.Core):
    PINS = []
    def __init__(self, config):
        super().__init__()
        self.objects = Objects()
        self.object_defs = {x: None for x in ModuleTypes}
        self._completion_callback = None
        self._load_objects(config)
        if not self.init_objects():
            raise controllers.core.CoreError("Failed to initialize objects.")
    def _load_objects(self, config):
        module = importlib.import_module("controllers.objects.object_defs")
        object_defs = getattr(module, "__objects__")
        available_objects = [x() for x in object_defs]
        self.object_defs.update({ModuleTypes[x.__class__.__name__.lower()]: x \
                                    for x in available_objects})
        self.object_defs
        for klass, name, options in config:
            if klass not in self.object_defs or \
                self.object_defs[klass] is None:
                logging.error(f"No definitions for klass '{klass}'")
                continue
            obj_conf = self.object_defs[klass].config()
            for field in obj_conf._fields_:
                value = vars(options).get(field[0], None)
                if value is None:
                    logging.error(f"Object config missing option '{field[0]}'")
                    continue
                if field[1]._type_ == ctypes.c_char:
                    value = bytes(value, "ascii")
                setattr(obj_conf, field[0], value)
            object_id = self.create_object(klass, name, ctypes.addressof(obj_conf))
            self.objects.add_object(klass, name, object_id)
    def get_params(self):
        params = {'commands': [], 'pins': [], "objects": []}
        cmds = {x: [] for x in ModuleTypes}
        for klass in ModuleTypes:
            if self.object_defs[klass] is not None:
                cmds[klass] += self.object_defs[klass].commands                
        params["commands"] = cmds
        pins = []
        for pin_set in self.PINS:
            pins += [x for x in pin_set]
        params["pins"] = pins
        objects = {x: [] for x in ModuleTypes}
        for klass, name, id in self.objects:
            objects[klass].append((name, id))
        params["objects"] = objects
        return params

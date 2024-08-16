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
from vortex.controllers.types import ModuleTypes

class Sentinal(dict):
    def __setattr__(self, name, value):
        raise TypeError(f"{self:r} is a frozen class")

class VirtualObjectBase:
    type = ModuleTypes.NONE
    commands = []
    # Virtual objects don't have events
    events = Sentinal()
    def __init__(self, config, obj_lookup, obj_query):
        self.config = config
        self.lookup = obj_lookup
        self.query = obj_query
    def __setattr__(self, name, value):
        if name == "events":
            raise TypeError("Virtual object don't support events")
        super().__setattr__(name, value)
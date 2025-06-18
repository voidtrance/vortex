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
import enum
from argparse import Namespace

@enum.unique
class RequestType(enum.IntEnum):
    KLASS_LIST = enum.auto()
    OBJECT_LIST = enum.auto()
    OBJECT_STATUS = enum.auto()
    OBJECT_COMMANDS = enum.auto()
    OBJECT_EVENTS = enum.auto()
    EMULATION_PAUSE = enum.auto()
    EMULATION_RESUME = enum.auto()
    EMULATION_RESET = enum.auto()
    EMULATION_PID = enum.auto()
    EXECUTE_COMMAND = enum.auto()
    COMMAND_STATUS = enum.auto()

    
class Request(Namespace):
    def __init__(self, type):
        self.type = type

class Response(Namespace):
    def __init__(self, type):
        self.type = type
        self.status = 0
        self.data = None
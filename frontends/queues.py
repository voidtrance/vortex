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
import queue
class Command:
    def __init__(self, obj_id, cmd_id, opts):
        self.obj_id, self.cmd_id, self.opts = \
            obj_id, cmd_id, opts
        self.id = id(self)
    def __str__(self):
        return f"Command({self.id}, {self.obj_id}:{self.cmd_id})"
        
class CommandQueue(queue.Queue):
    def __init__(self, maxsize=0):
        super().__init__(maxsize)
        self.__cmd_count = 0
        self.__max_size = maxsize
    def put(self, command):
        if not isinstance(command, Command):
            raise ValueError("'command' is not a Command instance")
        super().put(command)
        self.__cmd_count += 1
        return command.id
    def get(self, block=True, timeout=None):
        cmd = super().get(block, timeout)
        self.__cmd_count -= 1
        return cmd
    def queue_command(self, obj_id, cmd_id, opts):
        cmd = Command(obj_id, cmd_id, opts)
        return (self.put(cmd), cmd)
    def clear(self):
        self.shutdown(True)
        self.__cmd_count = 0
        self.is_shutdown = False
    @property
    def size(self):
        return self.__cmd_count
    @property
    def max_size(self):
        return self.__max_size

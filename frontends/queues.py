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
from threading import Lock
from collections import namedtuple
import vortex.core.lib.logging as logging

class Command:
    def __init__(self, obj_id, cmd_id, opts, callback):
        self.obj_id = obj_id
        self.cmd_id = cmd_id
        self.opts = opts
        self.callback = callback
        self.id = id(self)

    def __str__(self):
        return f"Command({self.id}, {self.obj_id}:{self.cmd_id})"

QueueCompletion = namedtuple("QueueCompletion", ["command", "result", "data"])
Completion = namedtuple("Completion", ["id", "result", "data"])

log = logging.getLogger("vortex.queue")

class CommandQueue(queue.Queue):
    def __init__(self, maxsize=0):
        super().__init__(maxsize)
        self.__cmd_count = 0
        self.__max_size = maxsize
        self.__lock = Lock()
        self.__cmd_queue = {}
        self.__comp_queue = {}

    def put(self, command):
        if not isinstance(command, Command):
            raise ValueError("'command' is not a Command instance")
        with self.__lock:
            super().put(command)
            self.__cmd_queue[command.id] = command
        self.__cmd_count += 1
        return command.id

    def get(self, block=True, timeout=None):
        cmd = super().get(block, timeout)
        self.__cmd_count -= 1
        return cmd

    def queue_command(self, obj_id, cmd_id, opts, callback=None):
        log.debug(f"Submitting command: {obj_id}: {cmd_id} {opts}")
        cmd = Command(obj_id, cmd_id, opts, callback)
        self.put(cmd)
        log.debug(f"Command queued as {cmd.id}")
        return cmd.id, cmd

    def complete_command(self, cmd_id, result, data=None):
        log.debug(f"Command {cmd_id} competed with {result}")
        with self.__lock:
            cmd = self.__cmd_queue.pop(cmd_id)

        if cmd.callback:
            cmd.callback(cmd_id, result, data)
        else:
            with self.__lock:
                self.__comp_queue[cmd_id] = QueueCompletion(cmd, result, data)

    def wait_for_command(self, cmd_ids):
        if isinstance(cmd_ids, int):
            cmd_set = [cmd_ids]
        if not isinstance(cmd_ids, (list, tuple, set)):
            cmd_set = list(cmd_set)
        cmd_set = set(cmd_set)
        comp_set = set()
        completed = []
        while not cmd_set & comp_set:
            with self.__lock:
                comp_set = set(self.__comp_queue.keys())
                for cmd_id in (cmd_set & comp_set):
                    completion = self.__comp_queue.pop(cmd_id)
                    completed.append(Completion(completion.command.id,
                                                completion.result,
                                                completion.data))
        return completed

    def clear(self):
        self.shutdown(True)
        with self.__lock:
            for cmd in self.get():
                if cmd.callback:
                    cmd.callback(cmd.id, -1, None)
        self.__cmd_count = 0
        self.is_shutdown = False

    @property
    def size(self):
        return self.__cmd_count

    @property
    def max_size(self):
        return self.__max_size

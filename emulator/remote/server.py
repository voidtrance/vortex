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
import socket
import pickle
import os
import errno
import ctypes
import vortex.emulator.remote.api as api
from vortex.core import ObjectTypes
from vortex.lib.ctypes_helpers import is_simple_char_array, is_simple

class RemoteThread(threading.Thread):
    def __init__(self, index, connection, emulation):
        self._conn = connection
        self._emulation = emulation
        self._controller = emulation.get_controller()
        self._frontend = emulation.get_frontend()
        self._do_run = False
        self._objects = {}
        self._klasses = {x: str(x) for x in ObjectTypes}
        for klass, name, id in self._controller.objects:
            if klass not in self._objects:
                self._objects[klass] = []
            self._objects[klass].append({"name":name, "id":id})
        super().__init__(None, None, f"vortex-remote-{index}")
    def _validate_reuest(self, request):
        if request.type == api.RequestType.OBJECT_STATUS:
            if not hasattr(request, "objects") or \
                not isinstance(request.objects, list):
                return False
            for obj in request.objects:
                if not isinstance(obj, int):
                    return False
        elif request.type == api.RequestType.OBJECT_COMMANDS:
            if not hasattr(request, "klass") or request.klass not in self._klasses:
                return False
        elif request.type == api.RequestType.OBJECT_EVENTS:
            if not hasattr(request, "klass") or request.klass not in self._klasses:
                return False
        elif request.type == api.RequestType.EXECUTE_COMMAND:
            if not hasattr(request, "klass") or request.klass not in self._klasses or \
                not hasattr(request, "object") or not isinstance(request.object, int) or\
                not hasattr(request, "command") or not isinstance(request.command, int) or \
                not hasattr(request, "opts") or not isinstance(request.opts, dict):
                return False
        elif request.type == api.RequestType.COMMAND_STATUS:
            if not hasattr(request, "command") or not isinstance(request.command, int):
                return False
        return True
    def _process_request(self, request):
        if not self._validate_reuest(request):
            response = api.Response(request.type)
            response.status = errno.EINVAL
            response.data = None
            return response
        response = api.Response(request.type)
        response.status = 0
        response.data = None
        if request.type == api.RequestType.KLASS_LIST:
            response.data = self._klasses
        elif request.type == api.RequestType.OBJECT_LIST:
            response.data = self.get_object_list()
        elif request.type == api.RequestType.OBJECT_STATUS:
            response.data = self._controller.query_objects(request.objects)
        elif request.type == api.RequestType.OBJECT_COMMANDS:
            response.data = self.get_object_commands(request.klass)
        elif request.type == api.RequestType.OBJECT_EVENTS:
            response.data = self.get_object_events(request.klass)
        elif request.type == api.RequestType.EMULATION_PAUSE:
            self._controller.pause(True)
        elif request.type == api.RequestType.EMULATION_RESUME:
            self._controller.pause(False)
        elif request.type == api.RequestType.EMULATION_RESET:
            self._controller.reset()
        elif request.type == api.RequestType.EMULATION_PID:
            response.data = os.getpid()
        elif request.type == api.RequestType.EXECUTE_COMMAND:
            cmd_id = self._frontend.queue_command(request.klass, request.object,
                                                 request.command, request.opts,
                                                 self._cmd_complete)
            if cmd_id is False:
                response.status = errno.EBADR
            else:
                response.data = cmd_id
        elif request.type == api.RequestType.COMMAND_STATUS:
            status = self._frontend.wait_for_command(request.command)
        return response
    def _cmd_complete(self, cmd_id, result):
        return
    def run(self):
        self._do_run = True
        data = b""
        while self._do_run:
            try:
                data += self._conn.recv(1024)
            except ConnectionResetError:
                break
            if not data:
                self._conn.close()
                break
            while data:
                try:
                    request = pickle.loads(data)
                except EOFError:
                    break
                response = self._process_request(request)
                self._conn.sendall(pickle.dumps(response))
                l = len(pickle.dumps(request))
                data = data[l:]
    def get_object_list(self):
        return self._objects
    def get_object_commands(self, klass):
        commands = self._controller.get_param("commands")
        _commands = {}
        # Convert all HW object command options to types
        for klass in commands:
            _commands[klass] = []
            for cmd in commands[klass]:
                if cmd[2] is None:
                    continue
                if isinstance(cmd[2], list):
                    _commands[klass].append(cmd)
                elif issubclass(cmd[2], ctypes.Structure):
                    _opts = []
                    for name, _type in cmd[2]._fields_:
                        if issubclass(_type, (ctypes.c_int, ctypes.c_uint,
                                             ctypes.c_int16, ctypes.c_uint16,
                                             ctypes.c_int32, ctypes.c_uint32,
                                             ctypes.c_int64, ctypes.c_uint64)):
                            _opts.append((name, int))
                        elif issubclass(_type, (ctypes.c_float, ctypes.c_double)):
                            _opts.append((name, float))
                        elif issubclass(_type, ctypes.c_char) or is_simple_char_array(type):
                            _opts.append((name, str))
                        elif issubclass(_type, ctypes.c_bool):
                            _opts.append((name, bool))
                    _commands[klass].append((cmd[0], cmd[1], _opts, cmd[3]))
        return _commands
    def get_object_events(self, klass):
        events = {}
        if klass is None:
            klass_set = ObjectTypes
        else:
            klass_set = [klass]
        params = self._controller.get_param("events")
        for klass in klass_set:
            if klass not in params:
                continue
            event_set = params[klass]
            events[klass] = []
            for event, args in event_set.items():
                if args is not None:
                    args = [x[0] for x in args._fields_]
                events[klass].append({"id": event,
                                      "args": [] if args is None else args})
        return events
    def stop(self):
        try:
            self._conn.shutdown(socket.SHUT_RDWR)
            self._conn.close()
        except OSError:
            pass

class RemoteServer(threading.Thread):
    path = "/tmp/vortex-remote"
    def __init__(self, emulator, max_conns=5):
        if os.path.exists(self.path):
            os.unlink(self.path)
        self._emulation = emulator
        self._max_connections = max_conns
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(self.path)
        self._monitor_run = False
        self._threads = []
        super().__init__(None, None, "vortex-remote-server")

    def run(self):
        self._socket.listen(self._max_connections)
        self._monitor_run = True
        child_count = 0
        while self._monitor_run:
            try:
                _conn, address = self._socket.accept()
                thread = RemoteThread(child_count, _conn, self._emulation)
                thread.start()
                self._threads.append(thread)
                child_count += 1
            except OSError:
                continue

    def stop(self):
        self._monitor_run = False
        for thread in self._threads:
            thread.stop()
            thread.join()
        self._socket.shutdown(socket.SHUT_RDWR)
        self._socket.close()
        self.join()
        os.unlink(self.path)

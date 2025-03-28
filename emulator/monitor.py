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
from vortex.core import ObjectTypes

class MonitorThread(threading.Thread):
    def __init__(self, index, connection, controller):
        self._conn = connection
        self._controller = controller
        self._do_run = False
        self._objects = {}
        self._klasses = {x: str(x) for x in ObjectTypes}
        for klass, name, id in self._controller.objects:
            if klass not in self._objects:
                self._objects[klass] = []
            self._objects[klass].append({"name":name, "id":id})
        super().__init__(None, None, f"vortex-monitor-{index}")
    def run(self):
        self._do_run = True
        while self._do_run:
            try:
                data = self._conn.recv(1024)
            except ConnectionResetError:
                break
            if not data:
                self._conn.close()
                break
            request = pickle.loads(data)
            if request["request"] == "object_list":
                response = self.get_object_list()
            elif request["request"] == "query":
                response = self.query_objects(request["objects"])
            elif request["request"] == "commands":
                response = self.get_object_commands(request.get("klass", None))
            elif request["request"] == "events":
                response = self.get_object_events(request.get("klass", None))
            elif request["request"] == "pause":
                self._controller.pause(request["action"])
                response = True
            elif request["request"] == "get_pid":
                response = os.getpid()
            else:
                continue
            self._conn.sendall(pickle.dumps(response))
    def get_object_list(self):
        return {"klass": self._klasses, "objects": self._objects}
    
    def query_objects(self, obj_list):
        obj_list = [int(x) for x in obj_list]
        status = self._controller.query_objects(obj_list)
        return status

    def get_object_commands(self, klass):
        commands = {}
        params = self._controller.get_params()
        if klass is None:
            klass_set = ObjectTypes
        else:
            klass_set = [klass]
        for klass in klass_set:
            if klass not in params["commands"]:
                continue
            command_set = params["commands"][klass]
            commands[klass] = []
            for command in command_set:
                if command[2] is None:
                    args = []
                elif isinstance(command[2], list):
                    args = command[2]
                else:
                    args = [x[0] for x in command[2]._fields_]
                commands[klass].append({"id": command[0],
                                        "name": command[1],
                                        "args": args,
                                        "defaults": command[3]})
        return commands

    def get_object_events(self, klass):
        events = {}
        params = self._controller.get_params()
        if klass is None:
            klass_set = ObjectTypes
        else:
            klass_set = [klass]
        for klass in klass_set:
            if klass not in params["events"]:
                continue
            event_set = params["events"][klass]
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

class MonitorServer(threading.Thread):
    path = "/tmp/vortex_monitor"
    def __init__(self, controller, queue, max_conns=5):
        if os.path.exists(self.path):
            os.unlink(self.path)
        self._controller = controller
        self._max_connections = max_conns
        self._queue = queue
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(self.path)
        self._monitor_run = False
        self._threads = []
        super().__init__(None, None, "vortex-monitor")

    def run(self):
        self._socket.listen(self._max_connections)
        self._monitor_run = True
        child_count = 0
        while self._monitor_run:
            try:
                _conn, address = self._socket.accept()
                thread = MonitorThread(child_count, _conn, self._controller)
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

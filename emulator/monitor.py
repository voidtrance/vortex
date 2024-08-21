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
import threading
import socket
import pickle
import os
from vortex.controllers.types import ModuleTypes

class MonitorServer(threading.Thread):
    path = "/tmp/vortex_monitor"
    def __init__(self, controller, queue):
        if os.path.exists(self.path):
            os.unlink(self.path)
        self._controller = controller
        self._queue = queue
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.bind(self.path)
        self._monitor_run = False
        self._conn = None
        super().__init__(None, None, "vortex-monitor")

    def run(self):
        self._socket.listen(1)
        self._monitor_run = True

        while self._monitor_run:
            try:
                self._conn, address = self._socket.accept()
            except OSError:
                continue
            while True:
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
                elif request["request"] == "pause":
                    self._controller.pause(request["action"])
                    response = True
                else:
                    continue
                self._conn.sendall(pickle.dumps(response))

    def stop(self):
        self._monitor_run = False
        self._socket.shutdown(socket.SHUT_RDWR)
        self._socket.close()
        if self._conn:
            try:
                self._conn.shutdown(socket.SHUT_RDWR)
                self._conn.close()
            except OSError:
                pass
        self.join()
        os.unlink(self.path)

    def get_object_list(self):
        objects = {}
        klasses = {x: str(x) for x in ModuleTypes}
        for klass, name, id in self._controller.objects:
            if klass not in objects:
                objects[klass] = []
            objects[klass].append({"name":name, "id":id})
        return {"klass": klasses, "objects": objects}
    
    def query_objects(self, obj_list):
        obj_list = [int(x) for x in obj_list]
        status = self._controller.query_objects(obj_list)
        return status
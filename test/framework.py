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
import os
import sys
import time
import fcntl
import queue
import socket
import pickle
import inspect
import subprocess
import threading
from socket import MSG_DONTWAIT
from vortex.emulator import config
from vortex.lib.ext_enum import ExtIntEnum, auto
from vortex.frontends.proto import *

VORTEX_PATH = "/tmp/vortex"
VORTEX_SOCKET_PATH = "/tmp/vortex_monitor"

class Logger:
    def __init__(self, log_writer):
        self._level = 0
        self._writer = log_writer
    def set_level(self, level):
        self._level = level
    def log(self, level, fmt, *args):
        if level <= self._level:
            msg = f"{time.time()} {fmt}"
            if args:
                msg = msg % args
            print(msg, file=sys.stderr)
            self._writer(msg + "\n")

class Color(ExtIntEnum):
    RED    = (auto(), '\33[31m')
    GREEN  = (auto(), '\33[32m')
    YELLOW = (auto(), '\33[33m')
    BLUE   = (auto(), '\33[34m')
    VIOLET = (auto(), '\33[35m')
    BEIGE  = (auto(), '\33[36m')
    WHITE  = (auto(), '\33[37m')
    END    = (auto(), '\33[0m')

class TestStatus(ExtIntEnum):
    FAIL = (auto(), f"{Color.RED}FAIL{Color.END}")
    PASS = (auto(), f"{Color.GREEN}PASS{Color.END}")
    WAIVE = (auto(), f"{Color.BLUE}WAIVE{Color.END}")

class TestFramework:
    def __init__(self, config_file, frontend="direct", controller="stm32f4",
                 logfile=None):
        self._config_file = config_file
        self._config = config.Configuration()
        self._config.read(config_file)
        self._frontend = frontend
        self._controller = controller
        self._logger = Logger(self._write_logfile)
        self._emulator = None
        self._klasses = []
        self._objects = {}
        self._collect = False
        self._collector = None
        self._commands = queue.Queue()
        self._complete = {}
        self._current_test = None
        self._logfile = logfile
        self._logfile_lock = threading.Lock()
        self._emulation_frequency = 200 # Hz

    @property
    def controller(self):
        return self._controller

    @property
    def frontend(self):
        return self._frontend

    def set_log_level(self, level=0):
        self._logger.set_level(level)

    def logging_enabled(self):
        return self._logfile is not None

    def log(self, level, fmt, *args):
        self._logger.log(level, fmt, *args)

    def warning(self, fmt, *args):
        self._logger.log(0, f"{Color.YELLOW}WARNING:{Color.END} {fmt}", *args)

    def error(self, fmt, *args):
        self._logger.log(0, f"{Color.RED}ERROR:{Color.END} {fmt}", *args)

    def begin(self, test_name):
        self._current_test = test_name
        print(f"Running test '{self._current_test}'...", end=" ", flush=True)
        self._write_logfile("=" * 30 + "\n")
        self._write_logfile(f"Running test '{self._current_test}\n")

    def passed(self, msg=None):
        msg = f"{Color.GREEN}PASS{Color.END}" + ((" " + msg) if msg else "")
        print(msg)
        self._write_logfile(f"Test '{self._current_test}: PASS\n")
        self._current_test = None
        return TestStatus.PASS

    def failed(self, msg=None):
        msg = f"{Color.RED}FAIL{Color.END}" + ((" " + msg) if msg else "")
        print(msg)
        self._write_logfile(f"Test '{self._current_test}: FAIL\n")
        self._current_test = None
        return TestStatus.FAIL

    def waived(self, msg=None):
        msg = f"{Color.BLUE}WAIVE{Color.RED}" + ((" " + msg) if msg else "")
        print(msg)
        self._write_logfile(f"Test '{self._current_test}: WAIVE\n")
        self._current_test = None
        return TestStatus.WAIVE

    def assertEQ(self, a, b):
        if type(a) == type(b) and a == b:
            return True
        self.log(0, f"[{self._get_caller()}] ASSERT: a != b, expected {b}, got {a}")
        return False

    def assertNE(self, a, b):
        if a != b:
            return True
        self.log(0, f"[{self._get_caller()}] ASSERT: a != b, expected {b}, got {a}")
        return False

    def assertGT(self, a, b):
        if type(a) == type(b) and a > b:
            return True
        self.log(0, f"[{self._get_caller()}] ASSERT: a <= b, expected {b}, got {a}")
        return False

    def assertGE(self, a, b):
        if type(a) == type(b) and a >= b:
            return True
        self.log(0, f"[{self._get_caller()}] ASSERT: a < b. expected {b}, got {a}")
        return False

    def assertLT(self, a, b):
        if type(a) == type(b) and a < b:
            return True
        self.log(0, f"[{self._get_caller()}] ASSERT: a >= b, expected {b}, got {a}")
        return False

    def assertLE(self, a, b):
        if type(a) == type(b) and a <= b:
            return True
        self.log(0, f"[{self._get_caller()}] ASSERT: a > b expected {b}, got {a}")
        return False

    def get_machine_config(self):
        return self._config.get_machine_config()

    def get_config_section(self, type, name):
        return self._config.get_section(type, name)

    def get_object_klasses(self):
        return self._klasses

    def get_object_klass(self, name):
        if not isinstance(name, str):
            raise TypeError("Klass name should be a string")
        return {n: v for v, n in self._klasses.items()}.get(name)

    def get_objects(self, klass=None):
        if klass is None:
            return self._objects
        if isinstance(klass, str):
            klass = {n: v for v, n in self._klasses.items()}.get(klass)
        return self._objects[klass]

    def get_status(self, objects):
        if isinstance(objects, int):
            objects = [objects]
        # Give emulator two update cycles before querying status
        # so objects can update.
        # However, logging significantly slows down the emulator
        # so in that case, give it extra long
        if self.logging_enabled:
            time.sleep(0.2)
        else:
            time.sleep(2. / self._emulation_frequency)
        return self._query("query", {"objects": objects})

    def run_command(self, cmd):
        self._frontend_fd.write(cmd.encode())
        return self._commands.get()

    def wait_for_completion(self, cmd_id):
        while cmd_id not in self._complete:
            time.sleep(0.2)
        result = self._complete.pop(cmd_id)
        return result

    def command_is_complete(self, cmd_id):
        return cmd_id in self._complete

    def _get_caller(self):
        stack = inspect.stack()
        return f"{stack[2].function}:{stack[2].lineno}"

    def _response_processor(self):
        incoming = b''
        while self._collect:
            try:
                data = self._frontend_fd.read(512)
            except OSError:
                continue
            incoming += data
            while incoming:
                if incoming[:2] != b'#$':
                    incoming = incoming[1:]
                    continue
                marker = incoming.find(b'$#')
                if marker == -1:
                    break
                response = pickle.loads(incoming[2:marker])
                incoming = incoming[marker+2:]
                if response.status != CommandStatus.COMPLETE:
                    self._commands.put(response.data)
                else:
                    self._complete[response.data.id] = response.data.status

    def _emulator_collector(self):
        fd = self._emulator.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        while self._collect:
            data = self._emulator.stdout.read()
            if data:
                self._write_logfile(data)

    def _write_logfile(self, data):
        if self._logfile is None:
            return
        if isinstance(data, str):
            data = data.encode()
        with self._logfile_lock:
            self._logfile.write(data)
            self._logfile.flush()

    def _emulator_read(self):
        response = b''
        while True:
            data = self._frontend_fd.read(512)
            if data:
                response += data
            if response:
                break
        return pickle.loads(response)

    def _launch_emulator(self):
        path = os.path.dirname(os.path.dirname(__file__))
        cmd = [os.path.join(path, "vortex.py"), "-C", self._config_file,
               "-f", self._frontend, "-c", self._controller, "-M", "-F",
               f"{self._emulation_frequency}Hz"]
        if self._logfile is not None:
            if os.path.exists(self._logfile):
                os.unlink(self._logfile)
            cmd += ["-d", "DEBUG"]
            self._logfile = open(self._logfile, "wb")
        self._logger.log(1, "Cmd: %s", " ".join(cmd))
        self._emulator = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT)
        while not os.path.exists(VORTEX_PATH) or not os.path.exists(VORTEX_SOCKET_PATH):
            time.sleep(0.5)
        self._collect = True
        self._collector = threading.Thread(None, self._emulator_collector,
                                           "emulator_collector")
        self._collector.start()
        return self._emulator

    def _connect_monitor(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(VORTEX_SOCKET_PATH)
        except (FileNotFoundError, ConnectionRefusedError) as e:
            self.error(f"Failed to connect to monitor: {str(e)}")
            return None
        return sock

    def _query(self, request, data={}):
        request = {"request": request}
        request.update(data)
        self._monitor.sendall(pickle.dumps(request))
        response = b""
        incoming = self._monitor.recv(1024)
        while incoming:
            response += incoming
            try:
                incoming = self._monitor.recv(1024, MSG_DONTWAIT)
            except BlockingIOError:
                break
        return pickle.loads(response)

    def _init_data(self):
        object_data = self._query("object_list")
        self._klasses = object_data["klass"]
        self._objects = object_data["objects"]

    def initialize(self):
        self._launch_emulator()
        self._monitor = self._connect_monitor()
        self._frontend_fd = open(VORTEX_PATH, 'wb+', buffering=0)
        self._response_parser = threading.Thread(None, self._response_processor,
                                                 "response_parser")
        self._response_parser.start()
        self._init_data()

    def terminate(self):
        self._monitor.close()
        if self._emulator:
            self._emulator.terminate()
            while self._emulator.poll() == None:
                time.sleep(0.5)
            self._collect = False
            if self._collector:
                self._collector.join()
            self._response_parser.join()
        if self._logfile:
            self._logfile.close()

    def __del__(self):
        self.terminate()
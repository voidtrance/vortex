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
import importlib
import logging
import pathlib
import subprocess
import threading
import vortex.emulator.remote.api as api
from vortex.emulator import config
from vortex.lib.ext_enum import ExtIntEnum, auto
from vortex.frontends.proto import *
from vortex.core import ObjectKlass
from testutils import TestStatus

VORTEX_PATH = "/tmp/vortex"
VORTEX_SOCKET_PATH = "/tmp/vortex-remote"

class Color(ExtIntEnum):
    RED         = (auto(), '\033[38;5;196m')
    GREEN       = (auto(), '\033[38;5;82m')
    YELLOW      = (auto(), '\033[38;5;227m')
    ORANGE      = (auto(), '\033[38;5;208m')
    BLUE        = (auto(), '\033[38;5;21m')
    CYAN        = (auto(), '\033[38;5;75m')
    VIOLET      = (auto(), '\033[38;5;129m')
    BEIGE       = (auto(), '\033[38;5;222m')
    WHITE       = (auto(), '\033[38;5;256m')
    GREY        = (auto(), '\033[38;5;247m')
    BOLD_RED    = (auto(), '\033[38;5;196;1m')
    BOLD_GREEN  = (auto(), '\033[38;5;82;1m')
    BOLD_YELLOW = (auto(), '\033[38;5;227;1m')
    BOLD_ORANGE = (auto(), '\033[38;5;208;1m')
    BOLD_BLUE   = (auto(), '\033[38;5;21;1m')
    BOLD_CYAN   = (auto(), '\033[38;5;75;1m')
    BOLD_VIOLET = (auto(), '\033[38;5;129;1m')
    BOLD_BEIGE  = (auto(), '\033[38;5;222;1m')
    BOLD_WHITE  = (auto(), '\033[38;5;256;1m')
    BOLD_GREY   = (auto(), '\033[38;5;247;1m')
    END         = (auto(), '\033[0m')

def verbose(msg, *args, **kwargs):
    if logging.root.isEnabledFor(logging.VERBOSE):
        logging.root._log(logging.VERBOSE, msg, args, **kwargs)

logging.VERBOSE = (logging.INFO + logging.DEBUG) / 2
logging.addLevelName(logging.VERBOSE, "VERBOSE")
logging.root.verbose = verbose
logging.verbose = lambda m, *a: logging.root.verbose(m, *a)

class CustomFormatter(logging.Formatter):
    FORMATS = {
        logging.DEBUG: str(Color.GREY),
        logging.VERBOSE: str(Color.GREY),
        logging.INFO: str(Color.GREY),
        logging.WARNING: str(Color.ORANGE),
        logging.ERROR: str(Color.RED),
        logging.CRITICAL: str(Color.BOLD_RED)
    }

    def format(self, record):
        s = super().format(record)
        return self.FORMATS[record.levelno] + s + str(Color.END)

class TestFramework:
    FAIL = f"{Color.RED}FAIL{Color.END}"
    PASS = f"{Color.GREEN}PASS{Color.END}"
    WAIVE = f"{Color.CYAN}WAIVE{Color.END}"

    def __init__(self, config_file, frontend="direct", controller="stm32f4",
                 logfile=None):
        self._config_file = config_file
        self._config = config.Configuration()
        self._config.read(config_file)
        self._frontend = frontend
        self._controller = controller
        self._emulator = None
        self._klasses = []
        self._objects = {}
        self._collect = False
        self._collector = None
        self._commands = queue.Queue()
        self._complete = {}
        self._ignore_completions = []
        self._logfile = logfile
        self._logfile_lock = threading.Lock()
        self._emulation_frequency = 200 # Hz
        logging.basicConfig(level=logging.DEBUG, datefmt="%Y-%m-%d %H:%M:%S")
        for h in logging.root.handlers:
            if isinstance(h, logging.StreamHandler):
                h.setFormatter(CustomFormatter("%(levelname)s: %(message)s"))

    @property
    def controller(self):
        return self._controller

    @property
    def frontend(self):
        return self._frontend

    def set_log_level(self, level=logging.INFO):
        logging.root.setLevel(level)
        pass

    def logging_enabled(self):
        return self._logfile is not None

    def begin(self, test_name, klass=None):
        print(f"Running {"object " if klass else ""}test '{test_name}'...", flush=True)
        self._write_logfile("=" * 30 + "\n")
        self._write_logfile(f"Running test '{test_name}\n")

    def end(self, test_name):
        pass

    def passed(self, name, msg=None):
        print(f"   {name}: " + self.PASS + ((" " + msg) if msg else ""))
        self._write_logfile(f"Test '{name}: PASS\n")
        return TestStatus.PASS

    def failed(self, name, msg=None):
        print(f"   {name}: " + self.FAIL + ((" " + msg) if msg else ""))
        self._write_logfile(f"Test '{name}: FAIL\n")
        return TestStatus.FAIL

    def waived(self, name, msg=None):
        print(f"   {name}: " + self.WAIVE + ((" " + msg) if msg else ""))
        self._write_logfile(f"Test '{name}: WAIVED\n")
        return TestStatus.WAIVE

    def get_frontend(self):
        return self._frontend

    def get_machine_config(self):
        return self._config.get_machine_config()

    def get_kinematics_config(self):
        return self._config.get_kinematics_config()

    def get_config_section(self, type, name):
        return self._config.get_section(type, name)

    def get_object_klasses(self):
        return self._klasses

    def get_object_klass(self, name):
        if not isinstance(name, str):
            raise TypeError("Klass name should be a string")
        return {n: v for v, n in self._klasses.items()}.get(name.upper())

    def get_objects(self, klass=None):
        if klass is None:
            return self._objects
        if isinstance(klass, str):
            klass = klass.upper()
            klass = {n: v for v, n in self._klasses.items()}.get(klass)
        return self._objects.get(klass, [])

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
        request = api.Request(api.RequestType.OBJECT_STATUS)
        request.objects = objects
        return self._query(request)

    def run_command(self, cmd):
        logging.debug("Sending command: %s", cmd)
        self._frontend_fd.write(cmd.encode())
        return self._commands.get()

    def wait_for_completion(self, cmd_id):
        while cmd_id not in self._complete:
            time.sleep(0.2)
        result = self._complete.pop(cmd_id)
        return result

    def command_is_complete(self, cmd_id):
        return cmd_id in self._complete

    def ignore_command_completion(self, cmd_id):
        self._ignore_completions.append(cmd_id)

    def _response_processor(self):
        incoming = b''
        while self._collect:
            try:
                data = self._frontend_fd.read(512)
            except OSError:
                continue
            incoming += data
            while incoming:
                start_marker = incoming.find(b'#$')
                if start_marker == -1:
                    break
                end_marker = incoming.find(b'$#')
                if end_marker == -1:
                    break
                response = pickle.loads(incoming[start_marker+2:end_marker])
                incoming = incoming[end_marker+2:]
                if response.status != CommandStatus.COMPLETE:
                    self._commands.put(response.data)
                else:
                    if response.data.id in self._ignore_completions:
                        self._ignore_completions.remove(response.data.id)
                        continue
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
        cmd = [os.path.join(path, "vortex_run.py"), "-C", self._config_file,
               "-f", self._frontend, "-c", self._controller, "-R", "-F",
               f"{self._emulation_frequency}Hz"]
        if self._logfile is not None:
            if os.path.exists(self._logfile):
                os.unlink(self._logfile)
            cmd += ["-d", "DEBUG"]
            self._logfile = open(self._logfile, "wb")
        logging.verbose("Cmd: %s", " ".join(cmd))
        self._emulator = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT)
        while not os.path.exists(VORTEX_PATH) or not os.path.exists(VORTEX_SOCKET_PATH):
            if self._emulator.poll() != None:
                status = self._emulator.wait()
                logging.error(f"Starting emulator failed ({status}).")
                sys.exit(status)
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
            logging.error(f"Failed to connect to monitor: {str(e)}")
            return None
        return sock

    def _query(self, request):
        self._monitor.sendall(pickle.dumps(request))
        response = b""
        incoming = self._monitor.recv(1024)
        while incoming:
            response += incoming
            try:
                incoming = self._monitor.recv(1024, socket.MSG_DONTWAIT)
            except BlockingIOError:
                break
        response = pickle.loads(response)
        if response.status != 0:
            return False
        return response.data

    def _init_data(self):
        self._klasses = self._query(api.Request(api.RequestType.KLASS_LIST))
        self._objects = self._query(api.Request(api.RequestType.OBJECT_LIST))

    def _load_test(self, test_file, test_data):
        try:
            test_module = importlib.import_module(f"tests.{self._frontend}.{test_file}")
        except ImportError as e:
            logging.error(str(e))
            return False
        tests = [f for n, f in inspect.getmembers(test_module, inspect.isfunction) \
                     if getattr(f, "__vtest__", False)]
        for test in tests:
            name = test.__vtest__[0]
            klass = test.__vtest__[1]
            deps = test.__vtest__[2]
            test_data[name] = (test, klass, deps)
        return True

    def _get_dependencies(self, test):
        test_deps = self._test_data[test][2]
        resolved = []
        for name, (func, provides, deps) in self._test_data.items():
            if provides in test_deps:
                resolved.append(name)
        return resolved

    def _resolve_dependencies(self, tests=None):
        if not tests:
            tests = list(self._test_data.keys())
        test_order = []
        for test in tests:
            deps = self._get_dependencies(test)
            if not deps:
                test_order.append(test)
            else:
                test_order += [t for t in self._resolve_dependencies(deps) \
                               if t not in test_order]
                if test not in test_order:
                    test_order.append(test)
        return test_order

    def initialize(self):
        self._launch_emulator()
        self._monitor = self._connect_monitor()
        self._frontend_fd = open(VORTEX_PATH, 'wb+', buffering=0)
        self._response_parser = threading.Thread(None, self._response_processor,
                                                 "response_parser")
        self._response_parser.start()
        self._init_data()
        return True

    def load_tests(self):
        test_files = []
        ## find all available tests:
        path = pathlib.Path(__file__).parent / "tests" / self._frontend
        for test_file in path.iterdir():
            if test_file.is_dir():
                continue
            test_files.append(test_file.stem)

        self._test_data = {}
        for test in test_files:
            if not self._load_test(test, self._test_data):
                logging.error(f"Failed to load tests")
                return False
        return True

    def show_result(self, name, status):
        msg = status.msg if isinstance(status, TestStatus.__base_test_status__) else None
        if status == TestStatus.FAIL:
            self.failed(name, msg)
        elif status == TestStatus.WAIVE:
            self.waived(name, msg)
        else:
            self.passed(name, msg)
        reset_request = api.Request(api.RequestType.EMULATION_RESET)
        response = self._query(reset_request)
        while not self._commands.empty():
            self._commands.get_nowait()
        if response is False:
            logging.error("Failed to reset emulator")

    def run_tests(self, tests=[], skip_dependencies=False):
        if skip_dependencies:
            order = [test for test in self._test_data.keys() if test in tests]
        else:
            order = self._resolve_dependencies(tests)

        for test in order:
            test_func = self._test_data[test][0]
            klass = self._test_data[test][1]
            self.begin(test, klass)
            if klass is None:
                status = test_func(self)
                self.show_result(test, status)
            else:
                klass = ObjectKlass[klass.upper()]
                if klass not in self._objects:
                    self.show_result(test, TestStatus.WAIVE(f"No {klass} objects in configuration."))
                    continue
                for obj in self._objects[klass]:
                    status = test_func(self, obj["name"], obj["id"])
                    self.show_result(obj["name"], status)
            self.end(test)

    def terminate(self):
        if hasattr(self, "_monitor") and self._monitor:
            self._monitor.close()
        if self._emulator:
            self._emulator.send_signal(subprocess.signal.SIGINT)
            emulator_wait = time.time()
            while self._emulator.poll() is None:
                if time.time() - emulator_wait > 5:
                    logging.warning("Emulator did not terminate in time, killing it.")
                    self._emulator.terminate()
                time.sleep(0.5)
            self._collect = False
            if self._collector:
                self._collector.join()
            if hasattr(self, "_response_parse") and self._response_parser:
                self._response_parser.join()
        if self._logfile:
            self._logfile.close()

#!/usr/bin/env python
import os
import io
import sys
import cmd
import enum
import pickle
import argparse
import readline
import pathlib
import socket
import threading
from time import sleep
import vortex.lib.GCode as gcode
import vortex.emulator.remote.api as api
from vortex.core import ObjectKlass
from vortex.core.kinematics import AxisType
from vortex.frontends.proto import CommandStatus, PacketMarker

class GColor:  # Gnome supported
    END = "\x1b[0m"
    # If Foreground is False that means color effect on Background
    @staticmethod
    def RGB(R, G, B, Foreground=True):  # R: 0-255  ,  G: 0-255  ,  B: 0-255
        # Effect on foreground or background
        FB_G = 38 + (not Foreground and 10 or 0)
        return "\001\033[" + str(FB_G) + ";2;" + str(R) + ";" + str(G) + ";" + str(B) + "m\002"

    @staticmethod
    def HEX(code, Foreground=True):
        if len(code) != 7 or code[0] != '#':
            raise TypeError("Invaid HEX color code.")
        R, G, B = [code[i:i + 2] for i in range(1, len(code), 2)]
        return GColor.RGB(int(R, 16), int(G, 16), int(B, 16), Foreground)

class Colors(enum.Enum):
    BLACK = GColor.RGB(0, 0, 0)
    RED = GColor.RGB(255, 0, 0)
    GREEN = GColor.RGB(0, 255, 0)
    BLUE = GColor.RGB(0, 0, 255)
    WHITE = GColor.RGB(255, 255, 255)
    YELLOW = GColor.RGB(255, 255, 0)
    LIGHT_BLUE = GColor.RGB(0, 128, 255)
    CYAN = GColor.RGB(91, 141, 222)
    ORANGE = GColor.RGB(255, 128, 0)
    MAGENTA = GColor.RGB(255, 0, 255)
    GRAY = GColor.RGB(128, 128, 128)
    LIGHT_GRAY = GColor.RGB(224, 224, 224)
    SKY_BLUE = GColor.RGB(102, 178, 255)
    BRONZE = GColor.HEX("#B1560F")
    EMERALD = GColor.HEX("#50C878")

    # Background colors
    BG_RED = GColor.RGB(255, 0, 0, False)

    # The following are format modifiers
    BOLD = "\x1b[1m"
    ITALICS = "\x1b[3m"
    UNDERLINE = "\x1b[4m"
    BLINK = "\x1b[5m"

    RESET = NONE = GColor.END

    def __str__(self):
        return self.value

def send_request(sock, request):
    return sock.sendall(pickle.dumps(request))

def receive_response(sock):
    data = b''
    try:
        data = b""
        recved = sock.recv(8192)
        while recved:
            data += recved
            try:
                recved = sock.recv(8192, socket.MSG_DONTWAIT)
                data += recved
            except BlockingIOError:
                break
    except (ConnectionError, socket.error):
        r = api.Response(api.RequestType.COMMAND_STATUS)
        r.status = -1
        return r
    return pickle.loads(data)

def send_receive(socket, request):
    send_request(socket, request)
    return receive_response(socket)

def get_emulator_info(socket):
    info = dict()
    response = send_receive(socket, api.Request(api.RequestType.KLASS_LIST))
    if response.status != 0:
        return None
    info["klasses"] = response.data
    response = send_receive(socket, api.Request(api.RequestType.OBJECT_LIST))
    if response.status != 0:
        return None
    info["objects"] = response.data
    for klass in info["klasses"]:
        info["commands"] = {}
        request = api.Request(api.RequestType.OBJECT_COMMANDS)
        request.klass = klass
        response = send_receive(socket, request)
        if response.status != 0:
            return None
        info["commands"] = response.data
    return info

@enum.unique
class CLIMode(enum.IntEnum):
    DIRECT = enum.auto()
    GCODE = enum.auto()
    KLIPPER = GCODE

CommandStatus.DISCONNECT = 99

class HeartbeadThread(threading.Thread):
    def __init__(self, socket_path, set_cb, msg_cb):
        self.set_func = set_cb
        self.msg_func = msg_cb
        super().__init__(name="heartbeat")
        self._is_alive = False
        self._prev_state = None
        self._do_run = True
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(socket_path)

    @property
    def is_alive(self):
        return self._is_alive

    def run(self):
        while self._do_run:
            request = api.Request(api.RequestType.HEARTBEAT)
            try:
                send_receive(self.sock, request)
                self._is_alive = True
            except (ConnectionError, ConnectionRefusedError, OSError, EOFError):
                self._is_alive = False
            if self._prev_state != self._is_alive:
                if self._prev_state is not None:
                    if self._is_alive:
                        self.msg_func(f"\n{Colors.CYAN}HEARTBEAT{Colors.NONE}:", "Server connection restored.")
                    else:
                        self.msg_func(f"\n{Colors.CYAN}HEARTBEAT{Colors.NONE}:", "Server connection terminated.")
                self.set_func(self._prev_state, self._is_alive)
                self._prev_state = self._is_alive
            sleep(0.5)

    def stop(self):
        self._do_run = False

class Interface(cmd.Cmd):
    def __init__(self, mode, frontend, server):
        self.data = {}
        super().__init__()
        self.mode = mode
        self.frontend_path = frontend
        self.frontend = None
        self.server_path = server
        self.server_sock = None
        self.heartbeat = None
        if self.mode == CLIMode.GCODE:
            self.gcode_parser = gcode.Parser.GCodeParser()
        self.prompt = f"{Colors.LIGHT_BLUE}Vortex Direct > {Colors.NONE}"
        if self.heartbeat is None:
            try:
                self.heartbeat = HeartbeadThread(self.server_path, self.__set_alive,
                                                 self.__msg)
            except Exception as exc:
                raise ConnectionError(exc)
            self.heartbeat.start()
        try:
            self.connect()
        except Exception as exc:
            self.warning("Could not connect to emulator.")
            self.warning(str(exc))
            raise ConnectionError
        self._response_stream = b""

    def __set_alive(self, was_alive, is_alive):
        self.__server_is_alive = is_alive
        if not was_alive and is_alive:
            self.connect()
            self.data = get_emulator_info(self.server_sock)
            if not self.data:
                raise ValueError("Could not get emulator data")
        elif not is_alive:
            self.disconnect()
        self.emptyline(False)

    def connect(self):
        try:
            if self.frontend is None:
                fd = os.open(self.frontend_path, os.O_RDWR | os.O_NOCTTY)
                self.frontend = io.FileIO(fd, "wb+")
            if self.server_sock is None:
                self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.server_sock.connect(self.server_path)
        except:
            self.disconnect()
            raise

    def disconnect(self):
        if self.frontend is not None:
            self.frontend.close()
            self.frontend = None
        if self.server_sock is not None:
            self.server_sock.close()

    def cmdloop(self):
        try:
            super().cmdloop()
        except KeyboardInterrupt:
            print()
            return

    def emptyline(self, repeat=True):
        print("emptyline", repeat)
        if repeat:
            return super().emptyline()
        else:
            super().onecmd("")
        return False

    def precmd(self, line):
        if line not in ( "connect", "quit") and not self.__server_is_alive:
            self.error("Server connection is not alive")
            self.disconnect()
            return ""
        return line

    def get_command_response(self, pipe):
        start, end = -1, -1
        while start == -1 and end == -1:
            try:
                self._response_stream += pipe.read()
            except OSError:
                self.disconnect()
                return CommandStatus.DISCONNECT
            start = self._response_stream.find(PacketMarker.START)
            end = self._response_stream.find(PacketMarker.END)
        response = self._response_stream[start+2:end]
        self._response_stream = self._response_stream[end+2:]
        return pickle.loads(response)

    def do_connect(self, args):
        if self.frontend and self.server_sock:
            self.error("Already connected")
            return False
        try:
            self.connect()
            self.success("Connected to emulation")
        except Exception as exc:
            self.error("Could not connect to emulator")
            self.error(str(exc))
        return False

    def do_disconnect(self):
        self.disconnect()
        self.success("Disconnected from emulation")

    def _validate_command(self, obj, command, args):
        for klass in self.data["objects"]:
            matches = list(filter(lambda o: o["name"] == obj,
                                  self.data["objects"][klass]))
            if matches:
                break
        if len(matches) == 0:
            self.error(f"No object named '{obj}'")
            return None
        if len(matches) != 1:
            self.error(f"Too many objects match name '{obj}'")
            return None
        klass = klass
        obj = matches[0]
        matches = list(filter(lambda o: o[1] == command,
                              self.data["commands"][klass]))
        if len(matches) == 0:
            self.error(f"No command for klass '{klass}'")
            return None
        if len(matches) > 1:
            self.error(f"Too many command matches for '{command}'")
            return None
        command = matches[0]
        opts = {}
        for arg in args.split():
            try:
                k, v = arg.split("=")
            except ValueError:
                self.error(f"Invalid command argument '{arg}")
                return None
            opts[k] = v
        for opt, value in opts.items():
            opt_defs = list(filter(lambda o: o[0] == k, command[2]))
            if len(opt_defs) == 0:
                self.error(f"Unknown command argument '{opt}'")
                return None
            if len(opt_defs) > 1:
                self.error(f"Too many argument matches for '{opt}'")
            try:
                opts[opt] = opt_defs[0][1](value)
            except ValueError:
                self.error(f"Invalid argument value for '{opt}'")
                return None
        return klass

    def _validate_gcode_command(self, cmd):
        try:
            cmd = self.gcode_parser.parse(cmd)
            return cmd
        except gcode.GCode.GCodeCommandParseError as exp:
            self.error(f"GCode command error: {str(exp)}")
            return None

    def do_execute(self, args):
        if not args:
            self.error("No command specified")
            return False
        if not self.frontend or not self.server_sock:
            self.error("Not connected to server")
            return False
        if self.mode == CLIMode.DIRECT:
            try:
                obj_name, command, args = args.split(maxsplit=2)
            except ValueError:
                self.error("Invalid command")
                return False
            klass = self._validate_command(obj_name, command, args)
            if not klass:
                return False
            command=f"{str(klass).lower()}:{obj_name}:{command[1]}:{",".join(args.split())}"
            try:
                self.frontend.write(bytes(command, "ascii"))
            except OSError:
                self.error("Emulator connection terminated unexpectedly.")
                return True
            response = self.get_command_response(self.frontend)
            if response == CommandStatus.FAILED:
                self.error(f"Command submission failed.")
                return False
            while response.status == CommandStatus.QUEUED:
                response = self.get_command_response(self.frontend)
            completion = response.data
            if completion.status != 0:
                self.error(f"Command execution failed (status={completion.status})")
                return False
            else:
                self.success(f"Command executed successfull")
                if completion.data:
                    print(completion.data)
        else:
            command = self._validate_gcode_command(args)
            if command is None:
                return False
            try:
                self.frontend.write(bytes(args, "ascii"))
            except OSError:
                self.error("Emulator connection terminated unexpectedly.")
                return True
            response = self.get_command_response(self.frontend)
            if response == CommandStatus.DISCONNECT:
                self.error("Emulator disconnected unexpectedly")
                self.disconnect()
                return False
            elif response == CommandStatus.FAIL:
                self.error("Command failed")
                return False
            print(response)
        return False

    def complete_execute(self, text, line, bidx, eidx):
        if self.mode == CLIMode.DIRECT:
            words = line.split()
            try:
                idx = words.index(text)
            except ValueError:
                idx = len(words)
            if idx == 1:
                names = [x["name"] for k in self.data["objects"].values() for x in k]
                return [x for x in names if x.lower().startswith(text)]
            elif idx == 2:
                commands = [x[1] for k in self.data["commands"].values() for x in k]
                return [x for x in commands if x.startswith(text)]
            else:
                arg_set = [x[2] for k in self.data["commands"].values() for x in k if x[1] == words[2]]
                if len(arg_set) != 1:
                    return []
                arg_set = [x[0] for x in arg_set[0]]
                return [x for x in arg_set if x.startswith(text)]
        else:
            words = line.split()
            if len(words) == 1:
                return gcode.GCode.GCodeCommandClasses
            try:
                command = self.gcode_parser.parse(" ".join(words[1:]))
            except gcode.GCode.GCodeCommandParserError as e:
                print(e)
                return ""
            print(command.command_class)
            if command.command_class == "G":
                return [str(x) for x in AxisType] + ["F"]
            return ""

    def do_show(self, arg):
        output = None
        if arg == "klasses":
            output = list(map(str, self.data["klasses"]))
            self.columnize(output)
        if arg == "objects":
            for klass in self.data["objects"]:
                print(f"Object Klass {Colors.MAGENTA}{klass}{Colors.NONE}")
                print("-" * 80)
                objects = []
                for object in self.data["objects"][klass]:
                    objects.append(f"{object["name"]} (id={object["id"]})")
                self.columnize(objects)
                print()
        if arg == "commands":
            for klass in self.data["commands"]:
                if self.data["commands"][klass]:
                    print(f"Object Klass {Colors.MAGENTA}{klass}{Colors.NONE}")
                    print("-" * 80)
                    commands = []
                    for command in self.data["commands"][klass]:
                        name = command[1]
                        args = [f"{x[0]}({x[1].__name__})" for x in command[2]]
                        commands.append(f"{Colors.CYAN}{name}{Colors.NONE} args=[{", ".join(args)}]")
                    self.columnize(commands)
                    print()
        words = arg.split()
        if words[0] == "status":
            objects = [x for k in self.data["objects"].values() for x in k]
            object_names = [x["name"] for x in objects]
            query_objects = {}
            for obj in words[1:]:
                if obj not in object_names:
                    self.error(f"Unknown object '{obj}'")
                    continue
                for o in objects:
                    if o["name"] == obj:
                        query_objects[obj] = o["id"]
            request = api.Request(api.RequestType.OBJECT_STATUS)
            request.objects = list(query_objects.values())
            response = send_receive(self.server_sock, request)
            for obj in query_objects:
                print(f"Object {Colors.MAGENTA}{obj}{Colors.NONE} Status")
                status = response.data[query_objects[obj]]
                width = max(map(len, status.keys())) + 2
                for elem in status:
                    print(f"    {elem:<{width}}: {status[elem]}")
        return False

    def complete_show(self, text, line, bidx, eidx):
        words = line.split()
        try:
            idx = words.index(text)
        except ValueError:
            idx = len(words)
        if words[idx - 1] == "status":
            objects = [x["name"] for k in self.data["objects"].values() for x in k]
            return [x for x in objects if x.startswith(text)]
        return [x for x in ["klasses", "objects", "commands", "status"] if x.startswith(text)]

    def __msg(self, prefix, fmt, *args, **kwargs):
        print(prefix, fmt.format(*args, **kwargs), flush=True)

    def success(self, *args, **kwargs):
        prefix = f"{Colors.GREEN}SUCCESS:{Colors.NONE}"
        self.__msg(prefix, *args, **kwargs)

    def error(self, *args, **kwargs):
        prefix = f"{Colors.RED}ERROR:{Colors.NONE}"
        self.__msg(prefix, *args, **kwargs)

    def warning(self, *args, **kwargs):
        prefix = f"{Colors.ORANGE}WARNING:{Colors.NONE}"
        self.__msg(prefix, *args, **kwargs)

    def info(self, *args, **kwargs):
        prefix = f"{Colors.YELLOW}INFO:{Colors.NONE}"

    def do_quit(self, arg):
        if self.heartbeat:
            self.heartbeat.stop()
            self.heartbeat.join()
            self.heartbeat = None
        self.disconnect()
        return True

    def terminate(self):
        self.disconnect()
        return self.do_quit("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=str, default="/tmp/vortex-remote")
    parser.add_argument("--frontend", type=str, default="/tmp/vortex")
    parser.add_argument("mode", choices=["gcode", "direct"])
    args = parser.parse_args()

    mode = CLIMode.DIRECT if args.mode == "direct" else CLIMode.GCODE
    cli = None
    history = pathlib.PosixPath(os.environ.get("HOME")) / ".local" / \
                                "vortex" / "history"
    if not history.exists():
        history.parent.mkdir(parents=True, exist_ok=True)
        history.touch()

    readline.read_history_file(history.as_posix())
    readline.set_history_length(100)

    try:
        cli = Interface(mode, args.frontend, args.server)
        cli.cmdloop()
    except (ConnectionError, ConnectionRefusedError):
        print(f"{Colors.RED}Startup Error{Colors.NONE}: Could not connect to emulator server")
        return -1
    except Exception as e:
        print("CLI failure:", str(e))
        raise
    finally:
        if cli:
            cli.terminate()

    readline.write_history_file(history.as_posix())
    return 0

if __name__ == "__main__":
    sys.exit(main())
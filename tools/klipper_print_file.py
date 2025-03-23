#!/usr/bin/env python3
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
import sys
import os
import time
import json
import pickle
import socket
import argparse
import configparser

parser = argparse.ArgumentParser()
seq = parser.add_argument_group("Sequential Printing",
                                description="Print file by sending commands one by one.")
seq.add_argument("--sequential", action="store_true", help="Enable sequential printing")
seq.add_argument("--interval", type=float, default=0.0, help="Send commands every INTERVAL seconds")
seq.add_argument("--wait", action="store_true", help="Wait for user intput before continuing")
seq.add_argument("-M", action="store_true", dest="monitor", help="Monitor emulator")
seq.add_argument("--emulator-pipe", default="/tmp/vortex_monitor", help="Emulator command pipe")
parser.add_argument("--pipe", default="/tmp/printer", help="Klipper command pipe")
parser.add_argument("config", help="Klipper config file")

args = parser.parse_args()
config_file = args.config
parser = configparser.ConfigParser()
parser.read(config_file)

if not parser.has_option("virtual_sdcard", "path"):
    print(f"ERROR: Virtual SDCard section is misconfigured")
    sys.exit(1)

gcode_path = parser.get("virtual_sdcard", "path")
gcode_path = os.path.abspath(os.path.expanduser(gcode_path))

gcode_files = [x for x in os.listdir(gcode_path) if x.endswith(".gcode")]
gcode_file = None
try:
    while True:
        print("Select file to print:")
        for i, filename in enumerate(gcode_files):
            print(f"{i}: {filename}")
        s = input(f"[0-{i}]? ")
        s = int(s)
        if s >= 0 and s < len(gcode_files):
            gcode_file = gcode_files[s]
            break
except KeyboardInterrupt:
    sys.exit(0)

print(f"Printing {gcode_file}...")
if args.sequential:
    if args.monitor:
        emulator = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            emulator.connect(args.emulator_pipe)
        except (FileNotFoundError, ConnectionRefusedError):
            print("Could not connect to emulator socket.")
            sys.exit(-1)

    printer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    printer.connect(args.pipe)
    id = 0
    try:
        with open(os.path.join(gcode_path, gcode_file), 'r') as gcode:
            for line in gcode:
                emulator.sendall(pickle.dumps({"request": "object_list"}))
                data = emulator.recv(8192)
                if not line.strip() or line.startswith(';'):
                    continue
                print(f"Executing {line.strip()}...")
                data = json.dumps({'id': id, 'method': 'gcode/script',
                                   'params': {'script': line.strip()}}).encode()
                printer.sendall(data + chr(0x3).encode())
                id += 1
                response = printer.recv(1024)
                if args.wait:
                    input("Next line? ")
                elif args.interval:
                    time.sleep(args.interval)
    except BrokenPipeError:
        sys.exit(0)
    finally:
        printer.close()
        if args.monitor:
            emulator.close()
else:
    printer = open(args.pipe, 'a')
    printer.write(f"SDCARD_PRINT_FILE FILENAME={gcode_file}\n")

sys.exit(0)
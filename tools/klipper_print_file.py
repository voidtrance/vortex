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
import argparse
import configparser

parser = argparse.ArgumentParser()
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
with open("/tmp/printer", 'a') as fd:
    fd.write("M21\n")
    fd.write(f"M23 {gcode_file}\n")
    fd.write("M24\n")

    
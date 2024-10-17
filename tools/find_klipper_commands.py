#!/usr/bin/env python3
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
# import sys
import re
import sys
import pathlib

HEADER = """
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
from argparse import Namespace
"""
reg_cmd = re.compile(r'^DECL_COMMAND(?:_FLAGS)?\((?P<handler>[^,]+),\s*(?:(?P<flag>[^,]+),\s*)*\"(?P<cmd>[^\"]+)\"\);$')
reg_resp = re.compile(r'^sendf\(\"(?P<resp>[^\"]+)\"(?:,\s*[^;]+)*;$')

def find_commands(path):
    commands = {}
    responses = {}
    for entry in path.iterdir():
        if entry.is_dir():
            find_commands(entry)
        elif entry.is_file():
            with open(entry, 'r') as fd:
                content = fd.readlines()
            for i in range(len(content)):
                line = content[i]
                # When it comes to the command declaration calls,
                # Klipper's coding style is inconsistent. With
                # all of the variations, it's hard to come up with
                # a single regular expression.
                # It's much easier to just combine all of the call
                # lines into one.
                string = line.strip()
                if not string.startswith("DECL_COMMAND") and \
                   not string.startswith("sendf"):
                    continue
                while not string.endswith(");"):
                    string += content[i+1].strip()
                    i += 1
                string = string.replace('""', '')
                if '//' in string or '/*' in string:
                    continue
                if string.startswith("sendf"):
                    m = reg_resp.match(string)
                    if m:
                        if entry.stem not in responses:
                            responses[entry.stem] = []
                        responses[entry.stem].append(m.groupdict())
                    else:
                        print(entry, string)
                else:
                    m = reg_cmd.match(string)
                    if m:
                        if entry.stem not in commands:
                            commands[entry.stem] = []
                        commands[entry.stem].append(m.groupdict())
                    else:
                        print(entry, string)
    return commands, responses

def output_commands(filename, commands):
    with open(filename, 'w') as fd:
        fd.write(HEADER)
        flags = []
        for cmd in [c for l in commands.values() for c in l]:
            if cmd["flag"] and cmd["flag"] not in flags:
                flags.append(cmd["flag"])
        if flags:
            fd.write("from vortex.lib.ext_enum import ExtIntEnum, auto\n\n")
            fd.write("class KlipperProtoFlags(ExtIntEnum):\n")
            for flag in flags:
                fd.write(f"\t{flag.upper()} = auto()\n")
        fd.write("\n")
        sections = [f"{entry}=Namespace()" for entry in list(commands.keys()) + ["tasks"]]
        s = 4
        fd.write(f"KLIPPER_PROTOCOL = Namespace({', '.join(sections[:s])}")
        for x in range(s, len(sections), s):
            fd.write(f",\n\t\t\t{', '.join(sections[x:x+s])}")
        fd.write(")\n\n")
        for entry in commands:
            fd.write(f"# {entry} commands\n")
            for cmd in commands[entry]:
                cmd_name = cmd["cmd"].split()[0]
                flag = ("KlipperProtoFlags." + cmd["flag"].upper()) if cmd["flag"] else "None"
                fd.write(f"KLIPPER_PROTOCOL.{entry}.{cmd_name} = Namespace(command=\"{cmd['cmd']}\", flags={flag}, response=None)\n")
            for resp in responses.get(entry, []):
                fd.write(f"\t\t\t\"{resp['resp']}\"\n")
            fd.write("\n")

if len(sys.argv) == 0:
    print("find_klipper_commands.py <klipper src dir> <output file>")

path = pathlib.Path(sys.argv[1])
commands, responses = find_commands(path)
output_commands(sys.argv[2], commands)

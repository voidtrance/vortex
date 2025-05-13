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
import pathlib
import re
import sys
import ast

MODE_EVENTS = 1
MODE_TYPES = 2

mode = MODE_EVENTS if sys.argv[1] == "-e" else MODE_TYPES
top = pathlib.PosixPath(sys.argv[2])
output_file = sys.argv[3]

def find_virtual_objects():
    objects = []
    object_reg = re.compile(r'^class (?P<klass>[^\(]+)\([^.]*.?VirtualObjectBase\):$', re.MULTILINE)
    for file in (top / "controllers/objects").iterdir():
        if file.is_dir():
            continue
        with open(file, 'r') as fd:
            for line in fd:
                match = object_reg.match(line)
                if not match:
                    continue
                objects.append((match.group("klass").strip(), file))
    return objects

def find_new_types(object_list):
    new_types = []
    new_events = []
    for object in object_list:
        with open(object[1], 'r') as fd:
            source = fd.read()
            node = ast.parse(source)
            for node in node.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                for cnode in node.body:
                    if not isinstance(cnode, ast.Assign):
                        continue
                    if cnode.targets[0].id == "type":
                        if cnode.value.value.id != "ObjectTypes":
                            continue
                        if cnode.value.attr not in new_types:
                            new_types.append(cnode.value.attr)
                    elif cnode.targets[0].id == "events":
                        if not isinstance(cnode.value, ast.List):
                            continue
                        lnode = cnode.value
                        for elnt in lnode.elts:
                            if elnt.value.id != "ObjectEvents":
                                continue
                            if elnt.attr not in new_events:
                                new_events.append(elnt.attr)
    return new_types, new_events

def gen_types(output_file, types):
    content = list()
    with open(top / f"{output_file}.in", 'r') as fd:
        for line in fd:
            if "@EXTRA_TYPES@" not in line and \
                "@EXTRA_TYPE_NAMES@" not in line and \
                "@EXTRA_TYPE_EXPORT_NAMES@" not in line:
                content.append(line)
                continue
            if "@EXTRA_TYPES@" in line:
                content += [" " * 4 + f"OBJECT_TYPE_{x.upper()},\n" \
                            for x in types]
            elif "@EXTRA_TYPE_EXPORT_NAMES@" in line:
                content += [" " * 4 + \
                            f"[OBJECT_TYPE_{x.upper()}] = stringify(OBJECT_TYPE_{x.upper()}),\n" \
                            for x in types]
                
            elif "@EXTRA_TYPE_NAMES@":
                content += [" " * 4 + \
                            f"[OBJECT_TYPE_{x.upper()}] = \"{x.lower()}\",\n" \
                            for x in types]

    with open(top / output_file, 'w') as fd:
        fd.write("".join(content))

def gen_events(output_file, events):
    content = list()
    with open(top / f"{output_file}.in", 'r') as fd:
        for line in fd:
            if "@EXTRA_EVENTS@" not in line and \
                "@EXTRA_EVENT_NAMES@" not in line:
                content.append(line)
                continue
            if "@EXTRA_EVENTS@" in line:
                content += [" " * 4 + f"OBJECT_EVENT_{x.upper()},\n" \
                           for x in events]
            elif "@EXTRA_EVENT_NAMES@" in line:
                content += [" " * 4 + \
                         f"[OBJECT_EVENT_{x.upper()}] = \"{x.upper()}\",\n" \
                            for x in events]
                

    with open(top / output_file, 'w') as fd:
        fd.write("".join(content))

objects = find_virtual_objects()
types, events = find_new_types(objects)
if mode == MODE_TYPES:
    gen_types(output_file, types)
else:
    gen_events(output_file, events)


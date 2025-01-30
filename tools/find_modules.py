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
import re
import sys
import os

def find_hw_objects(source_path):
    object_reg = re.compile(r'^class (?P<klass>[^\(]+)\(ObjectDef\):$', re.MULTILINE)
    objects = []
    with open(os.path.join(source_path, "controllers/objects/object_defs.py")) as fd:
        for line in fd:
            match = object_reg.match(line)
            if not match:
                continue
            objects.append(match.group("klass").strip().lower())
    return objects

if len(sys.argv) == 2:
    for object in find_hw_objects(sys.argv[1]):
        print(object)
elif len(sys.argv) > 2:
    files = os.listdir(sys.argv[1])
    for object in sys.argv[2:]:
        for filename in files:
            if filename.startswith(object) and filename.endswith(".c"):
                print(filename)

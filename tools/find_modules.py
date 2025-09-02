#!/usr/bin/env python3
# vortex - GCode machine emulator
# Copyright (C) 2024-2026 Mitko Haralanov
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
import pathlib
from clang import cindex
import argparse

def find_hw_objects(source_dir):
    object_dir = pathlib.PosixPath(source_dir)
    index = cindex.Index.create()
    objects = []
    for file in object_dir.iterdir():
        if file.suffix != ".c":
            continue
        tu = index.parse(file)
        for node in tu.cursor.walk_preorder():
            if node.kind == cindex.CursorKind.FUNCTION_DECL and \
                node.spelling == "object_create":
                objects.append(file.stem)
    return objects

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=str)
    parser.add_argument("--object", type=str, nargs="*")
    parser.add_argument("mode", choices=["modules", "files"])

    opts = parser.parse_args()

    if opts.mode == "modules":
        for object in find_hw_objects(opts.root):
            print(object)
    elif opts.mode == "files":
        files = os.listdir(opts.root)
        for object in opts.object:
            for filename in files:
                if filename.startswith(object) and filename.endswith(".c"):
                    print(filename)

main()
# vortex - GCode machine emulator
# Copyright (C) 2024,2026 Mitko Haralanov
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
from cffi import FFI
import argparse
import os

def get_clang_cursor_kind_defs():
    include_path = os.environ.get("CLANG_INCLUDE_PATH", "/usr/include")
    filename = os.path.join(include_path, "clang-c/Index.h")
    enum_found = False
    defs = ["enum CursorKind {"]
    enum_values = {}
    with open(filename, 'r') as fd:
        for line in fd.readlines():
            line = line.strip()
            if enum_found:
                if line == "};":
                    break
                if not line.startswith("CXCursor_"):
                    continue
                name, value = line.split(" = ")
                try:
                    value, _ = value.split(",")
                except ValueError:
                    if value[-1] == ',':
                        value = value[:-1]
                if value.isnumeric():
                    enum_values[name] = value
                else:
                    value = enum_values[value]
                _, py_name = name.split("_")
                defs.append(f"    {py_name} = {value},")
            else:
                if line.startswith("enum CXCursorKind {"):
                    enum_found = True
    defs +=  [f"    Any = {str(int(value) + 1)},"]
    defs += ["};"]
    return defs

def get_clang_type_kind_defs():
    include_path = os.environ.get("CLANG_INCLUDE_PATH", "/usr/include")
    filename = os.path.join(include_path, "clang-c/Index.h")
    enum_found = False
    defs = ["enum TypeKind {"]
    enum_values = {}
    with open(filename, 'r') as fd:
        for line in fd.readlines():
            line = line.strip()
            if enum_found:
                if line == "};":
                    break
                if not line.startswith("CXType_"):
                    continue
                name, value = line.split(" = ")
                try:
                    value, _ = value.split(",")
                except ValueError:
                    if value[-1] == ',':
                        value = value[:-1]
                if value.isnumeric():
                    enum_values[name] = value
                else:
                    value = enum_values[value]
                _, py_name = name.split("_", 1)
                defs.append(f"    {py_name} = {value},")
            else:
                if line.startswith("enum CXTypeKind {"):
                    enum_found = True
    for name in ("Char", "Size", "SSize"):
        defs += [f" {name} = {str(int(value) + 1)},"]
    defs += ["};"]
    return defs

def make_builder(header_path, link_path):
    ffibuilder = FFI()
    enum_cdef = get_clang_cursor_kind_defs()
    enum_cdef += get_clang_type_kind_defs()
    with open(os.path.join(header_path, "clang_ast.h"), "r") as fd:
        cdef = []
        for line in fd.readlines():
            if line.startswith("#"):
                continue
            cdef.append(line.rstrip())
        ffibuilder.cdef("\n".join(enum_cdef + cdef))

    builder = ["#include \"clang_ast.h\""] + enum_cdef
    ffibuilder.set_source("py_clang_ast", "\n".join(builder),
                          libraries=["clang_ast"],
                          include_dirs=[header_path],
                          library_dirs=[link_path],
                          extra_link_args=["-Wl,-rpath=$ORIGIN/tools/clang_ast"])
    return ffibuilder

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-I', required=True, dest="header_path")
    parser.add_argument("-L", required=True, dest="link_path")
    opts = parser.parse_args()

    curdir = os.getcwd()
    header_path = os.path.abspath(os.path.join(curdir, opts.header_path))
    link_path = os.path.abspath(os.path.join(curdir, opts.link_path))
    ffibuilder = make_builder(header_path, link_path)
    ret = ffibuilder.compile(verbose=3)
    print(ret)

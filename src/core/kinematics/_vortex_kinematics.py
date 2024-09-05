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
from cffi import FFI
import os
import argparse

def make_builder(header_path, link_path):
    ffibuilder = FFI()
    with open(os.path.join(header_path, "kinematics.h"), 'r') as fd:
        content = []
        for line in fd:
            if line[0] != '#':
                content.append(line)
        ffibuilder.cdef("\n".join(content))

    ffibuilder.set_source("_vortex_kinematics", '#include <kinematics.h>',
                          libraries=["kinematics"],
                          include_dirs=[header_path],
                          library_dirs=[link_path])
    return ffibuilder

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-I', required=True, dest="header_path")
    parser.add_argument('-L', required=True, dest="link_path")
    parser.add_argument('-O', dest="output_path")
    opts = parser.parse_args()

    curdir = os.getcwd()
    header_path = os.path.abspath(os.path.join(curdir, opts.header_path))
    link_path = os.path.abspath(os.path.join(curdir, opts.link_path))
    ffibuilder = make_builder(header_path, link_path)
    ffibuilder.compile(tmpdir=opts.output_path, target="_vortex_kinematics.*", verbose=3)
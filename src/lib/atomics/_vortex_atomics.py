# vortex - GCode machine emulator
# Copyright (C) 2024,2025  Mitko Haralanov
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
import subprocess

def make_builder(header_path, link_path, compiler):
    header_file = os.path.join(header_path, "atomics.h")
    preprocessed = os.path.join(header_path, "_atomics.h")
    processed = os.path.join(header_path, "__atomics.h")
    with open(header_file, 'r') as fd:
        with open(preprocessed, 'w') as out:
            for line in fd:
                if not line.startswith('#include'):
                    out.write(line)
    status, output = subprocess.getstatusoutput(f"{compiler} -E {preprocessed} -o {processed}")
    ffibuilder = FFI()
    with open(f"{processed}", 'r') as fd:
        content = fd.readlines()
        ffibuilder.cdef("\n".join(content))

    ffibuilder.set_source("_vortex_atomics", '#include <__atomics.h>',
                          libraries=["atomics"],
                          include_dirs=[header_path],
                          library_dirs=[link_path],
                          extra_link_args=['-Wl,-rpath=$ORIGIN'])
    return ffibuilder, [preprocessed, processed]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-C', required=True, dest="compiler")
    parser.add_argument('-I', required=True, dest="header_path")
    parser.add_argument('-L', required=True, dest="link_path")
    parser.add_argument('-O', dest="output_path")
    opts = parser.parse_args()

    curdir = os.getcwd()
    header_path = os.path.abspath(os.path.join(curdir, opts.header_path))
    link_path = os.path.abspath(os.path.join(curdir, opts.link_path))
    ffibuilder, tmp_files = make_builder(header_path, link_path, opts.compiler)
    ffibuilder.compile(tmpdir=opts.output_path, target="_vortex_atomics.*", verbose=3)
    for f in tmp_files:
        os.unlink(f)
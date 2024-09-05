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
r = run_command(py, root / 'tools/find_modules.py', root, check: true)
objects = r.stdout().strip()

auto_gen_types = custom_target('auto-types.h', output: 'auto-types.h',
                         input : root / 'tools/auto_gen_types.py',
                         command : [py, '@INPUT@', '-t', root, '@OUTPUT@'])

cc = meson.get_compiler('c')
math = cc.find_library('m')

foreach object : objects.split()
    lib = library(object, [object + '.c', auto_gen_types, auto_gen_events],
                         include_directories: [core_include],
                         dependencies: [core_utils_dep, core_kinematics_dep, math],
                         name_prefix: '',
                         install: true,
                         install_dir: py.get_install_dir(pure: false) / 'vortex/core/objects',
                         install_rpath: '$ORIGIN/../lib')
endforeach

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
core_atomics_inc = include_directories('.')
core_atomics = library('atomics', ['atomics.c'],
                        install: true,
                        install_dir: py.get_install_dir(pure: false) / 'vortex/core/lib/atomics')
core_atomics_dep = declare_dependency(link_with: core_atomics,
                                            include_directories: core_atomics_inc)

cc = meson.get_compiler('c')
py_atomics = custom_target('_vortex_atomics', output: '_vortex_atomics.so',
                        input : root / 'src/lib/atomics/_vortex_atomics.py',
                        command : [py, '@INPUT@', '-C',] +  cc.cmd_array() +
                                    ['-I', '@CURRENT_SOURCE_DIR@', 
                                    '-L', '@OUTDIR@', '-O', '@OUTDIR@'],
                        build_by_default: true,
                        install: true,
                        install_dir: py.get_install_dir(pure: false) / 'vortex/core/lib/atomics')
py.install_sources(['__init__.py'], subdir: 'vortex/core/lib/atomics')

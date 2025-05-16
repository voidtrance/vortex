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
core_include = include_directories('.')
pthreads = dependency('threads')

auto_gen_logging = custom_target('logging.h', output: 'logging.h',
                        input : root / 'tools/auto_gen_logging.py',
                        command : [py, '@INPUT@', root, '@OUTPUT@'])

subdir('kinematics')
subdir('objects')

py.extension_module('_vortex_core',
                    ['core.c', 'timers.c', auto_gen_events,
                             auto_gen_types, auto_gen_logging],
                    dependencies: [core_utils_dep, core_threads_dep,
                                   core_kinematics_dep, core_threads_dep,
                                   core_atomics_dep, pthreads],
                    include_directories: [core_include_general, core_atomics_inc],
                    install: true,
                    install_dir: py.get_install_dir(pure: false) / 'vortex/core',
                    link_args: ['-Wl,-rpath=$ORIGIN/lib',
                                '-Wl,-rpath=$ORIGIN/threads',
                                '-Wl,-rpath=$ORIGIN/kinematics',
                                '-Wl,-rpath=$ORIGIN/lib/atomics'],)
                    #install_rpath: '$ORIGIN/lib')
py.install_sources(['__init__.py'], subdir: 'vortex/core')

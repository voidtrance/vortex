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
core_include = include_directories('.')
pthreads = dependency('threads')

auto_gen_events = custom_target('auto-events.h', output: 'auto-events.h',
                         input : root / 'tools/auto_gen_types.py',
                         command : [py, '@INPUT@', '-e', root, '@OUTPUT@'])

subdir('objects')

py.extension_module('_vortex_core',
                    ['core.c', 'thread_control.c', auto_gen_events,
                     auto_gen_types],
                    include_directories: core_utils_include,
                    dependencies: [core_utils_dep, pthreads],
                    link_with: core_utils,
                    install: true,
                    install_dir: py.get_install_dir(pure: false) / 'vortex/core',
                    install_rpath: '$ORIGIN/lib')
py.install_sources(['__init__.py'], subdir: 'vortex/core')


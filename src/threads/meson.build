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
pthreads = dependency('threads')

core_threads_include = include_directories('.')
math = cc.find_library(('m'))
core_threads = library('threads', ['core_threads.c'],
                     install: true,
                     dependencies: [math, pthreads],
                     include_directories: [core_utils_include, core_include_general],
                     install_dir: py.get_install_dir(pure: false) / 'vortex/core/threads')
core_threads_dep = declare_dependency(link_with: core_threads,
                                    include_directories: core_threads_include)
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
core_threads_include = include_directories('.')
core_threads = library('threads', ['threads.c'],
                     install: true,
                     include_directories: core_utils_include,
                     install_dir: py.get_install_dir(pure: false) / 'vortex/core/threads')
core_threads_dep = declare_dependency(link_with: core_threads,
                                    include_directories: core_threads_include)
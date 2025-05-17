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
project('vortex', 'c', version: files('version.txt'),
        default_options: ['warning_level=1', 'werror=true'])
add_global_arguments('-Wunused', language: 'c')

cache = run_command('getconf', 'LEVEL1_DCACHE_LINESIZE', capture: true, check: true)
cacheline_size = cache.stdout().strip()
add_project_arguments('-DCACHELINE_SIZE=' + cacheline_size, language: 'c')

py = import('python').find_installation(pure: false)
root = meson.project_source_root()

# Build the core utils library
subdir('src')

# Install Python source
subdir('emulator')
subdir('controllers')
subdir('frontends')
subdir('lib')
subdir('tools')
install_data('vortex.py', install_dir: get_option('bindir'))
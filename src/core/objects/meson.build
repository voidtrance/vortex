# vortex - GCode machine emulator
# Copyright (C) 2024-2026 Mitko Haralanov
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
cc = meson.get_compiler('c')
math = cc.find_library('m')
build_env = environment()
build_env.prepend('PYTHONPATH', meson.project_build_root())

auto_gen_types = custom_target('auto-klass.h', output: 'auto-klass.h',
                         input : root / 'tools/auto_gen.py',
                         command : [py, '@INPUT@', '-o', root, '@OUTPUT@'],
                         depends: [py_clang_ast],
                         env: build_env)

auto_gen_events = custom_target('auto-events.h', output: 'auto-events.h',
                         input : root / 'tools/auto_gen.py',
                         command : [py, '@INPUT@', '-e', root, '@OUTPUT@'],
                         depends: [py_clang_ast],
                         env: build_env)

auto_gen_vobj = custom_target('vobj_defs.h', output: 'vobj_defs.h',
                         input: root / 'tools/generate_vobj_defs.py',
                         command: [py, '@INPUT@', '--root', root, '@OUTPUT@'])

r = run_command(py, root / 'tools/find_modules.py', '--root',
                 meson.current_source_dir(), 'modules', check: true)
objects = r.stdout().strip().split()

auto_structs = custom_target('structs.py', output: 'structs.py',
                        input : root / 'tools/auto_gen.py',
                        command : [py, '@INPUT@', '-d', '-B',
                                    meson.project_build_root(),
                                    '-M', objects, '--', root, '@OUTPUT@'],
                        depends: [auto_gen_events, py_clang_ast],
                        env: build_env,
                        install: true,
                        install_dir: py.get_install_dir(pure: false) / 'vortex/core/objects')
auto_structs_dep = declare_dependency(sources: [auto_structs])

foreach object : objects
    r = run_command(py, root / 'tools/find_modules.py',
                    '--object', object,
                    '--root', meson.current_source_dir(),
                    'files', check: true)
    sources = r.stdout().strip().split()
    library(object, sources + [auto_gen_types, auto_gen_events, auto_gen_vobj],
            include_directories: [core_include, core_include_general, core_threads_include],
            dependencies: [core_utils_dep, core_kinematics_dep, math, core_atomics_dep,
                           core_logging_dep, core_threads_dep],
            name_prefix: '',
            install: true,
            install_dir: py.get_install_dir(pure: false) / 'vortex/core/objects',
            link_args: ['-Wl,-rpath=$ORIGIN/../lib',
                        '-Wl,-rpath=$ORIGIN/../kinematics',
                        '-Wl,-rpath=$ORIGIN/../lib/atomics'])
endforeach

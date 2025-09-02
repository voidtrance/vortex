# vortex - GCode machine emulator
# Copyright (C) 2026 Mitko Haralanov
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
lib_clang = cc.find_library('clang', required: true)

clang_ast_include = include_directories('.')
clang_ast_lib = library('clang_ast', ['clang_ast.c'], install: false, dependencies: [lib_clang])
clang_ast_dep = declare_dependency(link_with: clang_ast_lib, include_directories: clang_ast_include)

py_clang_ast = custom_target('py_clang_ast', output: 'py_clang_ast.so',
                            input : root / 'tools/clang_ast/clang_ast_builder.py',
                            command : [py, '@INPUT@', '-I', '@CURRENT_SOURCE_DIR@',
                                        '-L', '@OUTDIR@'],
                            build_by_default: true,
                            install: false)

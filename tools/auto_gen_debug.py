#!/usr/bin/env python3
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
import sys
import os.path
import importlib.util

HEADER = """/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024  Mitko Haralanov
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
#ifndef __DEBUG_H__
#define __DEBUG_H__
#ifdef VORTEX_MEM_LEAK
#include "mem_debug.h"
#endif

"""
FOOTER = "\n#endif\n"
ROOT = sys.argv[1]
OUTPUT = os.path.join(ROOT, sys.argv[2])

spec = importlib.util.spec_from_file_location("ll",
                                              os.path.join(ROOT, "lib", "logging.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

level_dict = mod._levelToName
levels = sorted(level_dict.keys())
with open(OUTPUT, 'w') as fd:
    fd.write(HEADER)
    fd.write("typedef enum {\n")
    for value in levels:
        fd.write(f"    LOG_LEVEL_{level_dict[value].upper()} = {value},\n")
    fd.write("    LOG_LEVEL_MAX,\n")
    fd.write("} core_log_level_t;\n\n")

    fd.write("static const char *log_methods[] = {\n")
    for value in levels:
        if value:
            fd.write(f'    [LOG_LEVEL_{level_dict[value].upper()}] = "{level_dict[value].lower()}",\n')
    fd.write("};\n")

    fd.write("""
#define CORE_LOG(obj, level, fmt, ...)				\\
    (((core_object_t *)(obj))->call_data.log( \\
        (level), ((core_object_t *)(obj))->type,          \\
        ((core_object_t *)(obj))->name, (fmt), ##__VA_ARGS__))\n\n""")
    
    for value in levels:
        if value:
            nu = level_dict[value].upper()
            nl = level_dict[value].lower()
            fd.write(f'#define log_{nl}(o, fmt, ...) CORE_LOG(o, LOG_LEVEL_{nu}, fmt, ##__VA_ARGS__)\n')

    fd.write(FOOTER)
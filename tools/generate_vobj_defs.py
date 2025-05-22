#!/usr/bin/env python3
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
import sys
import ast
import pathlib
import argparse

VOBJ_DEF_HEADER = """/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2025 Mitko Haralanov
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
"""

VOBJ_DEF_H_PREFIX = VOBJ_DEF_HEADER + """
#ifndef __VOBJ_DEFS_H__
#define __VOBJ_DEFS_H__
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <objects/global.h>

"""

VOBJ_DEF_H_SUFFIX = "#endif\n"

def is_vobj(node):
    if not isinstance(node, ast.ClassDef):
        return False
    for base in node.bases:
        if isinstance(base, ast.Attribute) and \
            base.attr == "VirtualObjectBase":
            return True
    return False

def is_struct(node):
    if not isinstance(node, ast.ClassDef):
        return False
    for base in node.bases:
        if isinstance(base, ast.Attribute) and \
            base.attr == "Structure":
            return True
    return False

def get_type(type):
    if type.startswith("uint"):
        if type == "uint":
            return "unsigned int"
        return type + "_t"
    elif type == "ulong":
        return "unsigned long"
    elif type == "uchar":
        return "unsigned char"
    return type

def get_size(node):
    size = []
    if isinstance(node.left, ast.BinOp):
        f_name, ssize = get_size(node.left)
        size += ssize
    else:
        f_name = node.left.attr
    if isinstance(node.right, ast.Name):
        size.append(node.right.id)
    elif isinstance(node.right, ast.Constant):
        size.append(node.right.value)
    return f_name, size

def gen_commands(fd, name, commands, structs):
    fd.write("enum {\n")
    for cmd in commands:
        fd.write(f"\t{name.upper()}_{cmd[1].upper()} = {cmd[0]},\n")
    fd.write("};\n\n")
    for cmd in commands:
        cmd = cmd[1]
        c_arg_name = f"{name.lower()}_{cmd.lower()}_args"
        arg_name = "".join([x.capitalize() for x in c_arg_name.split("_")])
        if arg_name not in structs:
            return -1
        node = structs[arg_name]
        #print(ast.dump(node))
        fd.write(f"struct {c_arg_name} {{\n")
        for n in node.body:
            if not isinstance(n, ast.Assign) or n.targets[0].id != "_fields_":
                continue
            if not isinstance(n.value, ast.List):
                return -1
            fields = n.value
            for field in fields.elts:
                #print(ast.dump(field))
                if not isinstance(field, ast.Tuple):
                    return -1
                if isinstance(field.elts[1], ast.Attribute):
                    fd.write(f"\t{get_type(field.elts[1].attr[2:])} {field.elts[0].value};\n")
                elif isinstance(field.elts[1], ast.BinOp):
                    f_type, sizes = get_size(field.elts[1])
                    fd.write(f"\t{get_type(f_type[2:])} {field.elts[0].value}")
                    for size in sizes:
                        fd.write(f"[{size}]")
                    fd.write(";\n")
        fd.write("};\n\n")
    return 0

def gen_status(fd, name, structs):
    fd.write("typedef struct {\n")
    c_arg_name = f"{name.lower()}_state"
    arg_name = "".join([x.capitalize() for x in c_arg_name.split("_")])
    if arg_name not in structs:
        return -1
    node = structs[arg_name]
    #print(ast.dump(node))
    for n in node.body:
        if not isinstance(n, ast.Assign) or n.targets[0].id != "_fields_":
            continue
        if not isinstance(n.value, ast.List):
            return -1
        fields = n.value
        for field in fields.elts:
            if not isinstance(field, ast.Tuple):
                return -1
            if isinstance(field.elts[1], ast.Attribute):
                fd.write(f"\t{get_type(field.elts[1].attr[2:])} {field.elts[0].value};\n")
            elif isinstance(field.elts[1], ast.BinOp):
                f_type, sizes = get_size(field.elts[1])
                #print(f_type, sizes)
                fd.write(f"\t{get_type(f_type[2:])} {field.elts[0].value}")
                for size in sizes:
                    fd.write(f"[{size}]")
                fd.write(";\n")
    fd.write(f"}} {name.lower()}_status_t;\n\n")
    return 0

def gen_header(target, name, defs, structs):
    header = target / name
    with open(header, 'w') as out:
        out.write(VOBJ_DEF_H_PREFIX)
        for obj in defs:
            ret = gen_commands(out, obj, defs[obj]["commands"], structs)
            if ret != 0:
                return ret
            ret = gen_status(out, obj, structs)
            if ret != 0:
                return ret
        out.write(VOBJ_DEF_H_SUFFIX)
    return 0

def gen_vobj_defs(root, target, name):
    vobj_defs = {}
    structs = {}
    for filename in (root / "controllers/objects").iterdir():
        if filename.suffix != ".py":
            continue
        with open(filename, 'r') as fd:
            tree = ast.parse(fd.read(), filename)
        for node in ast.walk(tree):
            if not is_vobj(node) and not is_struct(node):
                continue
            if is_struct(node):
                structs[node.name] = node
                continue
            obj_type = ""
            for b in node.body:
                if isinstance(b, ast.Assign) and \
                    b.targets[0].id == "type":
                    obj_type = b.value.attr
                if not isinstance(b, ast.Assign) or \
                    b.targets[0].id not in ("commands", "status"):
                    continue
                if obj_type not in vobj_defs:
                    vobj_defs[obj_type] = {"commands": [], "status": None}
                if b.targets[0].id == "commands":
                    commands = b.value
                    if not isinstance(commands, ast.List):
                        return -1
                    for cmd in commands.elts:
                        if not isinstance(cmd, ast.Tuple):
                            return -1
                        c = (cmd.elts[0].value, cmd.elts[1].value, cmd.elts[2].id)
                        vobj_defs[obj_type]["commands"].append(c)
                else:
                    vobj_defs[obj_type]["status"] = b.value.id

                #if b.targets[0].id == "commands":
                #    vobj_defs[obj_type]["commands"] = c
                #else:

    return gen_header(target, name, vobj_defs, structs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=str)
    parser.add_argument("--target", type=str, default=".")
    parser.add_argument("filename", type=str)

    opts = parser.parse_args()

    return gen_vobj_defs(pathlib.Path(opts.root), 
                  pathlib.Path(opts.target), 
                  opts.filename)

sys.exit(main())
#!/usr/bin/env python3
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
import re
import sys
import ast
import pathlib
import argparse
import py_clang_ast

clang_ast_ffi = py_clang_ast.ffi
clang_ast_lib = py_clang_ast.lib

OBJECT_DEF_HEADER = """# vortex - GCode machine emulator
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
import ctypes
from argparse import Namespace
from vortex.core import ObjectKlass, ObjectEvents
from vortex.lib.ext_enum import ExtIntEnum

################################################################
##                                                            ##
##    This file is auto-generated. Please, do not edit it     ##
##    unless you know what you are doing.                     ##
##                                                            ##
################################################################

class ObjectDef(Namespace):
    virtual = False
    def __init__(self, type=ObjectKlass.NONE):
        self.type = type
        self.config = getattr(self, str(type).capitalize() + "ConfigParams", None)
        self.state = getattr(self, str(type).capitalize() + "Status", None)
        self.commands = []
        self.events = {}

"""

C_TYPE_MAP = {
    "int" : "ctypes.c_int",
    "long" : "ctypes.c_long",
    "long long" : "ctypes.c_longlong",
    "unsigned" : "ctypes.c_uint",
    "unsigned long" : "ctypes.c_ulong",
    "unsigned long long" : "ctypes.c_ulonglong",
    "double" : "ctypes.c_double",
    "float" : "ctypes.c_float",
    "_Bool" : "ctypes.c_bool",
    "size_t" : "ctypes.c_size_t",
    "ssize_t" : "ctypes.c_ssize_t",
    "short" : "ctypes.c_short",
    "ushort" : "ctypes.c_ushort",
    "char" : "ctypes.c_char",
    "char *" : "ctypes.c_char_p",
    "void *" : "ctypes.c_void_p",
    "int8_t" : "ctypes.c_int8",
    "int16_t" : "ctypes.c_int16",
    "int32_t" : "ctypes.c_int32",
    "int64_t" : "ctypes.c_int64",
    "uint8_t" : "ctypes.c_uint8",
    "uint16_t" : "ctypes.c_uint16",
    "uint32_t" : "ctypes.c_uint32",
    "uint64_t" : "ctypes.c_uint64",
}

TYPE_DEFAULT_MAP = {
    "int" : 0,
    "long" : 0,
    "long long" : 0,
    "unsigned" : 0,
    "unsigned long" : 0,
    "unsigned long long" : 0,
    "double" : 0.0,
    "float" : 0.0,
    "_Bool" : False,
    "size_t" : 0,
    "ssize_t" : 0,
    "short" : 0,
    "ushort" : 0,
    "char" : "",
    "char *" : None,
    "void *" : None,
    "int8_t" : 0,
    "int16_t" : 0,
    "int32_t" : 0,
    "int64_t" : 0,
    "uint8_t" : 0,
    "uint16_t" : 0,
    "uint32_t" : 0,
    "uint64_t" : 0,
}

__LOG_LEVEL = 0
LOG_LEVEL_INFO = 1
LOG_LEVEL_VERBOSE = 2
LOG_LEVEL_DEBUG = 3

def log(level, *args, **kwargs):
    if level <= __LOG_LEVEL:
        print(*args, **kwargs, file=sys.stderr, flush=True)

def find_virtual_objects(top):
    objects = []
    object_reg = re.compile(r'^class (?P<klass>[^\(]+)\([^.]*.?VirtualObjectBase\):$', re.MULTILINE)
    for file in (top / "controllers/objects/virtual").iterdir():
        if file.is_dir():
            continue
        with open(file, 'r') as fd:
            for line in fd:
                match = object_reg.match(line)
                if not match:
                    continue
                objects.append((match.group("klass").strip(), file))
    return objects

def find_new_types(object_list):
    new_types = []
    new_events = []
    for object in object_list:
        with open(object[1], 'r') as fd:
            source = fd.read()
            node = ast.parse(source)
            for node in node.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                for cnode in node.body:
                    if not isinstance(cnode, ast.Assign):
                        continue
                    if cnode.targets[0].id == "type":
                        if cnode.value.value.id != "ObjectKlass":
                            continue
                        if cnode.value.attr not in new_types:
                            new_types.append(cnode.value.attr)
                    elif cnode.targets[0].id == "events":
                        if not isinstance(cnode.value, ast.List):
                            continue
                        lnode = cnode.value
                        for elnt in lnode.elts:
                            if elnt.value.id != "ObjectEvents":
                                continue
                            if elnt.attr not in new_events:
                                new_events.append(elnt.attr)
    return new_types, new_events

def gen_types(top, output_file, types):
    content = list()
    with open(top / f"{output_file}.in", 'r') as fd:
        for line in fd:
            if "@EXTRA_KLASSES@" not in line and \
                "@EXTRA_KLASS_NAMES@" not in line and \
                "@EXTRA_KLASS_EXPORT_NAMES@" not in line:
                content.append(line)
                continue
            if "@EXTRA_KLASSES@" in line:
                content += [" " * 4 + f"OBJECT_KLASS_{x.upper()},\n" \
                            for x in types]
            elif "@EXTRA_KLASS_EXPORT_NAMES@" in line:
                content += [" " * 4 + \
                            f"[OBJECT_KLASS_{x.upper()}] = stringify(OBJECT_KLASS_{x.upper()}),\n" \
                            for x in types]
                
            elif "@EXTRA_KLASS_NAMES@":
                content += [" " * 4 + \
                            f"[OBJECT_KLASS_{x.upper()}] = \"{x.lower()}\",\n" \
                            for x in types]

    with open(output_file, 'w') as fd:
        fd.write("".join(content))

def gen_events(top, output_file, events):
    content = list()
    with open(top / f"{output_file}.in", 'r') as fd:
        for line in fd:
            if "@EXTRA_EVENTS@" not in line and \
                "@EXTRA_EVENT_NAMES@" not in line:
                content.append(line)
                continue
            if "@EXTRA_EVENTS@" in line:
                content += [" " * 4 + f"OBJECT_EVENT_{x.upper()},\n" \
                           for x in events]
            elif "@EXTRA_EVENT_NAMES@" in line:
                content += [" " * 4 + \
                         f"[OBJECT_EVENT_{x.upper()}] = \"{x.upper()}\",\n" \
                            for x in events]
                

    with open(output_file, 'w') as fd:
        fd.write("".join(content))

PY_INDENT_PREFIX = " " * 4

def ffi_string(str_ptr):
    return clang_ast_ffi.string(str_ptr).decode() if str_ptr != clang_ast_ffi.NULL else "null"

def py_struct_name(name, c_struct_name):
    parts = c_struct_name.split("_")
    if parts[-1] == "t":
        parts = parts[:-1]
    if parts and parts[0].lower() != name.lower():
        parts.insert(0, name.capitalize())
    return "".join([x.capitalize() for x in parts])

def py_enum_name(name, c_enum_name):
    parts = c_enum_name.split("_")
    if parts[-1] == "t":
        parts = parts[:-1]
    if parts and parts[0] != name.lower():
        parts.insert(0, name.capitalize())
    return "".join([x.capitalize() for x in parts])

def is_unnamed(node):
    name = ffi_string(node.base.name)
    return "unnamed" in name

def get_struct_name(node):
    struct_name = ffi_string(node.name)
    if is_unnamed(node):
        parent = clang_ast_lib.clang_node_get_parent(node)
        if parent != clang_ast_ffi.NULL and parent.kind == clang_ast_lib.TypedefDecl:
            struct_name = ffi_string(parent.name)
        else:
            child = clang_ast_lib.clang_node_next(node, clang_ast_lib.FieldDecl)
            if child != clang_ast_ffi.NULL:
                struct_name = ffi_string(child.name)
    return struct_name

def py_type(c_type):
    if c_type in C_TYPE_MAP:
        return C_TYPE_MAP[c_type]
    return None

def py_member_type(name, c_type, structs, node):
    py_member_type = py_type(c_type)
    if py_member_type:
        return py_member_type

    py_member_type = structs.get(c_type, py_struct_name(name, get_struct_name(node)))
    return py_member_type["name"] if isinstance(py_member_type, dict) else py_member_type

def get_member_default(member_type, structs):
    if member_type in TYPE_DEFAULT_MAP:
        return TYPE_DEFAULT_MAP[member_type]
    elif member_type in structs:
        return structs[member_type]["defaults"]
    return None

def find_py_struct(structs, name):
    struct = [x for x in structs if structs[x]["name"] == name]
    return struct[0] if struct else None

def generate_enum(name, c_enum, structs):
    enum_name = ffi_string(c_enum.name)
    enum_name = py_enum_name(name, enum_name)
    s = {"name": enum_name, "usedby":[], "requires":[], "enum": False, "def":"", "defaults": []}
    s["def"] += f"{PY_INDENT_PREFIX}class {enum_name}(ExtIntEnum):\n"
    member = clang_ast_lib.clang_node_next(c_enum, clang_ast_lib.EnumConstantDecl)
    while member != clang_ast_ffi.NULL:
        s["def"] += f"{PY_INDENT_PREFIX * 2}{ffi_string(member.name).upper()} = " + \
            f"({member.base.enum_constant.value}, \"{ffi_string(member.name).upper()}\")\n"
        member = clang_ast_lib.clang_node_next(c_enum, clang_ast_lib.EnumConstantDecl)

    s["defaults"].append(0)
    s["enum"] = True
    structs[ffi_string(c_enum.name)] = s
    return 0

def log_struct_def(struct):
    STRUCT_PREFIX = " " * 5
    STRUCT_MEMBER_PREFIX = " " * 8
    log(LOG_LEVEL_DEBUG, f"{STRUCT_PREFIX}struct def={{")
    for key in struct.keys():
        log(LOG_LEVEL_DEBUG, f"{STRUCT_MEMBER_PREFIX}{key} = {struct[key]}")
    log(LOG_LEVEL_DEBUG, f"{STRUCT_PREFIX}}}")

def generate_struct(name, node, struct_name, structs, prereqs):
    struct_name = get_struct_name(node)
    if struct_name in structs:
        return 0

    # First, generate dependecies.
    # This effectively ensures that all child structures are parsed
    # first in order to be able to use them when generating "this"
    # structure.
    member = clang_ast_lib.clang_node_first(node, clang_ast_lib.Any)
    while member != clang_ast_ffi.NULL:
        if member.kind == clang_ast_lib.StructDecl:
            ret = generate_struct(name, member, ffi_string(member.name), structs, prereqs)
            if ret:
                return ret
        member = clang_ast_lib.clang_node_next(node, clang_ast_lib.Any)

    class_name = py_struct_name(name, struct_name)
    s = {"name": class_name, "usedby":[], "requires":[], "enum":False, "def":"", "defaults" : []}
    s["def"] += f"{PY_INDENT_PREFIX}class {class_name}(ctypes.Structure):\n" + \
        f"{PY_INDENT_PREFIX * 2}_fields_ = [\n"

    # Go through all of the structure fields/members and generate
    # _fields_ entries.
    member = clang_ast_lib.clang_node_first(node, clang_ast_lib.Any)
    while member != clang_ast_ffi.NULL:
        member_name = ffi_string(member.name)
        if member.kind != clang_ast_lib.StructDecl:
            member_type = ffi_string(member.base.name)
            member_clang_type = member.base
            log(LOG_LEVEL_DEBUG, f"member_name={member_name}")
            log(LOG_LEVEL_DEBUG, f"     type={member_type}, type_name={ffi_string(member_clang_type.name)}")
            log(LOG_LEVEL_DEBUG, f"          type_val={member_clang_type.type}")

            # Check if this member could be an structure
            # defined within the structure. If so, generated it.
            if member_clang_type.type in (clang_ast_lib.Elaborated, clang_ast_lib.Record):
                child = clang_ast_lib.clang_node_first(member, clang_ast_lib.Any)
                if child.kind == clang_ast_lib.StructDecl:
                    ret = generate_struct(name, child, ffi_string(member.name), structs, prereqs)
                    if ret:
                        return ret

            # Process any type qualifiers. If any of the types are
            # qualified, use the canonical member type.
            if member.base.qualifier != clang_ast_lib.Q_NONE or \
                member.canonical.qualifier != clang_ast_lib.Q_NONE:
                member_type = ffi_string(member.canonical.name)
                member_clang_type = member.canonical
            py_member_t = py_member_type(name, member_type, structs, member)
            log(LOG_LEVEL_DEBUG, f"     py_member_t={py_member_t} unnamed={is_unnamed(member)}")

            # The member type could be referring to any of the structures that
            # are pre-requisites - structures defined in other headers but used
            # within the objects.
            if member_type in prereqs:
                py_member_t = py_struct_name("", member_type)
                if member_type in prereqs and prereqs[member_type]["enum"]:
                    py_member_t = py_member_type(name, "int", structs, member)

            py_struct_t = py_member_t
            member_default = get_member_default(member_type, structs)

            if member_type in structs and structs[member_type]["enum"]:
                py_struct_t = py_member_type(name, "int", structs, member)

            if member_clang_type.type == clang_ast_lib.ConstantArray:
                # If the member is a constant array, go through the type and
                # generated any multi-dimentional arrays needed.
                member_default = get_member_default(ffi_string(member_clang_type.array.name), structs)
                py_member_t = py_member_type(name, ffi_string(member_clang_type.array.name), structs,
                                             member)
                for x in range(member_clang_type.array.n_dims - 1, -1, -1):
                    if x == member_clang_type.array.n_dims - 1:
                        py_struct_t = f"({py_member_t} * {member_clang_type.array.sizes[x]})"
                    else:
                        py_struct_t = f"({py_struct_t} * {member_clang_type.array.sizes[x]})"
            elif member_clang_type.type == clang_ast_lib.Pointer:
                # If the member is a pointer, generate the ctypes pointers
                member_default = get_member_default(ffi_string(member_clang_type.pointer.name), structs)
                py_member_t = py_member_type(name, ffi_string(member_clang_type.pointer.name), structs,
                                             member)
                py_struct_t = f"ctypes.POINTER({py_member_t})"

            # Generate the dependencies for this structure.
            if py_member_t in [x["name"] for x in structs.values()] or \
                py_member_t not in C_TYPE_MAP.values():
                used = find_py_struct(structs, py_member_t)
                if used:
                    structs[used]["usedby"] = struct_name
                    s["requires"].append(used)
                elif member_type in prereqs:
                    s["requires"].append(py_member_t)

            # Add the _field_ to the Python structure and set default
            # value for the member.
            s["def"] += f"{PY_INDENT_PREFIX * 5}(\"{member_name}\", {py_struct_t}),\n"
            if not isinstance(member_default, list):
                member_default = [member_default]
            s["defaults"] += member_default
        member = clang_ast_lib.clang_node_next(node, clang_ast_lib.Any)
    s["def"] += f"{PY_INDENT_PREFIX * 5}]\n"
    log_struct_def(s)
    structs[struct_name] = s
    return 0

def process_module_requirements(struct, structs):
    # Generate requirements first
    req_structs = ""
    struct = structs.pop(struct)
    for req in struct["requires"]:
        c_struct_name = [x for x in structs if structs[x]["name"] == req]
        if c_struct_name:
            req_structs += process_module_requirements(c_struct_name[0], structs)
    for line in struct["def"].split("\n"):
        req_structs += line.removeprefix(PY_INDENT_PREFIX) + "\n"
    return req_structs

def get_object_defs(top, module, build_top, prereqs_list):
    object_dir = top / "src" / "core" / "objects"
    event_enum_file = build_top / "src" / "core" / "objects" / "auto-events.h"

    # Create a translation unit for the events header file.
    # The event enum is in a different file because all events from
    # all objects are in a single, unified enum.
    # Therefore, it needs to be parsed first so the event definitions
    # can be used for the individual objects
    event_unit = clang_ast_lib.clang_unit_init(bytes(event_enum_file.as_posix(), "ascii"))
    if event_unit == clang_ast_ffi.NULL:
        return None

    if not clang_ast_lib.clang_unit_parse(event_unit):
        print("Parsing of event file failed")
        return None

    node = clang_ast_lib.clang_node_find_by_name(event_unit.root, b"core_object_event_type_t",
                                                 clang_ast_lib.EnumDecl)
    if node == clang_ast_ffi.NULL:
        print(f"Object event enum not found for '{module}'")
        clang_ast_lib.clang_unit_destroy(event_unit)
        return None

    object_events = {}
    member = clang_ast_lib.clang_node_first(node, clang_ast_lib.EnumConstantDecl)
    while member != clang_ast_ffi.NULL:
        event = ffi_string(member.name)
        value = member.base.enum_constant.value
        event = event.removeprefix("OBJECT_EVENT_")
        try:
            object_name, event_name = event.split("_", 1)
            if object_name.lower() not in object_events:
                object_events[object_name.lower()] = []
            object_events[object_name.lower()].append((event, value))
        except ValueError:
            break
        member = clang_ast_lib.clang_node_next(node, clang_ast_lib.EnumConstantDecl)

    clang_ast_lib.clang_unit_destroy(event_unit)

    # Now, start working with the actual object header file
    object_file = object_dir / (module + ".h")
    unit = clang_ast_lib.clang_unit_init(bytes(object_file.as_posix(), "ascii"))
    if unit == clang_ast_ffi.NULL:
        return None

    if not clang_ast_lib.clang_unit_parse(unit):
        print(f"Parsing of object file '{object_file.name}' failed")
        return None

    struct_set = {}

    # Parse all enumerations.
    # Those don't have structure dependencies so can be processed and parsed
    # first.
    c_enum = clang_ast_lib.clang_node_find(unit.root, clang_ast_lib.EnumDecl)
    while c_enum != clang_ast_ffi.NULL:
        ret = generate_enum(module, c_enum, struct_set)
        if ret:
            return None
        c_enum = clang_ast_lib.clang_node_find_next(c_enum, clang_ast_lib.EnumDecl)

    module_def = ""

    # Parse all structures and create a list keyed by the C structure name
    #  1. Process any structures that are children of typedef's
    typedef = clang_ast_lib.clang_node_next(unit.root, clang_ast_lib.TypedefDecl)
    while typedef != clang_ast_ffi.NULL:
        name = ffi_string(typedef.name)
        struct = clang_ast_lib.clang_node_first(typedef, clang_ast_lib.StructDecl)
        if struct != clang_ast_ffi.NULL:
            ret = generate_struct(module, struct, name, struct_set, prereqs_list)
            if ret:
                return None
        typedef = clang_ast_lib.clang_node_next(unit.root, clang_ast_lib.TypedefDecl)

    #  2. Process named structus
    clang_ast_lib.clang_node_reset(unit.root)
    struct = clang_ast_lib.clang_node_next(unit.root, clang_ast_lib.StructDecl)
    while struct != clang_ast_ffi.NULL:
        parent = clang_ast_lib.clang_node_get_parent(struct)
        if parent.kind == clang_ast_lib.TypedefDecl:
            struct_name = ffi_string(parent.name)
        else:
            struct_name = ffi_string(struct.name)
        generate_struct(module, struct, struct_name, struct_set, prereqs_list)
        struct = clang_ast_lib.clang_node_next(unit.root, clang_ast_lib.StructDecl)

    def def_strip(body):
        return "\n".join([line.removeprefix(PY_INDENT_PREFIX) for line in body.split("\n")])

    for struct in list(struct_set):
        current = struct_set.get(struct, None)
        if not current:
            continue
        if not current["requires"] and current["usedby"]:
            module_def += def_strip(current["def"]) + "\n"
            del struct_set[struct]
            continue
        if current["requires"] and current["usedby"]:
            for req in current["requires"]:
                req = struct_set.pop(req, None)
                if req:
                    module_def += def_strip(req["def"]) + "\n"
            module_def += def_strip(current["def"]) + "\n"
            del struct_set[struct]
            continue

    module_def += f"class {module.capitalize()}(ObjectDef):\n"
    for struct in struct_set.values():
        module_def += struct["def"] + "\n"
    module_def += f"{PY_INDENT_PREFIX}def __init__(self):\n"
    module_def += f"{PY_INDENT_PREFIX * 2}super().__init__(ObjectKlass.{module.upper()})\n"

    # If the module has any commands, generate them.
    if f"{module.lower()}_commands" in struct_set:
        clang_ast_lib.clang_node_reset(unit.root)
        node = clang_ast_lib.clang_node_find_by_name(unit.root,
                                                      bytes(f"{module.lower()}_commands",
                                                            "ascii"),
                                                            clang_ast_lib.Any)
        if node == clang_ast_ffi.NULL:
            print(f"Failed to find '{module}' object command enum!", file=sys.stderr)
            return None
        module_def += f"{PY_INDENT_PREFIX * 2}self.commands = [\n"
        enum_member = clang_ast_lib.clang_node_first(node, clang_ast_lib.Any)
        while enum_member != clang_ast_ffi.NULL:
            enum_name = ffi_string(enum_member.name)
            _, _, cmd = enum_name.split("_", 2)
            cmd_args_name = py_struct_name(module, cmd + "_args")
            for struct in struct_set.values():
                data_args_name = py_struct_name(module, cmd + "_data")
                data_struct = [struct for struct in struct_set.values() \
                               if struct["name"] == data_args_name]
                if struct["name"] == cmd_args_name:
                    module_def += f"{PY_INDENT_PREFIX * 4}({enum_member.base.enum_constant.value}, " + \
                                 f" \"{cmd.lower()}\", self.{cmd_args_name}, " + \
                                 f"{'self.' + data_args_name if data_struct else "None"}, " + \
                                    f"{tuple(struct["defaults"])}),\n"
            enum_member = clang_ast_lib.clang_node_next(node, clang_ast_lib.EnumConstantDecl)
        module_def += f"{PY_INDENT_PREFIX * 4}]\n"

    # Now, lastly, generate object event set
    if module in object_events:
        module_def += f"{PY_INDENT_PREFIX * 2}self.events = {{\n"
        for event in object_events[module]:
            event_name, _ = event
            event_struct_name = event_name.lower() + "_event_data_t"
            if event_struct_name not in struct_set:
                print(f"No event data structure for object '{module}'")
                return None
            event_struct_name = py_struct_name(module, event_struct_name)
            module_def += f"{PY_INDENT_PREFIX * 5}ObjectEvents.{event_name}: self.{event_struct_name},\n"
        module_def += f"{PY_INDENT_PREFIX * 4}}}\n"

    module_def += "\n"
    clang_ast_lib.clang_unit_destroy(unit)
    return module_def

def process_object_prereq_files(top, filename, structs):
    struct_set = {}
    file = top / (filename + ".h")
    unit = clang_ast_lib.clang_unit_init(bytes(file.as_posix(), "ascii"))
    if unit == clang_ast_ffi.NULL:
        return struct_set

    if not clang_ast_lib.clang_unit_parse(unit):
        print("Parsing of event file failed")
        return struct_set

    for struct in structs:
        node = clang_ast_lib.clang_node_find_by_name(unit.root, bytes(struct, "ascii"),
                                                     clang_ast_lib.Any)
        if node == clang_ast_ffi.NULL:
            print(f"Object event enum not found for '{filename}'")
            break

        if node.kind == clang_ast_lib.TypedefDecl:
            node = clang_ast_lib.clang_node_first(node, clang_ast_lib.Any)
            if node == clang_ast_ffi.NULL:
                return struct_set

        if node.kind == clang_ast_lib.EnumDecl:
            generate_enum(filename, node, struct_set)
        elif node.kind == clang_ast_lib.StructDecl:
            generate_struct(filename, node, ffi_string(node.name), struct_set, list(struct_set.keys()))
            
    clang_ast_lib.clang_unit_destroy(unit)
    return struct_set


def main():
    global __LOG_LEVEL

    parser = argparse.ArgumentParser()
    exc = parser.add_mutually_exclusive_group(required=True)
    exc.add_argument("-e", dest="events", action="store_true", help="Generate events.")
    exc.add_argument("-o", dest="objects", action="store_true", help="Generate objects.")
    exc.add_argument("-d", dest="defs", action="store_true", help="Generate object defs.")
    parser.add_argument("-B", dest="build_dir", help="Top build directory")
    parser.add_argument("-M", dest="module", nargs="+", help="Name of module for which to generate header")
    parser.add_argument("-v", dest="verbose", default=0, action="count", help="Increase verbosity level")
    parser.add_argument("top_dir", help="Top source directory.")
    parser.add_argument("output_file", help="Output filename.")

    args = parser.parse_args()
    top = pathlib.PosixPath(args.top_dir)
    output_file = pathlib.PosixPath(args.output_file)

    if args.events or args.objects:
        objects = find_virtual_objects(top)
        types, events = find_new_types(objects)
        if args.objects:
            gen_types(top, output_file, types)
        else:
            gen_events(top, output_file, events)
    else:
        __LOG_LEVEL = args.verbose
        clang_ast_lib.clang_set_verbose_level(args.verbose)
        ret = 0
        prereqs = process_object_prereq_files(top / "src" / "core" / "kinematics", "kinematics",
                                        ["kinematics_axis_type_t", "kinematics_coordinates_t"])
        if not prereqs:
            print("Failed to find pre-requisite structures")
            return 1

        build_top = pathlib.PosixPath(args.build_dir)
        output = open(output_file, "w")
        output.write(OBJECT_DEF_HEADER)

        for struct in prereqs.values():
            for line in struct["def"].split("\n"):
                output.write(line.removeprefix(PY_INDENT_PREFIX) + "\n")

        for module in args.module:
            output.write(f"# ============== {module.upper()} Definitions ================\n\n")
            module_def = get_object_defs(top, module, build_top, prereqs)
            if module_def:
                output.write(module_def)
            else:
                print(f"Failed to create Python definition for '{module}'")
                ret = 1
        output.close()
        if ret:
            return ret

    return 0

sys.exit(main())

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
import re
import os
import enum
import pprint
import pathlib
import argparse
from clang import cindex

HEADER = """# vortex - GCode machine emulator
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
import enum
from argparse import Namespace
from vortex.lib.ext_enum import ExtIntEnum, auto, unique

@unique
class ResponseTypes(ExtIntEnum):
    ACK = auto()
    NACK = auto()
    RESPONSE = auto()
"""

PREFIX  = " " * 4

class ProtocolType(enum.IntEnum):
    NONE = 0
    COMMAND = 1
    RESPONSE = 2
    TASK = 3
    SHUTDOWN = 4
    STATIC_STRING = 5

# This regular expression is used to parse
# Klipper command flags since Clang AST does
# not provide nodes for #define's.
reg_cmd = re.compile(r'^DECL_COMMAND(?:_FLAGS)?\((?P<handler>[^,]+),\s*(?:(?P<flag>[^,]+),\s*)*\"(?P<cmd>[^\"]+)\"\);$')

def parse_file(filename):
    index = cindex.Index.create()
    tu = index.parse(filename)
    return tu

def find_command_string(node):
    if node.kind == cindex.CursorKind.STRING_LITERAL:
        string_literal = node.spelling[1:-1]
        decl, command = string_literal.split(maxsplit=1)
        if decl == "_DECL_CALLLIST":
            call_list, func = command.split(maxsplit=1)
            if call_list == "ctr_run_taskfuncs":
                return ProtocolType.TASK, (func,)
        elif decl == "_DECL_STATIC_STR":
            return ProtocolType.STATIC_STRING, (command,)
        elif decl == "DECL_COMMAND_FLAGS":
            func, flags, command = command.split(maxsplit=2)
            return ProtocolType.COMMAND, (func, int(flags, 16), command)
        return ProtocolType.NONE, ()
    for child in node.get_children():
        type, data = find_command_string(child)
        if type is not ProtocolType.NONE:
            return type, data
    return ProtocolType.NONE, ()

def parse_commands(node, p=0):
    commands = []
    if node.kind == cindex.CursorKind.VAR_DECL and \
        node.spelling.startswith("_DECLS_"):
        # Unfortunately, we don't get the "DECL_COMMAND_*" macros
        # as an AST node so we have to parse the literal string.
        type, data = find_command_string(node)
        if type is not ProtocolType.NONE:
            commands.append((type, data))
    for child in node.get_children():
        commands +=  parse_commands(child, p+2)
    return commands

def get_response_string(node):
    if node.kind == cindex.CursorKind.STRING_LITERAL:
        string_literal = node.spelling[1:-1]
        decl, response = string_literal.split(maxsplit=1)
        if decl =="_DECL_ENCODER":
            return response
        return None
    for child in node.get_children():
        response = get_response_string(child)
        if response is not None:
            return response
    return None

def find_response_call(node):
    if node.kind == cindex.CursorKind.CALL_EXPR and \
        node.spelling == "command_sendf":
        return node
    for child in node.get_children():
        node = find_response_call(child)
        if node is not None:
            return node
    return None

def parse_response(node):
    responses = []
    if node.kind == cindex.CursorKind.FUNCTION_DECL:
        call_node = find_response_call(node)
        if call_node is not None:
            responses.append((ProtocolType.RESPONSE, (node.spelling, get_response_string(call_node))))
    for child in node.get_children():
        responses += parse_response(child)
    return responses

def parse_flag_names(filename):
    with open(filename, "r") as fd:
        content = fd.readlines()
    flags = []
    for i in range(len(content)):
        line = content[i]
        # When it comes to the command declaration calls,
        # Klipper's coding style is inconsistent. With
        # all of the variations, it's hard to come up with
        # a single regular expression.
        # It's much easier to just combine all of the call
        # lines into one.
        string = line.strip()
        if not string.startswith("DECL_COMMAND"):
            continue
        while not string.endswith(");"):
            string += content[i+1].strip()
            i += 1
        string = string.replace('""', '')
        if '//' in string or '/*' in string:
            continue
        m = reg_cmd.match(string)
        if m:
            if m["flag"] and m["flag"] not in flags:
                flags.append(m["flag"])
    return flags

def get_flag_value(filename, flag):
    with open(filename, "r") as fd:
        for line in fd:
            line = line.strip()
            if line.startswith(f"#define {flag}"):
                parts = line.split(maxsplit=3)
                return int(parts[2], 16)
    return None

def get_git_version(src_dir):
    curdir = os.getcwd()
    os.chdir(src_dir)
    sha = os.popen(f"git -C {src_dir} describe --always --tags --long").read().strip()
    os.chdir(curdir)
    return sha

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="klipper_proto.py",
                        help="Output file")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("source", type=str, help="Klipper source directory")

    args = parser.parse_args()

    klipper_src = pathlib.PosixPath(args.source)
    if not (klipper_src / "src").exists():
        print(f"Klipper source path {klipper_src} does not contain a 'src' directory")
        return 1

    protocol = {}
    flag_names = []
    for filename in (klipper_src / "src").iterdir():
        if filename.suffix != ".c":
            continue
        flag_names += parse_flag_names(filename)
        ast = parse_file(filename)
        protocol[filename.stem] = parse_commands(ast.cursor)
        protocol[filename.stem] += parse_response(ast.cursor)

    if (args.debug):
        pprint.pprint(protocol)

    flags = {"HF_NONE": 0}
    flags.update(dict.fromkeys(flag_names, -1))
    for filename in (klipper_src / "src").iterdir():
        if filename.is_dir():
            continue
        for flag in flags:
            value = get_flag_value(filename, flag)
            if value is not None:
                flags[flag] = value

    proto_fd = open(args.output, "w")
    proto_fd.write(HEADER)

    proto_fd.write("\n")
    proto_fd.write("# Klipper command flags\n")
    proto_fd.write("class KlipperProtoFlags(enum.Flag):\n")
    for flag, value in flags.items():
        proto_fd.write(f"{PREFIX}{flag.upper()} = {value}\n")

    proto_fd.write("\n")
    proto_fd.write("KLIPPER_PROTOCOL = Namespace(\n")
    for namespace in protocol:
        if protocol[namespace]:
            proto_fd.write(f"{PREFIX}{namespace}=Namespace(),\n")
    proto_fd.write(")\n\n")

    klipper_ver = get_git_version(klipper_src)
    proto_fd.write(f"KLIPPER_PROTOCOL.version = \"{klipper_ver}\"\n\n")

    strings = []
    for namespace in protocol:
        if not protocol[namespace]:
            continue
        proto_fd.write(f"# {namespace} commands\n")
        # Generate command/response pairs.
        used_responses = []
        for command in protocol[namespace]:
            type = command[0]
            data = command[1]
            if type == ProtocolType.STATIC_STRING:
                strings.append(data[0])
            elif type == ProtocolType.COMMAND:
                cmd_name = data[0][8:]
                for flag_name, flag_value in flags.items():
                    if flag_value == data[1]:
                        break
                # find reponse
                response = None
                for r in protocol[namespace]:
                    if r[0] == ProtocolType.RESPONSE and r[1][0] == data[0]:
                        response = r[1][1]
                        used_responses.append(r)
                # The section below attempts to find the response to
                # a perioding query command that runs as a task.
                # It takes advantage of the fact that each periodic
                # tasks is started using a "query_*" or "*_query"
                # command.
                if response is None and "query" in data[2]:
                    head = data[2].split()[0]
                    if head.startswith("query"):
                        kind = head[6:]
                    elif head.endswith("query"):
                        kind = head[:7]
                    for r in protocol[namespace]:
                        if r[0] == ProtocolType.RESPONSE and r[1][0] == f"{kind}_task":
                            response = r[1][1]
                            used_responses.append(r)
                proto_fd.write(f"KLIPPER_PROTOCOL.{namespace}.{cmd_name} = Namespace(command=\"{data[2]}\", flags=KlipperProtoFlags.{flag_name}, response=")
                proto_fd.write(f"\"{response}\")\n" if response else "None)\n")
        # Generate response-only commands.
        for command in protocol[namespace]:
            type = command[0]
            data = command[1]
            if type == ProtocolType.RESPONSE and command not in used_responses and \
                data[1]:
                cmd_name = data[1].split()[0]
                proto_fd.write(f"KLIPPER_PROTOCOL.{namespace}.{cmd_name} = Namespace(command=None, flags=None, response=\"{data[1]}\")\n")
        proto_fd.write("\n")

    proto_fd.write("\n")
    proto_fd.write("# Static strings\n")
    proto_fd.write(f"KLIPPER_PROTOCOL.strings = [\n")
    for string in strings:
        proto_fd.write(f"{PREFIX}\"{string}\",\n")
    proto_fd.write("]\n")
    proto_fd.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())


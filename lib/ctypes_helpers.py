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
import ctypes
import vortex.core.lib.logging as logging
from _ctypes import _Pointer
# This is only to get access to ConfigParser.BOOLEAN_STATES
from configparser import ConfigParser
from argparse import Namespace

def is_simple_char_array(ctype):
    return issubclass(ctype, ctypes.Array) and \
        (ctype._type_ == ctypes.c_char or ctype._type_ == ctypes.c_char_p)

def is_simple_pointer(ctype):
    return isinstance(ctype, _Pointer)

def is_simple(ctype):
    if is_simple_char_array(ctype) or is_simple_pointer(ctype):
        return True
    return issubclass(ctype, ctypes._SimpleCData)

def attempt_value_conversion(ctype, value):
    if ctype in (ctypes.c_char, ctypes.c_char_p) or \
        is_simple_char_array(ctype):
        if isinstance(value, bytes):
            return value
        if isinstance(value, list):
            value = "".join([str(v) for v in value])
        if value is None:
            value = ""
        return bytes(value, "ascii")
    if ctype == ctypes.c_bool:
        if isinstance(value, str):
            if value.lower() in ConfigParser.BOOLEAN_STATES:
                return ConfigParser.BOOLEAN_STATES[value.lower()]
            else:
                return value
        return bool(value)
    if ctype in (ctypes.c_float, ctypes.c_double):
        if value is None:
            value = 0.0
        return float(value)
    if value is None:
        value = 0
    return int(value)

def fill_ctypes_struct(instance, data):
    t = type(instance)
    if issubclass(t, ctypes.Structure):
        if not isinstance(data, (dict, Namespace)):
            raise TypeError("'data' should be a dictionary or a Namespace")
        if isinstance(data, Namespace):
            data = vars(data)
        for key, expected_type in t._fields_:
            if is_simple(expected_type):
                try:
                    value = attempt_value_conversion(expected_type, data.get(key, None))
                except TypeError as e:
                    raise TypeError(f"{key}: {str(e)}")
                setattr(instance, key, value)
            else:
                fill_ctypes_struct(getattr(instance, key), data.get(key, None))
    elif issubclass(t, ctypes.Union):
        logging.error("Unions are not supported in object configuration")
    elif issubclass(t, ctypes.Array):
        if not isinstance(data, list) and not isinstance(data, bytes):
            raise TypeError("'data' should be a list")
        for i, val in enumerate(data):
            if is_simple(t._type_):
                try:
                    instance[i] = attempt_value_conversion(t._type_, val)
                except Exception as e:
                    raise TypeError(f"{str(instance)}: {str(e)}")
            else:
                fill_ctypes_struct(instance[i], val)
    elif is_simple_pointer(instance):
        data = [data] if not isinstance(data, list) else data
        arr = (instance._type_ * (len(data) + 1))()
        fill_ctypes_struct(arr, data)
        arr[-1] = None
        instance.contents = arr
    else:
        raise TypeError(f"Unknown ctypes type {t}")

def parse_ctypes_struct(instance):
    data = {}
    t = type(instance)
    if issubclass(t, ctypes.Structure):
        for key, expected_type in t._fields_:
            if is_simple(expected_type):
                if is_simple_char_array(expected_type):
                    data[key] = getattr(instance, key).decode('ascii')
                else:
                    data[key] = getattr(instance, key)
            else:
                data[key] = parse_ctypes_struct(getattr(instance, key))
    elif issubclass(t, ctypes.Array):
        if is_simple_char_array(t):
            return ctypes.string_at(instance).decode('ascii')
        elif issubclass(t._type_, ctypes._SimpleCData):
            return list(instance)
        return [parse_ctypes_struct(x) for x in instance]
    elif is_simple_pointer(instance):
        return instance.contents
    return data


def expand_substruct_config(options, obj_conf):
    def create_namespace_from_conf(conf):
        namespace = Namespace()
        anon = []
        for fname, ftype in conf._fields_:
            if issubclass(ftype, ctypes.Structure):
                anon += [f[0] for f in getattr(ftype, "_anonymous_", [])]
                n, a = create_namespace_from_conf(ftype)
                anon += a
                setattr(namespace, fname, n)
            elif issubclass(ftype, ctypes.Union):
                logging.error("Unions are not supported in object configurations")
            elif issubclass(ftype, ctypes.Array) and \
                issubclass(ftype._type_, (ctypes.Structure, ctypes.Union)):
                l = []
                for _ in range(ftype._length_):
                    n, a = create_namespace_from_conf(ftype._type_)
                    anon += a
                    l.append(n)
                setattr(namespace, fname, l)
            elif issubclass(ftype, ctypes.Array) and \
                ftype._type_ is not ctypes.c_char:
                setattr(namespace, fname, [ftype._type_(0).value] * ftype._length_)
            else:
                if isinstance(ftype, type(_Pointer)):
                    setattr(namespace, fname, None)
                else:
                    setattr(namespace, fname, ftype(0).value)
        return namespace, anon

    def fill_namespace_from_opts(namespace, options, anonymous, prefix=None):
        for name in vars(namespace):
            member = getattr(namespace, name)
            member_prefix = f"{prefix}_{name}" if prefix else name
            if isinstance(member, Namespace):
                if name in anonymous:
                    member_prefix = prefix
                fill_namespace_from_opts(member, options, anonymous, member_prefix)
            elif isinstance(member, list):
                if name in anonymous:
                    member_prefix = prefix
                if isinstance(member[0], Namespace):
                    for idx in range(len(member)):
                        fill_namespace_from_opts(member[idx], options, anonymous,
                                                 f"{member_prefix}_{idx + 1}")
                else:
                    if hasattr(options, member_prefix):
                        setattr(namespace, name, getattr(options, member_prefix))
            else:
                opt_dict = vars(options)
                if member_prefix in opt_dict:
                    setattr(namespace, name, opt_dict[member_prefix])

    opt_space, anonymous = create_namespace_from_conf(obj_conf)
    fill_namespace_from_opts(opt_space, options, anonymous)
    return opt_space

def show_struct(struct, printer, indent=0):
    printer(" " * indent + "%s", struct)
    indent += 2
    for fname, ftype in struct._fields_:
        if issubclass(ftype, ctypes.Structure):
            show_struct(getattr(struct, fname), printer, indent)
        elif issubclass(ftype, ctypes.Array):
            if issubclass(ftype._type_, ctypes.Structure):
                for idx in range(ftype._length_):
                    show_struct(getattr(struct, fname)[idx], printer, indent + 2)
            elif is_simple_char_array(ftype):
                printer(" " * indent + f"{fname}: %s", getattr(struct, fname))
        else:
            printer(" " * indent + f"{fname}: %s", getattr(struct, fname))
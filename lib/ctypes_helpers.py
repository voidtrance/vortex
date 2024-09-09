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
import ctypes
from _ctypes import _Pointer
# This is only to get access to ConfigParser.BOOLEAN_STATES
from configparser import ConfigParser


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
        if value is None:
            value = ""
        return bytes(value, "ascii")
    if ctype == ctypes.c_bool:
        if value.lower() not in ConfigParser.BOOLEAN_STATES:
            return value
        return ConfigParser.BOOLEAN_STATES[value.lower()]
    if ctype in (ctypes.c_float, ctypes.c_double):
        return float(value)
    return int(value)

def fill_ctypes_struct(instance, data):
    t = type(instance)
    if issubclass(t, ctypes.Structure):
        if not isinstance(data, dict):
            raise TypeError("'data' should be a dictionary")
        for key, expected_type in t._fields_:
            if is_simple(expected_type):
                #if is_simple_char_array(expected_type):
                #    setattr(instance, key, bytes(data[key], "ascii"))
                #else:
                value = attempt_value_conversion(expected_type, data.get(key, None))
                setattr(instance, key, value)
            else:
                fill_ctypes_struct(getattr(instance, key), data.get(key, None))
    elif issubclass(t, ctypes.Array):
        if not isinstance(data, list):
            raise TypeError("'data' should be a list")
        for i, val in enumerate(data):
            if is_simple(t._type_):
                #if is_simple_char_array(t):
                #    instance[i] = bytes(data[i], "ascii")
                #else:
                instance[i] = attempt_value_conversion(t, val)
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


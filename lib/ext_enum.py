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
import enum
unique = enum.unique
auto = enum.auto


def getitem_wrap(orig):
    def wrapped(cls, key):
        member = None
        if isinstance(key, int):
            members = [x for x in cls.__members__.values() if x.value == key]
            if members:
                member = members[0]
        elif isinstance(key, str):
            if key in cls._member_map_:
                member = cls._member_map_[key]
            else:
                members = [x for x in cls.__members__.values()
                           if x._str_ == key]
                if members:
                    member = members[0]
        else:
            member = orig(cls, key)
        if not member:
            raise KeyError(f"Enum '{cls.__name__}' does not contain '{key}'")
        return member
    return wrapped


enum.Enum.__class__.__getitem__ = \
    getitem_wrap(enum.Enum.__class__.__getitem__)


class ExtIntEnumMeta(enum.EnumMeta):
    def __contains__(cls, element):
        if isinstance(element, str):
            return element in cls._member_map_
        return super().__contains__(element)


class ExtIntEnum(enum.IntEnum, metaclass=ExtIntEnumMeta):
    def __new__(cls, value, *args):
        if type(value) not in (int, auto):
            raise TypeError("Valid values are integers and 'auto'")
        if type(value) == auto:
            value = len(cls.__members__) + 1
        obj = int.__new__(cls, value)
        obj._value_ = value
        obj._str_ = args[0] if args else None
        return obj

    def __str__(self):
        value = getattr(self, "_str_", None)
        return value if value else self.name

    def __format__(self, spec):
        if spec and not spec.endswith("s"):
            return format(self._value_, spec)
        value = getattr(self, "_str_", None)
        return format(value if value else self.name, spec)

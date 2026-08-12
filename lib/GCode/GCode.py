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
import regex
from typing import *

class GCodeParamParseError(Exception):
    pass

class GCodeParam:
    gcode_param_regexp = regex.compile(r'^(?P<name>[A-Z]+)=?(?P<value>.+)$')
    float_regexp = regex.compile(r'(?P<mantisa>[0-9-]+)(?:\.(?P<exp>[0-9]+))?')

    def __init__(self, param : str) -> None:
        parsed = self.gcode_param_regexp.match(param)
        if not parsed:
            raise GCodeParamParseError

        self.__name = parsed.group("name")
        self.__raw_value = parsed.group("value")
        v_parsed = self.float_regexp.match(self.__raw_value)
        if v_parsed:
            if v_parsed.group("exp"):
                self.__value = (float(self.__raw_value),
                                len(v_parsed.group("exp")))
            elif not v_parsed.group("exp") and self.__raw_value.endswith("."):
                self.__value = (float(self.__raw_value), 0)
            else:
                self.__value = (int(self.__raw_value), 0)
        else:
            self.__value = (self.__raw_value, None)

    @property
    def name(self) -> str:
        return self.__name

    @property
    def value(self) -> str:
        return self.__value[0]

    def __str__(self) -> str:
        if self.__value[1] == None:
            v = self.__value
        elif self.__value[1] != 0:
            v = f"{self.__value[0]:{self.__value[1]}f}"
        else:
            v = f"{self.__value[0]}"
        return f"{self.name}{v}"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.name == other
        elif isinstance(other, GCodeParam):
            return self.name == other.name
        else:
            return False

class GCodeCommandParseError(Exception):
    pass

GCodeCommandClasses = [ "G", "M", "T", "D", "S" ]

class GCodeCommand:
    gcode_regexp = regex.compile(
        r'^(?P<cmd>(?P<prefix>[A-Z])(?P<code>[0-9]+))(?:\ (?P<data>[^;]*))?(?:\ *;\ *(?P<comment>.*))?$')
    macro_r = regex.compile(
        r'^(?P<cmd>[^\ ]+)\ *(?P<data>[^;]*)(?:;\ *(?P<comment>.*))?$')

    def __init__(self, command : str) -> None:
        self.__is_macro = False
        parsed = self.gcode_regexp.match(command)
        if not parsed:
            parsed = self.macro_r.match(command)
            if not parsed:
                raise GCodeCommandParseError
            self.__is_macro = True
        self.__cmd = parsed.group("cmd")
        self.__raw_params = parsed.group("data")
        self.__comment = parsed.group("comment")
        self.__cmd_class = parsed.group("prefix") \
            if not self.__is_macro else None
        if not self.__is_macro and self.__cmd_class not in GCodeCommandClasses:
            raise GCodeCommandParseError("Invalid GCode Command")
        self.__cmd_code = int(parsed.group("code")) \
            if not self.__is_macro else 0
        self.__params = []

        if self.__raw_params:
            for param in self.__raw_params.split():
                self.__params.append(GCodeParam(param))

    @property
    def command(self) -> str:
        return self.__cmd

    @property
    def command_class(self) -> str:
        return self.__cmd_class

    @property
    def command_code(self) -> int:
        return self.__cmd_code

    @property
    def comment(self) -> str:
        return self.__comment

    @property
    def is_macro(self) -> bool:
        return self.__is_macro

    def has_params(self) -> bool:
        return self.__params

    def has_param(self, name : str) -> bool:
        return name in self.__params

    def get_param(self, name : str) -> Union[str, None]:
        for param in self.__params:
            if param == name:
                return param
        return None

    def get_params(self, exclude : Optional[list] = None) -> Generator[str]:
        for param in self.__params:
            if not exclude or param.name not in exclude:
                yield(param)

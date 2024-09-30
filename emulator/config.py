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
import configparser
from argparse import Namespace
import logging
from vortex.controllers.types import ModuleTypes

class Configuration:
    def __init__(self):
        self._parser = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation())

    def _read_file(self, filename):
        content = []
        with open(filename, 'r') as fd:
            for line in fd:
                line = line.rstrip()
                if line.startswith("<include ") and \
                    line[-1] == ">":
                    include_file = line[9:-1]
                    content += self._read_file(include_file)
                    content.append("")
                else:
                    content.append(line)
        return content
    def read(self, filename):
        config_content = self._read_file(filename)
        for line in config_content:
            logging.debug("CONFIG: " + line)
        self._parser.read_string("\n".join(config_content))

    def get(self, type, name, option):
        if not isinstance(type, ModuleTypes):
            raise TypeError("'type' must be a ModuleTypes enumeration value")
        section = f"{str(type)} {name}"
        if self._parser.has_section(section):
            return self._get(self._parser.get(section, option))
        return None

    def get_machine_config(self):
        return self.__parse_section("machine")
    
    def get_section(self, type, name):
        if not isinstance(type, ModuleTypes):
            raise TypeError("'type' must be a ModuleTypes enumeration value")
        section = f"{str(type)} {name}"
        if self._parser.has_section(section):
            return self.__parse_section(section)

    def __iter__(self):
        for section in self._parser.sections():
            if section == "machine":
                continue
            klass, name = section.split(maxsplit=1)
            klass_enum = getattr(ModuleTypes, klass.upper(), None)
            if klass_enum is None:
                logging.error(f"Unknown klass '{klass}'")
                continue
            yield klass_enum, name, self.__parse_section(section)

    def _get(self, value):
        def convert(v, t):
            if t == list:
                if ',' in value:
                    v = [self._get(x.strip()) for x in value.split(',')]
                else:
                    raise ValueError
            elif t == bool:
                v = self._parser._convert_to_boolean(v)
            else:
                v = t(v)
            return v
        for type in (list, int, float, bool, str):
            try:
                value = convert(value, type)
                break
            except ValueError:
                continue
        return value
    
    def __parse_section(self, section):
        section_config = Namespace()
        for option, value in self._parser.items(section):
            value = self._get(value)
            setattr(section_config, option, value)
        return section_config
    
import configparser
from argparse import Namespace
from controllers.types import ModuleTypes

class Configuration:
    def __init__(self):
        self._parser = configparser.ConfigParser()

    def read(self, filename):
        self._parser.read(filename)

    def __iter__(self):
        for section in self._parser.sections():
            klass, name = section.split(maxsplit=1)
            yield ModuleTypes[klass], name, self.__parse_section(section)

    def _get(self, value, conv):
        if conv == list:
            if ',' in value:
                value = [x.strip() for x in value.split(',')]
            else:
                raise ValueError
        elif conv == bool:
            value = self._parser._convert_to_boolean(value)
        else:
            value = conv(value)

        return value
    
    def __parse_section(self, section):
        section_config = Namespace()
        for option, value in self._parser.items(section):
            for type in (list, int, float, bool, str):
                try:
                    value = self._get(value, type)
                except ValueError:
                    continue
                else:
                    setattr(section_config, option, value)
                    break
        return section_config
    
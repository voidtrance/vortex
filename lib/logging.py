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
import logging

class VortexLoggerFilter(logging.Filter):
    def __init__(self, name=""):
        self.exact = True if name[-1] == '.' else False
        if self.exact:
            name = name[:-1]
        super().__init__(name)
    def filter(self, record):
        if "*" in self.name:
            if self.name.endswith(".*"):
                return record.name == self.name[:-2]
            elif self.name.startswith("vortex.*."):
                n_len = len(self.name) - 9
                return record.name[-n_len:] == self.name[9:]
            else:
                filter_sections = self.name.split(".")
                record_sections = record.name.split(".")
                if self.exact and len(filter_sections) != len(record_sections):
                    return False
                if len(filter_sections) > len(record_sections) and \
                    (len(filter_sections) != len(record_sections) + 1 or \
                    filter_sections[-1] != "*"):
                    return False
                n_parts = min(len(filter_sections), len(record_sections))
                for i in range(n_parts):
                    if filter_sections[i] != "*" and filter_sections[i] != record_sections[i]:
                        return False
                return True
        elif self.exact:
            if self.name == record.name:
                return True
            else:
                return False
        return super().filter(record)

class VortexLogger(logging.Logger):
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)
        self._prefix = None
    def add_prefix(self, prefix):
        self._prefix = prefix
    def _log(self, level, msg, args, **kwargs):
        if self._prefix:
            msg = f"{self._prefix}: {msg}"
        super()._log(level, msg, args, **kwargs)
    def verbose(self, message, *args, **kwargs):
        if self.isEnabledFor(VERBOSE):
            self._log(VERBOSE, message, args, **kwargs)
    def filter(self, record):
        results = set()
        for filter in self.filters:
            if hasattr(filter, "filter"):
                result = filter.filter(record)
            else:
                result = filter(record)
            if isinstance(result, logging.LogRecord):
                record = result
                results.add(True)
            else:
                results.add(result)
        return record if True in results else False

def get_logging_levels():
    return logging._nameToLevel

def get_logging_level_names():
    return logging._levelToName

logger = VortexLogger("vortex")
logging.root = logger
logging.Logger = VortexLogger
logging.Logger.root = logger
logging.Logger.manager = logging.Manager(logging.Logger.root)
logging.Logger.manager.setLoggerClass(VortexLogger)

def getLogger(name=None):
    logger = logging.getLogger(name)
    for filter in logging.root.filters:
        logger.addFilter(filter)
    return logger

NOTSET = logging.NOTSET
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
VERBOSE = 15

logging._levelToName[VERBOSE] = 'VERBOSE'
logging._nameToLevel['VERBOSE'] = VERBOSE

debug = logging.debug
info = logging.info
warning = logging.warning
error = logging.error
critical = logging.critical
exception = logging.exception
fatal = logging.fatal
log = logging.log

def verbose(msg, *args, **kwargs):
    logging.root.verbose(msg, *args, **kwargs)

def setup_vortex_logging(level=logging.INFO, logfile=None, extended=False, filters=[]):
    fmt = "%(created)f %(levelname)s"
    if extended:
        fmt += " {%(name)s} [%(pathname)s:%(lineno)d]"
    fmt += ": %(message)s"
    logging.basicConfig(level=level, filename=logfile, format=fmt)
    for filter in filters:
        f = VortexLoggerFilter(f"vortex.{filter}")
        logger.addFilter(f)

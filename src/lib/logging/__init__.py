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
import os
import atexit
import errno
from sys import stderr
from inspect import currentframe
import vortex.core.lib.logging._vortex_logging as core_logging

NOTSET = core_logging.lib.LOG_LEVEL_NOTSET
DEBUG = core_logging.lib.LOG_LEVEL_DEBUG
VERBOSE = core_logging.lib.LOG_LEVEL_VERBOSE
INFO = core_logging.lib.LOG_LEVEL_INFO
WARNING = core_logging.lib.LOG_LEVEL_WARNING
ERROR = core_logging.lib.LOG_LEVEL_ERROR
CRITICAL = core_logging.lib.LOG_LEVEL_CRITICAL

LOG_LEVELS = {
    NOTSET: core_logging.ffi.string(core_logging.lib.log_level_names[NOTSET]).decode(),
    DEBUG: core_logging.ffi.string(core_logging.lib.log_level_names[DEBUG]).decode(),
    VERBOSE: core_logging.ffi.string(core_logging.lib.log_level_names[VERBOSE]).decode(),
    INFO: core_logging.ffi.string(core_logging.lib.log_level_names[INFO]).decode(),
    WARNING: core_logging.ffi.string(core_logging.lib.log_level_names[WARNING]).decode(),
    ERROR: core_logging.ffi.string(core_logging.lib.log_level_names[ERROR]).decode(),
    CRITICAL: core_logging.ffi.string(core_logging.lib.log_level_names[CRITICAL]).decode(),
}

class VortexLogger:
    def __init__(self, name):
        self.name = name
        _logger = core_logging.ffi.new("vortex_logger_t **")
        ret = core_logging.lib.vortex_logger_create(name.encode('ascii'), _logger)
        if ret != 0:
            if ret == errno.EINVAL:
                raise ValueError(f"Invalid logger name: {name}")
            elif ret == errno.ENOMEM:
                raise MemoryError("Failed to allocate memory for logger")
            elif ret == errno.EFAULT:
                raise RuntimeError("Vortex logging not setup yet")
            else:
                raise RuntimeError(f"Unknown error occurred while creating logger: {ret}")
        self._logger = _logger[0]
        if self._logger == core_logging.ffi.NULL:
            raise RuntimeError(f"Failed to create logger with name: {name}")

    def _is_internal(self, frame):
        f_name = os.path.normcase(frame.f_code.co_filename)
        return f_name == __file__ or ("importlib" in f_name and "_bootstrap" in f_name)

    def _get_caller_info(self, n_frames=1):
        frame = currentframe()
        while n_frames:
            frame = frame.f_back
            if not self._is_internal(frame):
                n_frames -= 1
        co = frame.f_code
        return co.co_filename, co.co_name, frame.f_lineno
    
    def add_prefix(self, prefix):
        return core_logging.lib.vortex_logger_set_prefix(self._logger, prefix.encode('ascii'))

    def log(self, level, msg, *args, **kwargs):
        # Variadic arguments are supported with CFFI so we cound have
        # the C function do the formatting. However, in order to use
        # variadic arguments, each one has to be cast to a C type.
        # This means that each argument would have to be checked and
        # converted to something suitable.
        # It's much easier to just format the message in Python.
        msg = msg % args
        filename, func_name, line_no = self._get_caller_info()
        ret = core_logging.lib.vortex_logger_log(self._logger, level,
                                                 filename.encode('ascii'),
                                                 line_no,
                                                 msg.encode('ascii'))
        return ret
    
    def debug(self, msg, *args, **kwargs):
        return self.log(DEBUG, msg, *args, **kwargs)

    def verbose(self, msg, *args, **kwargs):
        return self.log(VERBOSE, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        return self.log(INFO, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        return self.log(WARNING, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        return self.log(ERROR, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        return self.log(CRITICAL, msg, *args, **kwargs)

    def __del__(self):
        if hasattr(self, "_logger"):
            core_logging.lib.vortex_logger_destroy(self._logger)

_baseLogger = None

def _init_base_logger():
    global _baseLogger
    if _baseLogger is None:
        _baseLogger = VortexLogger("vortex")

def init(level, log_file=None, extended_logging=False):
    """
    Initialize the Vortex logging system.

    :param level: The logging level to set. Must be an integer.
    :param log_file: Optional log file path. If None, logging will not be written to a file.
    :param extended_logging: If True, enables extended logging which includes source file and line number.
    :return: 0 on success, or an error code on failure.
    """
    level = get_level_value(level)

    status = core_logging.lib.vortex_logging_init()
    if status != 0:
        return status

    status = core_logging.lib.vortex_logging_add_stream(stderr.fileno(), level)
    if status != 0:
        return status
    
    if log_file:
        log_fd = open(log_file, "a")
        status = core_logging.lib.vortex_logging_add_stream(log_fd.fileno(), level)
        if status != 0:
            return status;

    core_logging.lib.vortex_logging_set_extended(extended_logging)
    _init_base_logger()
    atexit.register(core_logging.lib.vortex_logging_deinit)
    return 0

def add_filter(filter):
    """
    Add a filter to the Vortex logging system.
    
    :param filter: A string representing the filter to be added.
    :return: 0 on success, or an error code on failure.
    """
    if not isinstance(filter, list):
        filter = [filter]

    for f in filter:
        if not isinstance(f, str):
            raise TypeError("Filter must be a string")
        status = core_logging.lib.vortex_logging_add_filter(f.encode("ascii"))
        if status != 0:
            return status
    return 0

def get_level_value(level):
    """
    Convert level into it's numerical value and validate it.
    Raises TypeError if level is not an integer or a valid
    logging level name. Raises ValueError if level is not a
    valid logging level numerical value.

    :param level: The level to check.
    :return: Logging level numerical value
    """
    if isinstance(level, str):
        for key, value in LOG_LEVELS.items():
            if value.lower() == level.lower():
                level = key
                break

    if not isinstance(level, int):
        raise TypeError("Logging level must be an integer or a valid string representation")

    if level <= NOTSET or level > CRITICAL:
        raise ValueError(f"Invalid logging level: {level}")

    return level

def add_output_stream(stream, level):
    """
    Add an additional output stream.

    :param stream: An open file descriptor of the stream.
    :return: 0 on success, or an error code of failure.
    """
    level = get_level_value(level)

    if not isinstance(stream, int):
        return errno.EINVAL

    return core_logging.lib.vortex_logging_add_stream(stream, level)

def remove_output_stream(stream):
    if not isinstance(stream, int):
        return errno.EINVAL

    return core_logging.lib.vortex_logging_remove_stream(stream)

def get_level():
    """
    Get the current logging level of the Vortex logging system.

    :return: The current logging level as an integer.
    """
    return core_logging.lib.vortex_logging_get_level()

def getLogger(name):
    """
    Get a Vortex logger instance with the specified name.

    :param name: The name of the logger.
    :return: A VortexLogger instance.
    """
    _init_base_logger()
    if not isinstance(name, str):
        raise TypeError("Logger name must be a string")
    return VortexLogger(name)

def debug(msg, *args, **kwargs):
    """
    Log a debug message.

    :param msg: The message to log.
    :param args: Additional arguments for formatting the message.
    :param kwargs: Additional keyword arguments for formatting the message.
    """
    _init_base_logger()
    return _baseLogger.log(DEBUG, msg, *args, **kwargs)

def verbose(msg, *args, **kwargs):
    """
    Log a verbose message.

    :param msg: The message to log.
    :param args: Additional arguments for formatting the message.
    :param kwargs: Additional keyword arguments for formatting the message.
    """
    _init_base_logger()
    return _baseLogger.log(VERBOSE, msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    """
    Log an error message.

    :param msg: The message to log.
    :param args: Additional arguments for formatting the message.
    :param kwargs: Additional keyword arguments for formatting the message.
    """
    _init_base_logger()
    return _baseLogger.log(ERROR, msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    """
    Log a warning message.

    :param msg: The message to log.
    :param args: Additional arguments for formatting the message.
    :param kwargs: Additional keyword arguments for formatting the message.
    """
    _init_base_logger()
    return _baseLogger.log(WARNING, msg, *args, **kwargs)

def critical(msg, *args, **kwargs):
    """
    Log a critical message.

    :param msg: The message to log.
    :param args: Additional arguments for formatting the message.
    :param kwargs: Additional keyword arguments for formatting the message.
    """
    _init_base_logger()
    return _baseLogger.log(CRITICAL, msg, *args, **kwargs)
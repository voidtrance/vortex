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
import argparse
import logging
import errno
import traceback
import vortex.emulator
import vortex.emulator.config
import vortex.core.lib.logging as logging

def create_arg_parser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    frontend = parser.add_argument_group("Frontend Options")
    frontend.add_argument("-f", "--frontend", default="direct",
                        help="""The frontend that will be started for
                        the emulation.""")
    frontend.add_argument("-s", action="store_true", dest="sequential",
                          help="""Enable sequential mode. In this
                          mode, the frontent will execute one command
                          at a time rather than submit commands to the
                          command queue as they are received.""")

    controller = parser.add_argument_group("Controller Options")
    controller.add_argument("-c", "--controller", default=None,
                            help="""The HW controller to be used for the
                            emulation. This argument is required.""")
    controller.add_argument("-F", "--frequency", default="1MHz",
                            help="""Frequency of control loop. This
                            control loop is the main emulator control loop. It's
                            the one that updates controller clock and emulation
                            runtime. Higher values provide more precise
                            emulation, at the cost of CPU load.""")
    controller.add_argument("-T", "--process-frequency", default="100KHz",
                            help="""This is the frequency with which the
                            core's event processing threads updates will run.
                            The event processing thread are responsible for
                            processing command submission and completion,
                            event processing, etc.""")
    controller.add_argument("-P", "--set-priority", action="store_true",
                            help="""Set the priority of the emulator to
                            real-time. This will make the emulator run
                            with higher priority than other processes
                            on the system. This is useful for more
                            precise emulation but may affect system
                            performance as the emulator will take up more
                            CPU cycles.""")
    debug = parser.add_argument_group("Debug Options")
    debug_levels = sorted(logging.LOG_LEVELS.values())
    debug.add_argument("-d", "--debug", choices=debug_levels, metavar="LEVEL",
                        default="INFO",
                        help="""Set logging level. Higher logging levels will
                        provide more information but will also affect
                        conroller timing more.""")
    debug.add_argument("--filter", type=str, action="append", default=[],
                       help="""Filter log messages by the specified
                       module/object. Filter format is a dot-separated
                       hierarchy of modules/objects. For example, the filter
                       'vortex.core.stepper.X' will only show log messages from
                       the core HW stepper object with name 'X'. '*' can
                       be used to match all modules/objects at the particular
                       level. This option can be used multiple times to
                       filter multiple modules. The filter is applied to
                       the module name and not the logger name.""")
    debug.add_argument("-l", "--logfile", type=str, default=None,
                       help="""Log messages are sent to the file specified
                       by this option.""")
    debug.add_argument("--extended-logging", action="store_true",
                       help="""Enable extended debugging. When enabled, log
                       messages will also contain the source of the message
                       (filename and line number). """)
    debug.add_argument("-R", "--remote", action="store_true",
                       help="""Start remote API server thread. This thread
                       processes requests from the monitoring application.""")
    debug.add_argument("--enable-profiling", action="store_true")

    parser.add_argument("-C", "--config", required=True,
                        help="""HW object configuration file. This argument
                        is required.""")
    return parser

def main():
    parser = create_arg_parser()
    opts = parser.parse_args()

    logging.init(opts.logfile, opts.extended_logging)
    logging.set_level(opts.debug)
    logging.add_filter(opts.filter)

    config = vortex.emulator.config.Configuration()
    try:
        config.read(opts.config)
    except Exception as e:
        logging.error(e)
        return errno.EINVAL

    if opts.controller:
        config.override_controller(opts.controller)

    try:
        emulation = vortex.emulator.Emulator(config, opts.frontend, opts.sequential)
    except vortex.emulator.EmulatorError as err:
        print(err)
        return errno.ENOENT
    
    if opts.enable_profiling:
        emulation.enable_profiler()

    emulation.set_frequency(opts.frequency, opts.process_frequency)
    emulation.set_thread_priority_change(opts.set_priority)
    if opts.remote:
        emulation.start_remote_server()

    try:
        emulation.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if opts.debug.lower() == "debug":
            traceback.print_exc(e)
        print(f"Emulator exception: {e}")
    finally:
        emulation.stop()

    return 0

sys.exit(main())
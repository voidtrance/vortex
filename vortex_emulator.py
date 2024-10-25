#!/usr/bin/env python3
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
import sys
import argparse
import logging
import errno
import vortex.emulator
import vortex.emulator.config
import vortex.frontends

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
    controller.add_argument("-F", "--frequency", default="200Hz",
                            help="""This is the frequency with which the
                            object update loop will run. Controllers still
                            clock ticks are still updated based on their
                            defined frequency.""")
    debug = parser.add_argument_group("Debug Options")
    debug.add_argument("-d", "--debug", choices=logging._nameToLevel.keys(),
                        default="INFO",
                        help="""Set logging level. Higher logging levels will
                        provide more information but will also affect
                        conroller timing more.""")
    debug.add_argument("-l", "--logfile", type=str, default=None,
                       help="""Log messages are sent to the file specified
                       by this option.""")
    debug.add_argument("-M", "--monitor", action="store_true",
                       help="""Start monitoring server thread. This thread
                       processes requests from the monitoring application.""")

    parser.add_argument("-C", "--config", required=True,
                        help="""HW object configuration file. This argument
                        is required.""")
    return parser

def main():
    parser = create_arg_parser()
    opts = parser.parse_args()

    logging.basicConfig(filename=opts.logfile, level=opts.debug,
                        format="%(created)f %(levelname)s: %(message)s")

    config = vortex.emulator.config.Configuration()
    config.read(opts.config)

    if opts.controller:
        config.override_controller(opts.controller)

    frontend = vortex.frontends.create_frontend(opts.frontend)
    if frontend is None:
        logging.error(f"Did not find fronted '{opts.frontend}'")
        return errno.ENOENT

    frontend.set_sequential_mode(opts.sequential)

    try:
        emulation = vortex.emulator.Emulator(frontend, config)
    except vortex.emulator.EmulatorError as err:
        print(err)
        return errno.ENOENT
    
    emulation.set_frequency(opts.frequency)
    if opts.monitor:
        emulation.start_monitor()

    try:
        emulation.run()
    except KeyboardInterrupt:
        emulation.stop()

    return 0

sys.exit(main())
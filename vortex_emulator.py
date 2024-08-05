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
import importlib
import logging
import vortex.emulator
import vortex.emulator.config
import vortex.frontends

def create_arg_parser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    frontend = parser.add_argument_group("Frontend Options")
    frontend.add_argument("-f", "--frontend", default="direct",
                        help="""Select frontend.""")
    frontend.add_argument("-s", action="store_true", dest="sequential",
                          help="""Enable sequential mode. In this
                          mode, the frontent will execute one command
                          at a time rather than submit commands to the
                          command queue as they are received.""")

    controller = parser.add_argument_group("Controller Options")
    controller.add_argument("-c", "--controller", required=True)
    controller.add_argument("-F", "--frequency", default=0)

    debug = parser.add_argument_group("Debug Options")
    debug.add_argument("-d", "--debug", choices=logging._nameToLevel.keys(),
                        default="INFO",
                        help="""Set logging level. Higher logging levels will
                        provide more information but will also affect
                        conroller timing more.""")
    debug.add_argument("-l", "--logfile", type=str, default=None)

    parser.add_argument("-C", "--config", required=True)
    return parser

def load_mcu(name, config):
    try:
        module = importlib.import_module(f"vortex.controllers.{name}")
    except ImportError as e:
        logging.error(f"Failed to create {name} controller: {str(e)}")
        logging.error(sys.path)
        return None
    module_object = getattr(module, "__controller__", None)
    if module_object:
        return module_object(config)
    return None

def main():
    parser = create_arg_parser()
    opts = parser.parse_args()

    logging.basicConfig(filename=opts.logfile, level=opts.debug)

    config = vortex.emulator.config.Configuration()
    config.read(opts.config)

    frontend = vortex.frontends.create_frontend(opts.frontend)
    if frontend is None:
        return 1

    frontend.set_sequential_mode(opts.sequential)

    controller = load_mcu(opts.controller, config)
    if controller is None:
        logging.error(f"Did not find controller '{opts.controller}'")
        return 1
    
    emulation = vortex.emulator.Emulator(controller, frontend)
    emulation.set_frequency(opts.frequency)

    try:
        emulation.run()
    except KeyboardInterrupt:
        emulation.stop()

    return 0

sys.exit(main())
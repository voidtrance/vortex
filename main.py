#!/usr/bin/env python3
import sys
import emulator
import emulator.config
import frontends
import argparse
import os
import importlib
import logging

def create_arg_parser():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-f", "--frontend", default="direct")
    parser.add_argument("-C", "--config", required=True)
    parser.add_argument("-c", "--controller", required=True)
    parser.add_argument("-F", "--frequency", default=0)
    parser.add_argument("-d", "--debug", choices=logging._nameToLevel.keys(),
                        default="INFO")
    parser.add_argument("-l", "--logfile", type=str, default=None)
    return parser


#    def load_modules(self):
#        for filename in os.listdir("./modules"):
#            if os.path.isfile(f"./modules/{filename}") and \
#                filename.endswith(".py"):
#                module = importlib.import_module(f"modules.{filename[:-3]}")
#                module_objects = getattr(module, "__module_objects__", None)
#                if module_objects:
#                    self._module_lib.update(module_objects)
#
#    def initialize_module(self, klass, name, config):
#        module = None
#        if klass in self._module_lib:
#            mod_conf = ModuleConfig(name, self, config)
#            self._modules.append(self._module_lib[klass](name, mod_conf))
#            module = self._modules[-1]
#        return module
#    
#    def lookup_object(self, object_class, object_name):
#        for module in self._modules:
#            if module._class == object_class:
#                if module.config.name == object_name:
#                    return module
#        return None
#
#    def queue_event(self, event, *args):
#        assert isinstance(event, events.Event)
#        self.event_queue.queue_event(event)

def load_mcu(name, config):
    if os.path.isfile(f"./controllers/{name}.py"):
        module = importlib.import_module(f"controllers.{name}")
        module_object = getattr(module, "__controller__", None)
        if module_object:
            return module_object(config)
    return None

def main():
    parser = create_arg_parser()
    opts = parser.parse_args()

    logging.basicConfig(filename=opts.logfile, level=opts.debug)

    config = emulator.config.Configuration()
    config.read(opts.config)

    frontend = frontends.create_frontend(opts.frontend)
    if frontend is None:
        return 1

    controller = load_mcu(opts.controller, config)
    if controller is None:
        print(f"Did not fine controller '{opts.controller}'", file=sys.stderr)
        return 1
    
    emulation = emulator.Emulator(controller, frontend)
    emulation.set_frequency(opts.frequency)

    try:
        emulation.run()
    except KeyboardInterrupt:
        emulation.stop()

    return 0

sys.exit(main())
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
import argparse
import configparser
from typing import Type
from vortex.controllers.types import ModuleTypes
from vortex.emulator.kinematics import AxisType

def parse_pin(pin_name : str):
    if ":" in pin_name:
        return pin_name.split(':')[1]
    if pin_name.startswith(('^', '~')):
        pin_name = pin_name[1:]
    if pin_name.startswith('!'):
        pin_name = pin_name[1:]
    return pin_name

def generate_stepper_config(section : str, name: str,
                            kconfig : Type[configparser.ConfigParser],
                            econfig : Type[configparser.ConfigParser]) -> None:
    s = f"stepper stepper{name.upper()}"
    econfig.add_section(s)
    for pname in ("enable_pin", "dir_pin", "step_pin"):
        pin = parse_pin(kconfig.get(section, pname))
        econfig.set(s, pname, pin)
    econfig.set(s, "microsteps", kconfig.get(section, "microsteps"))
    spr = kconfig.getint(section, "full_steps_per_rotation")
    econfig.set(s, "steps_per_rotation", str(spr))
    rd = kconfig.getfloat(section, "rotation_distance")
    gr = kconfig.get(section, "gear_ratio", fallback="1:1")
    i, o = [int(x) for x in gr.split(':')]
    spm = (spr * (i / o)) / rd
    econfig.set(s, "steps_per_mm", str(int(spm)))
    econfig.set(s, "start_speed", "30")

def generate_axis_config(section : str, kconfig : Type[configparser.ConfigParser],
                         econfig : Type[configparser.ConfigParser]) -> None:
    klass, _, name = section.partition("_")
    print(f"Generating config for section '{section}'...")
    if name[0] == "z":
        axis = AxisType.Z
    else:
        axis = AxisType[name.upper()]
    generate_stepper_config(section, name, kconfig, econfig)
    if axis == AxisType.Z and name != "z":
        steppers = econfig.get("axis axisZ", "stepper")
        steppers = ",".join([steppers, f"stepper{name.upper()}"])
        econfig.set("axis axisZ", "stepper", steppers)
        return

    s = f"endstop endstop{name.upper()}"
    econfig.add_section(s)
    pe = kconfig.getfloat(section, "position_endstop")
    minp = kconfig.getfloat(section, "position_min")
    maxp = kconfig.getfloat(section, "position_max")
    if abs(minp - pe) < abs(maxp - pe):
        econfig.set(s, "type", "min")
    else:
        econfig.set(s, "type", "max")
    econfig.set(s, "axis", str(axis).lower())
    pin = parse_pin(kconfig.get(section, "endstop_pin"))
    econfig.set(s, "pin", pin)

    s = f"axis axis{str(axis).upper()}"
    econfig.add_section(s)
    econfig.set(s, "type", str(axis).lower())
    econfig.set(s, "length", kconfig.get(section, "position_max"))
    econfig.set(s, "stepper", f"stepper{name.upper()}")
    econfig.set(s, "endstop", f"endstop{name.upper()}")

def generate_thermistor(section : str, name : str,
                        kconfig : Type[configparser.ConfigParser],
                        econfig : Type[configparser.ConfigParser]) -> None:
    t_type = kconfig.get(section, "sensor_type")
    if t_type.lower() not in ("pt1000", "pt100", "generic 3950"):
        print("Unsupported thermistor type")
        return
    s = f"thermistor sensor{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "heater", f"heater{name.upper()}")
    econfig.set(s, "pin", kconfig.get(section, "sensor_pin"))
    econfig.set(s, "resistor", kconfig.get(section, "pullup_resistor", fallback="4700"))
    if t_type.lower() == "generic 3950":
        econfig.set(s, "sensor_type", "beta3950")
        econfig.set(s, "beta", "3950")
    else:
        econfig.set(s, "sensor_type", t_type.lower())

    return

def generate_heater_config(section : str, kconfig : Type[configparser.ConfigParser],
                           econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    if name == "extruder":
        generate_stepper_config(section, name, kconfig, econfig)
    s = f"heater heater{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "pin", kconfig.get(section, "heater_pin"))
    econfig.set(s, "max_temp", kconfig.get(section, "max_temp"))
    # Klipper config does not have a setting for the wattage of the heaters.
    # Make one up.
    econfig.set(s, "power", "60")
    generate_thermistor(section, name, kconfig, econfig)
    return

def generate_dpin_config(section : str, kconfig : Type[configparser.ConfigParser],
                         econfig : Type[configparser.ConfigParser]) -> None:
    return

def generate_probe_config(section : str, kconfig : Type[configparser.ConfigParser],
                          econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    if not econfig.has_section("toolhead"):
        s = "toolhead toolheadA"
        econfig.add_section(s)
        toolhead_axis = []
        for es in econfig.sections():
            e_klass, _, e_name = es.partition(" ")
            if e_klass == "axis":
                axis_type = econfig.get(es, "type")
                if axis_type != "e":
                    toolhead_axis.append(axis_type)
        econfig.set(s, "axes", ",".join(toolhead_axis))
    s = f"probe probe{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "toolhead", "toolheadA")
    offsets = [kconfig.get(section, "x_offset"), kconfig.get(section, "y_offset"),
               kconfig.get(section, "z_offset")]
    econfig.set(s, "offsets", ",".join(offsets))
    econfig.set(s, "pin", kconfig.get(section, "pin"))
    econfig.set(s, "range", "0.005")
    return

def generate_thermistor_config(section : str, kconfig : Type[configparser.ConfigParser],
                               econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    generate_thermistor(section, name, kconfig, econfig)    
    return

KLIPPER_SECTION_HANDLERS = {
    "stepper" : generate_axis_config,
    "extruder": generate_heater_config,
    "heater": generate_heater_config,
    "fan": generate_dpin_config,
    "probe": generate_probe_config,
    "temperature_sensor": generate_thermistor_config,
}

parser = argparse.ArgumentParser()
parser.add_argument("klipper_config", help="Klipper configuration file")
parser.add_argument("emulator_config", help="Pin map file")

opts = parser.parse_args()
klipper_config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
klipper_config.read(opts.klipper_config)

emulator_config = configparser.ConfigParser()
emulator_config.add_section("machine")
emulator_config.set("machine", "kinematics",
                    klipper_config.get("printer", "kinematics"))
emulator_config.set("machine", "controller", "stm32f4")

for section in klipper_config.sections():
    for key, handler in KLIPPER_SECTION_HANDLERS.items():
        if key in section:
            handler(section, klipper_config, emulator_config)

with open(opts.emulator_config, 'w') as fd:
    emulator_config.write(fd)

print("Emulator configuration file generated.")
print("Please, check the config file to make sure")
print("all necessary sections and settings are present.")
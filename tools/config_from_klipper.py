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
import argparse
import configparser
from sys import exit
from typing import Type
from time import strftime
from vortex.core.kinematics import AxisType

def parse_pin(pin_name : str):
    if ":" in pin_name:
        return pin_name.split(':')[1]
    if pin_name.startswith(('^', '~')):
        pin_name = pin_name[1:]
    if pin_name.startswith('!'):
        pin_name = pin_name[1:]
    return pin_name

def generate_stepper_config(section : str,
                            kconfig : Type[configparser.ConfigParser],
                            econfig : Type[configparser.ConfigParser]) -> bool:
    if section == "extruder":
        name = "e"
    else:
        klass, _, name = section.partition("_")
        if not name:
            name = klass
    print(f"Generating stepper config for section '{section}'...")
    s = f"stepper stepper{name.upper()}"
    econfig.add_section(s)
    for pname in ("enable_pin", "dir_pin", "step_pin"):
        pin = parse_pin(kconfig.get(section, pname))
        econfig.set(s, pname, pin)
    ms = kconfig.getint(section, "microsteps")
    econfig.set(s, "microsteps", str(ms))
    spr = kconfig.getint(section, "full_steps_per_rotation")
    econfig.set(s, "steps_per_rotation", str(spr))
    rd = kconfig.getfloat(section, "rotation_distance")
    gr = kconfig.get(section, "gear_ratio", fallback="1:1")
    i, o = [int(x) for x in gr.split(':')]
    spm = (spr * ms * (i / o)) / rd
    econfig.set(s, "steps_per_mm", str(int(spm)))
    econfig.set(s, "start_speed", "30")
    return True

def generate_axis_config(section : str, kconfig : Type[configparser.ConfigParser],
                         econfig : Type[configparser.ConfigParser]) -> bool:
    klass, _, name = section.partition("_")
    if not name and section.startswith("extruder"):
        name = "e"

    if name[0] == "z":
        axis = AxisType.Z
    else:
        axis = AxisType[name.upper()]

    print(f"Generating axis config for axis '{axis}'...")

    kin = econfig.get("kinematics", "type")

    if axis != AxisType.E:
        if kin == "delta":
            s = f"endstop endstop{name.upper()}"
            econfig.add_section(s)
            econfig.set(s, "type", "max")
            pin = parse_pin(kconfig.get(section, "endstop_pin"))
            econfig.set(s, "pin", pin)
            econfig.set(s, "axis", str(axis).lower())
        else:
            if axis != AxisType.Z or name == "z":
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
    if not econfig.has_section(s):
        econfig.add_section(s)
        econfig.set(s, "type", str(axis).lower())
        if axis != AxisType.E:
            econfig.set(s, "endstop", f"endstop{name.upper()}")
        econfig.set(s, "stepper", f"stepper{name.upper()}")

    # Handle various kinematics types
    if kin == "corexy" and axis in (AxisType.X, AxisType.Y):
        if econfig.has_option(s, f"stepper"):
            steppers = econfig.get(s, "stepper")
            if "stepperX" in steppers:
                stepper = "stepperY"
            else:
                stepper = "stepperX"
            steppers = steppers.split(',') + [stepper]
            steppers = ",".join(sorted(steppers))
            econfig.set(s, "stepper", steppers)
    elif kin == "corexz" and axis in (AxisType.X, AxisType.Z):
        if econfig.has_option(s, f"stepper"):
            steppers = econfig.get(s, "stepper")
            if "stepperX" in steppers:
                stepper = "stepperZ"
            else:
                stepper = "stepperX"
            steppers = steppers.split(',') + [stepper]
            steppers = ",".join(sorted(steppers))
            econfig.set(s, "stepper", steppers)
    elif axis == AxisType.Z and name != "z":
        steppers = econfig.get("axis axisZ", "stepper")
        steppers = ",".join([steppers, f"stepper{name.upper()}"])
        econfig.set("axis axisZ", "stepper", steppers)
    return True

def generate_pwm(section : str, kconfig : Type[configparser.ConfigParser],
                 econfig : Type[configparser.ConfigParser]) -> None:
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    if kconfig.get(section, "hardware_pwm", fallback=False):
        s = f"pwm {name.upper()}"
        econfig.add_section(s)
        econfig.set(s, "pin", parse_pin(kconfig.get(section, "pin")))

def generate_thermistor(section : str, name : str,
                        kconfig : Type[configparser.ConfigParser],
                        econfig : Type[configparser.ConfigParser]) -> bool:
    t_type = kconfig.get(section, "sensor_type")
    if t_type.lower() not in ("pt1000", "pt100", "generic 3950"):
        print("Unsupported thermistor type")
        return False
    s = f"thermistor sensor{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "heater", f"heater{name.upper()}")
    econfig.set(s, "pin", kconfig.get(section, "sensor_pin"))
    econfig.set(s, "config_type", "2")
    econfig.set(s, "config_resistor", kconfig.get(section, "pullup_resistor", fallback="4700"))
    if t_type.lower() == "generic 3950":
        econfig.set(s, "sensor_type", "beta3950")
        # Set resistance/temp values for coefficient calculation
        econfig.set(s, "config_coeff_1_temp", "25.0")
        econfig.set(s, "config_coeff_1_resistance", "100000")
        econfig.set(s, "config_coeff_2_temp", "150")
        econfig.set(s, "config_coeff_2_resistance", "1770")
        econfig.set(s, "config_coeff_3_temp", "250")
        econfig.set(s, "config_coeff_3_resistance", "230")
    else:
        econfig.set(s, "sensor_type", t_type.lower())

    return True

def generate_extruder_layers(section : str, esection : str,
                             name : str,
                             kconfig : Type[configparser.ConfigParser],
                             econfig : Type[configparser.ConfigParser]) -> None:
    # Klipper config does not have a setting for the wattage of the heaters.
    # Make one up.
    econfig.set(esection, "power", "60")
    for name in ("kp", "ki", "kd"):
        econfig.set(esection, name, kconfig.get(section, f"pid_{name}"))
    # Generate extruder thermal layers
    econfig.set(esection, "layers_1_type", "1")
    econfig.set(esection, "layers_1_density", "1100000")
    econfig.set(esection, "layers_1_capacity", "0.9")
    econfig.set(esection, "layers_1_conductivity", "0.3")
    econfig.set(esection, "layers_1_emissivity", "0.9")
    econfig.set(esection, "layers_1_convection", "0,0")
    econfig.set(esection, "layers_1_size", "10,10,2")
    econfig.set(esection, "layers_2_type", "2")
    econfig.set(esection, "layers_2_density", "2650000")
    econfig.set(esection, "layers_2_capacity", "0.9")
    econfig.set(esection, "layers_2_conductivity", "120")
    econfig.set(esection, "layers_2_emissivity", "0.2")
    econfig.set(esection, "layers_2_convection", "8,4")
    econfig.set(esection, "layers_2_size", "20.0,20.0,10.0")

def generate_bed_layers(section : str, esection : str, name : str,
                        kconfig : Type[configparser.ConfigParser],
                        econfig : Type[configparser.ConfigParser]) -> None:
    # Klipper config does not have a setting for the wattage of the heaters.
    # Make one up.
    econfig.set(esection, "power", "400")
    for name in ("kp", "ki", "kd"):
        econfig.set(esection, name, kconfig.get(section, f"pid_{name}"))
    # Get axis sizes so we can infer bed size
    bed_size = dict.fromkeys(["x", "y", "z"], 0.)
    kin_type = econfig.get("kinematics", "type")
    if kin_type in ("cartesian", "corexy", "corexz"):
        axis_sizes = econfig.get("kinematics", "axis_length").split(",")
        bed_size["x"], bed_size["y"] = map(float, axis_sizes[:2])
    elif kin_type == "delta":
        bed_size["x"], bed_size["y"] = [econfig.getfloat("kinematics", "radius")] * 2

    # Generate bed thermal layers
    econfig.set(esection, "layers_1_type", "1")
    econfig.set(esection, "layers_1_density", "1100000")
    econfig.set(esection, "layers_1_capacity", "0.9")
    econfig.set(esection, "layers_1_conductivity", "0.3")
    econfig.set(esection, "layers_1_emissivity", "0.9")
    econfig.set(esection, "layers_1_convection", "0,0")
    layer_size = ",".join([str(bed_size["x"] - 50),
                           str(bed_size["y"] - 50), "1.5"])
    econfig.set(esection, "layers_1_size", layer_size)
    econfig.set(esection, "layers_2_type", "2")
    econfig.set(esection, "layers_2_density", "2650000")
    econfig.set(esection, "layers_2_capacity", "0.9")
    econfig.set(esection, "layers_2_conductivity", "120")
    econfig.set(esection, "layers_2_emissivity", "0.2")
    econfig.set(esection, "layers_2_convection", "8,4")
    layer_size = ",".join([str(bed_size["x"]), str(bed_size["y"]), "8"])
    econfig.set(esection, "layers_2_size", layer_size)
    econfig.set(esection, "layers_3_type", "3")
    econfig.set(esection, "layers_3_density", "3700000")
    econfig.set(esection, "layers_3_capacity", "0.9")
    econfig.set(esection, "layers_3_conductivity", "0.25")
    econfig.set(esection, "layers_3_emissivity", "0.9")
    econfig.set(esection, "layers_3_convection", "0,0")
    layer_size = ",".join([str(bed_size["x"]), str(bed_size["y"]), "1.2"])
    econfig.set(esection, "layers_3_size", layer_size)
    econfig.set(esection, "layers_4_type", "3")
    econfig.set(esection, "layers_4_density", "5500000")
    econfig.set(esection, "layers_4_capacity", "0.6")
    econfig.set(esection, "layers_4_conductivity", "0.6")
    econfig.set(esection, "layers_4_emissivity", "0.9")
    econfig.set(esection, "layers_4_convection", "0,0")
    layer_size = ",".join([str(bed_size["x"]), str(bed_size["y"]), "0.75"])
    econfig.set(esection, "layers_4_size", layer_size)

def generate_heater_config(section : str, kconfig : Type[configparser.ConfigParser],
                           econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    if name == "extruder":
        generate_stepper_config(section, kconfig, econfig)
    s = f"heater heater{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "pin", kconfig.get(section, "heater_pin"))
    econfig.set(s, "max_temp", kconfig.get(section, "max_temp"))
    # Add thermal layers to the config. This assumes a certain
    # configuration of layers
    if name == "extruder":
        generate_extruder_layers(section, s, name, kconfig, econfig)
    elif name == "heater_bed":
        generate_bed_layers(section, s, name, kconfig, econfig)
    generate_thermistor(section, name, kconfig, econfig)
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
        econfig.set(s, "attachment", ",".join(toolhead_axis))
        econfig.set(s, "axes", "x,y,z")
    s = f"probe probe{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "toolhead", "toolheadA")
    offsets = [kconfig.get(section, "x_offset"), kconfig.get(section, "y_offset"),
               kconfig.get(section, "z_offset")]
    econfig.set(s, "offsets", ",".join(offsets))
    econfig.set(s, "pin", kconfig.get(section, "pin"))
    econfig.set(s, "range", "0.01")
    # Klipper probes are only relative to the Z axis
    econfig.set(s, "axes", "z")
    return

def generate_thermistor_config(section : str, kconfig : Type[configparser.ConfigParser],
                               econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    generate_thermistor(section, name, kconfig, econfig)    
    return

def generate_digital_pin(section : str,
                    name : str,
                    pin : str,
                    kconfig : Type[configparser.ConfigParser],
                    econfig : Type[configparser.ConfigParser]) -> None:
    s = f"digital_pin dpin{name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "pin", parse_pin(pin))
    return

def generate_digital_pin_config(section : str, kconfig : Type[configparser.ConfigParser],
                                econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating digital pin config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    generate_digital_pin(section, name, kconfig.get(section, "pin"), kconfig, econfig)
    return

def generate_encoder_config(section : str, pins : list[str],
                            econfig : Type[configparser.ConfigParser]) -> bool:
    if len(pins) != 2:
        print("Pin list has to have only two pins in it.")
        return False
    print(f"Generating ecoder config for section '{section}...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    s = f"encoder {name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "pin_a", pins[0])
    econfig.set(s, "pin_b", pins[1])
    return True

def generate_display_config(section : str, kconfig : Type[configparser.ConfigParser],
                            econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating display config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    s = f"display {name.upper()}"
    econfig.add_section(s)
    econfig.set(s, "type", kconfig.get(section, "lcd_type"))
    econfig.set(s, "cs_pin", parse_pin(kconfig.get(section, "cs_pin")))
    econfig.set(s, "reset_pin", parse_pin(kconfig.get(section, "rst_pin")))
    econfig.set(s, "data_pin", parse_pin(kconfig.get(section, "a0_pin")))
    econfig.set(s, "spi_miso_pin",
                parse_pin(kconfig.get(section, "spi_software_miso_pin")))
    econfig.set(s, "spi_mosi_pin",
                parse_pin(kconfig.get(section, "spi_software_mosi_pin")))
    econfig.set(s, "spi_sclk_pin",
                parse_pin(kconfig.get(section, "spi_software_sclk_pin")))
    if kconfig.has_option(section, "encoder_pins"):
        pins = [x.strip() for x in kconfig.get(section, "encoder_pins").split(",")]
        generate_encoder_config(section, pins, econfig)
    if kconfig.has_option(section, "click_pin"):
        generate_digital_pin(section, "DISPLAY_CLICK", kconfig.get(section, "click_pin"),
                        kconfig, econfig)
    return

def generate_fan_config(section : str, kconfig : Type[configparser.ConfigParser],
                        econfig : Type[configparser.ConfigParser]) -> None:
    print(f"Generating fan config for section '{section}'...")
    klass, _, name = section.partition(" ")
    if not name:
        name = klass
    generate_digital_pin(section, name, kconfig.get(section, "pin"), kconfig, econfig)
    generate_pwm(section, kconfig, econfig)

def generate_kinematics_config(kconfig : Type[configparser.ConfigParser],
                               econfig : Type[configparser.ConfigParser]) -> bool:
    econfig.add_section("kinematics")
    kin_type = kconfig.get("printer", "kinematics")
    econfig.set("kinematics", "type", kin_type)

    if kin_type in ("cartesian", "corexy", "corexz"):
        axis_lengths = []
        for axis_type in ("x", "y", "z"):
            ksection = f"stepper_{axis_type}"
            if not kconfig.has_section(ksection):
                print(f"ERROR: Klipper config missing section '{ksection}")
                return False
            axis_lengths.append(kconfig.get(ksection, "position_max"))
        econfig.set("kinematics", "axis_length", ",".join(axis_lengths))
    elif kin_type == "delta":
        econfig.set("kinematics", "tower_radius", kconfig.get("printer", "delta_radius"))
        if kconfig.has_option("printer", "print_radius"):
            radius = kconfig.get("printer", "print_radius")
        else:
            radius = kconfig.get("printer", "delta_radius")
        econfig.set("kinematics", "radius", radius)
        arm_length = 0.
        tower_angles = []
        endstop = 0.0
        default_angles = ["210", "330", "90"]
        for i, axis_type in enumerate(("a", "b", "c")):
            ksection = f"stepper_{axis_type}"
            if kconfig.has_option(ksection, "arm_length") and not arm_length:
                arm_length = kconfig.get(ksection, "arm_length")
            if kconfig.has_option(ksection, "position_endstop") and not endstop:
                endstop = kconfig.get(ksection, "position_endstop")
            angle = kconfig.get(ksection, "angle", fallback=default_angles[i])
            tower_angles.append(angle)
        econfig.set("kinematics", "arm_length", arm_length)
        econfig.set("kinematics", "z_length", endstop)
        econfig.set("kinematics", "tower_angle", ",".join(tower_angles))
    return True

def generate_neopixel_config(section : str, kconfig : Type[configparser.ConfigParser],
                             econfig : Type[configparser.ConfigParser]) -> bool:
    print(f"Generating neopixel config for section '{section}...")
    econfig.add_section(section)
    econfig.set(section, "pin", kconfig.get(section, "pin"))
    econfig.set(section, "count", kconfig.get(section, "chain_count"))
    econfig.set(section, "type", kconfig.get(section, "color_order"))
    return True

KLIPPER_SECTION_HANDLERS = {
    "stepper" : generate_stepper_config,
    "extruder": generate_heater_config,
    "heater": generate_heater_config,
    "fan": generate_fan_config,
    "temperature_sensor": generate_thermistor_config,
    "button": generate_digital_pin_config,
    "display": generate_display_config,
    "neopixel": generate_neopixel_config,
}

parser = argparse.ArgumentParser()
parser.add_argument("klipper_config", help="Klipper configuration file")
parser.add_argument("emulator_config", help="Emulator configuration filename")

opts = parser.parse_args()
klipper_config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
klipper_config.read(opts.klipper_config)

emulator_config = configparser.ConfigParser()
emulator_config.add_section("machine")
emulator_config.set("machine", "controller", "stm32f4")

if not generate_kinematics_config(klipper_config, emulator_config):
    exit(1)

for section in klipper_config.sections():
    for key, handler in KLIPPER_SECTION_HANDLERS.items():
        if key in section:
            ret = handler(section, klipper_config, emulator_config)
            if ret is False:
                print(f"ERROR: Failed to generate configiration")
                exit(1)

# Generate axis configuration.
# Axes are done separately to ensure that all steppers have
# already been configured. This is required in order to be
# able to generate configuration for different kinematics types.
for section in klipper_config.sections():
    if section.startswith("stepper") or section.startswith("extruder"):
        ret = generate_axis_config(section, klipper_config, emulator_config)
        if ret is False:
            print(f"ERROR: Failed to generate axis configuration")
            exit(1)

# Once we have all the axes configured, we can generate the
# toolhead/probe configuration.
if klipper_config.has_section("probe"):
    generate_probe_config("probe", klipper_config, emulator_config)

with open(opts.emulator_config, 'w') as fd:
    fd.write("### Auto-generated Vortex configuration\n")
    fd.write(f"### Generated from {opts.klipper_config}\n")
    fd.write(f"### on {strftime('%m-%d-%Y %H:%M:%S')}\n")
    emulator_config.write(fd)

print("Emulator configuration file generated.")
print("Please, check the config file to make sure")
print("all necessary sections and settings are present.")
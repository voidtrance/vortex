# Vortex Configuratoin Guide
The configuration guide describe configuration options for
each individual HW object.

## Configuration File Format
The Vortex configuration file use the following format:

```
[<object type> <object name>]
<object setting>: <setting value>
...

```
Please note that each object configuration section ends
with a blank line. Skipping this line will cause parsing
errors.

## Machine Configuration
The configuration file requires a `machine` configuration.

```ini
[machine]
kinematics:
controller:
```

| Setting | Type | Description |
| :- | :-: | :- |
| kinematics | string | The machine kinematics. Some values are `cartesian`, `delta`, `corexy`, `corexz`. |
| controller | string | This setting specifies the controller type to be used. |

## Object Configuration Guide
Vortex provides the following emulated HW objects:
* Motors/Steppers
* Axes
* Endstops
* Probes
* Heaters
* Thermistors
* Toolheads

In addition, the following virtual objects are also
provided:
* Digital Pin
* Fan

### Motors/Stepper
Motor/Stepper configuration user the following format:

```ini
[stepper stepper1]
steps_per_rotation:
steps_per_mm:
microsteps:
start_speed:
driver:
enable_pin:
dir_pin:
step_pin:
```

| Setting | Type | Description |
| :--- | :---: | :--- |
| steps_per_rotation | integer | The number of steps a stepper motor has to make for a full revolution. This numb comes from the motor specification. |
| steps_per_mm | float | The number of steps required to move the axis 1mm |
| microsteps | integer | The number of microsteps that this stepper motor should be configured for. |
| start_speed | float | The initial motor speed. |
| driver | string | The motor driver chip to emulate. |
| enable_pin | string | The name of the motor's enable pin |
| dir_pin | string | The name of the motor's direction pin (if the motor is a stepper) |
| step_pin | string | The name of the motor's direction pin (if the motor is a stepper) |

### Axis
```ini
[axis x]
length:
type:
stepper:
endstop:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| length | float | The length of the axis in millimeters. |
| type | char | They axis type. One of `x`, `y`, `z`, `a`, `b`, `c`, or `e` |
| stepper | list[string] | A comma-separated list of all motors assigned to the axis. |
| endstop | string | The name of the endstop object asigned to the axis. |

### Endstop
```ini
[endstop x_endstop]
type:
axis:
pin:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| type | string | Either 'min' or 'max'. 'min' type endstops trigger when the axis is at is minimum travel position (0.0). 'max' type endstop trigger when the axis is at its maximum position ('length'). |
| axis | string | The axis this endstop is assigned to. |
| pin | string | The endstop's pin name |

### Thermistor
```ini
[thermistor temp_sensor1]
sensor_type:
heater:
pin:
config_type:
config_resistor:
config_coeff_<n>_temp:
config_coeff_<n>_resistance:
config_beta_beta:
```
Thermistor objects represent resistive temperature sensors.

| Setting | Type | Description |
| :- | :-: | :- |
| sensor_type | string | Type of sensors. The supported types are `beta3590`, `pt100`, and `pt1000` |
| heater | string | The heater object this thermistor is associated with |
| pin | string | The pin name used to read the thermistor's resistance |
| config_type | [1, 2] | The type of sensor configuration: `1` - "beta", `2` - "coefficient". Depending on the type, either the `config_coeff_*` or `config_beta_*` settings are required. |
| config_coeff_\<n>_temp | uint16 | "Coefficient" configuration type requires three known resistance values for specific temperature in order to compute the thermistor's coefficients. `config_coeff_<n>_temp` specified the temperature in a pair of values (`n` is between `1` and `3`) |
| config_coeff_\<n>_resistance | uint32 | The resistance of the thermistor at temperature `config_coeff_\<n>_temp` |

### Heater
```ini
[heater heater1]
power:
max_temp:
pin:
layers_<n>_type:
layers_<n>_density:
layers_<n>_capacity:
layers_<n>_conductivity:
layers_<n>_emissivity:
layers_<n>_convection:
layers_<n>_size:
```

Heater objects emulate a heating element that is attached to a heated body. They use an
algorithm that approximates the heat transfer rates from the heating element to the the
heated body and from the heated body to the surrounding atmosphere.

The algorithm that was used is from the 3D printer bed simulator developed by Paniel
Detersson (https://github.com/monkeypangit/thermalemulator).

Heater elements are define in "layers". Each layer represents the next object in the
emulated heater. For example, a 3D printer bed can be emulated by definning a heating
element layer (the heater mat), an aluminum heated bed, a magnetic sticker sheet, and
a steel build plate. Each layer needs its thermal properties defined in the heater
configuration section.

| Setting | Type | Description |
| :--- | :---: | :--- |
| power | integer | The wattage of the heating element. This setting is used to compute how fast the element will heat up during the emulation. The calculation does not take into account any thermal mass of anything attached to the heating element. However, this setting can be used to emulate that. |
| max_temp | integer | The maximum temperature that the heater can reach. |
| pin | string | The heater's control pin name |
| layer_\<n>_type | integer | Type of the layer: 1 - heating element, 2 - heated body, 3 - other |
| layer_\<n>_density | float | Material density in g/m^3 |
| layer_\<n>_capacity | float | Thermal capacity constant for the material (in J/gK) |
| layer_\<n>_conductivity | float | Material thermal conductivity rate (in W/mK) |
| layer_\<n>_emissivity | float | |
| layer_\<n>_convection | list[float] | Two, comma-separated values for the heat convection rate (in W/m^2K) |
| layer_\<n>_size | list[float] | A comma-separated list of the layer's dimensions (in mm) |

### Probe
```ini
[probe surface_probe]
toolhead:
offsets:
range:
pin:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| z_offset | float | The distance that the probe is offted from the tip of the tool/toolhead. |
| range | float | The probe object attempts to provide a more realistic emulation of a real-world probe by randomizing when it triggers. This setting specifies a maximum distance (in mm) from the axis 0 position for the randomization range. The probe will trigger at a random distance between 0 and 'range'. |
| toolhead | string | The toolhead to which the probe is attached. |
| pin | string | The probe's output pin name |

### Fan
```ini
[fan cooling]
pin:
```
Fan objects do not have any configuration settings.

### Toolhead
```ini
[toolhead tool1]
axes:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| axes | list[char] | A comma-separated list of all the axes types the toolhead is attached to. See `type` setting of the [Axis object](#Axis). |

### Digital Pin
```ini
[digital_pin pin1]
pin:
```
Digital pin objects do not have any settings.
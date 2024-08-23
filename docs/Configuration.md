# Vortex Configuratoin Guide
The configuration guide describe configuration options for
each individual HW object.

## Available HW Objects
Vortex provides the following emulated HW objects:
* Motors/Steppers
* Axes
* Endstops
* Probes
* Heaters
* Thermistors

In addition, the following virtual objects are also
provided:
* Digital Pin
* Fan
* Toolhead

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

## Object Configuration Guide
### Motors/Stepper
Motor/Stepper configuration user the following format:

```
[stepper stepper1]
steps_per_rotation:
microsteps:
start_speed:
driver:
```

| Setting | Type | Description |
| :--- | :---: | :--- |
| steps_per_rotation | integer | The number of steps a stepper motor has to make for a full revolution. This numb comes from the motor specification. |
| microsteps | integer | The number of microsteps that this stepper motor should be configured for. |
| start_speed | float | The initial motor speed. |
| driver | string | The motor driver chip to emulate. |

### Axis
```
[axis x]
length:
travel_per_step:
stepper:
endstop:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| length | float | The length of the axis in millimeters. |
| travel_per_step | float | The distance the axis position changes for each step of the axis motor. |
| stepper | list | A comma-separated list of all motors assigned to the axis. |
| endstop | string | The name of the endstop object asigned to the axis. |

### Endstop
```
[endstop x_endstop]
type:
axis:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| type | string | Either 'min' or 'max'. 'min' type endstops trigger when the axis is at is minimum travel position (0.0). 'max' type endstop trigger when the axis is at its maximum position ('length'). |
| axis | string | The axis this endstop is assigned to. |

### Thermistor
```
[thermistor temp_sensor1]
sensor_type:
beta:
heater:
```

### Heater
```
[heater heater1]
power:
max_temp:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| power | integer | The wattage of the heating element. This setting is used to compute how fast the element will heat up during the emulation. The calculation does not take into account any thermal mass of anything attached to the heating element. However, this setting can be used to emulate that. |
| max_temp | integer | The maximum temperature that the heater can reach. |

### Probe
```
[probe surface_probe]
z_offset:
range:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| z_offset | float | The distance that the probe is offted from the tip of the tool/toolhead. |
| range | float | The probe object attempts to provide a more realistic emulation of a real-world probe by randomizing when it triggers. This setting specifies a maximum distance (in mm) from the axis 0 position for the randomization range. The probe will trigger at a random distance between 0 and 'range'. |

### Fan
```
[fan cooling]
```
Fan objects do not have any configuration settings.
### Toolhead
```
[toolhead tool1]
axes:
```
| Setting | Type | Description |
| :--- | :---: | :--- |
| axes | list | A comma-separated list of all the axes the toolhead is attached to. |

### Digital Pin
```
[digital_pin pin1]
```
Digital pin objects do not have any settings.
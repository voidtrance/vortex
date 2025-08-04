<style type="text/css" rel="stylesheet">
table > thead:has(> tr > th:empty):not(:has(> tr > th:not(:empty))) { display: none; }
tr { vertical-align: top}
td { text-align: left; }
</style>

# Vortex Object Reference

This reference describes all Vortex objects with their supported commands and events.

## HW Objects

### Stepper

Stepper objects emulate stepper motors by keeping track of individual step counts. Step counts
can then be used by other objects to track other emulation properties, like axis position, etc.

#### Available Commands

<table>
  <thead><tr><th colspan=3>enable enable=0|1</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Enables/disables a stepper motor.</td></tr>
  <tr><td>Arguments</td><td>enable=0|1</td><td>`0` to disable the motor, `1` to enable it</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>set_speed steps_per_second=&lt;double&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set the speed of the stepper motor. This command will set
  the number of steps by which the internal step counter will be incremented each second.</td></tr>
  <tr><td>Arguments</td><td>stepr_per_second</td><td>A floating point number for the number of steps
  to be taken per second.</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>set_accel accel=&lt;int&gt; decel=&lt;int&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set stepper motor acceleration and deceleration rate.
  Internally, the object will compute the rate by which to increase the steps per second until
  the set motor speed is reached. On deceleration, the motor step rate will be decreased according
  to this rate until the movement stops.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>accel</td><td></td></tr>
  <tr><td>decel</td><td></td></tr>
</table>

<table>
  <thead><tr><th colspan=3>move direction=1|2; steps=&lt;int&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Move the stepper motor by "steps" steps in "direction" direction.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>direction</td><td>The direction in which to move the stepper motor. `1` for forward, `2` for backward.</td></tr>
  <tr><td>steps</td><td>The number of steps by which to move the motor.</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>use_pins enable=0|1</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Enable the control of the stepper by using a pin word. This
  will allocated a 32 bits, where different bits of the word control different virtual pins (enable,
  step, direction).</td></tr>
  <tr><td rowspan=2>Arguments</td><td>enable</td><td>`0` for disable, `1` for enable.</td></tr>
</table>

#### Available Events

| Event | Data | Description |
| :- | :- | :- |
| STEPPER_MOVE_COMPLETE | step | Triggered when the stepper move is complete. `steps` indicates the current step count. This event does not trigger if the stepper is using a pin word for control. |

#### Status

| Field | Description |
| :- | :- |
| enabled | Is the motor enabled? |
| use_pins | Is the pin control enabled? |
| steps | The current step count. |
| spr | Steps per rotation. |
| microsteps | The number of microsteps the stepper is emulating. |
| speed | The current stepper speed. This value is only valid when pin control is not used. |
| accel | The current stepper acceleration rate. This value is only valid when pin control is not used. |
| decel | The current stepper deceleration rate. This value is only valid when pin control is not used. |
| steps_per_mm | Steps per millimeter that the motor take. This value is calculated based on the `spr` and `microsteps` values. |
| enable_pin | The name of the motor's enable pin. |
| dir_pin | The name of the motor's direction pin. |
| step_pin | The name of the motor's step pin. |
| pin_addr | The address of the pin control word. This value is set to `0` if `use_pins` is False. |

### Thermistor

Thermistor objects emulate resistive thermistors like PT100, PT1000, etc.

#### Available Commands

The object does not support any commands.

#### Events

The object does not have any events.

#### Status

| Field | Description |
| :- | :- |
| resistance | The resistance value of the thermistor. This value is computed based on the temperature of the heater to which the thermistor is attached. |
| adc | The thermistor's maximum ADC conversion value. |
| pin | The name of the thermistor's pin. |

### Heater

Heater objects emulate a heating element. They use a Euler approximation in order to simulate
real-world behavior based on the power of the heater and the thermal properties of what the heater
is attached.

#### Available Commands

<table>
  <thead><tr><th colspan=3>set_temperature temperature=&lt;float&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set the temperature that the heater has to reach.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>temperature</td><td>Temperature in C</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>use_pins enable=0|1</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Enable pin control. Setting the control pin to `1` will turn
  the heater on at full power. Setting it to `0` will turn the heater power off.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>enable</td><td>`0` to disable, `1` to enable.</td></tr>
</table>

#### Events
| Event | Data | Description |
| :- | :- | :- |
| HEATER_TEMP_REACHED | temperature | Triggered when the heater reaches the set temperature. `temperature` is the reached temperature. This event does not trigger if the stepper is using a pin word for control. |

#### Status
| Field | Description |
| :- | :- |
| temperature | The heater's current temperature value. |
| max_temp | The heater's maximum temperature. |
| pin | The name of the heater's control pin. |
| pin_addr | The address of the pin control word. This is set to `0` if pin control is not enabled. |

### Endstop
#### Available Commands

The endstop object does not support any commands.

#### Events

| Event | Data | Description |
| :- | :- | :- |
| ENDSTOP_TRIGGERED | triggered | Event is triggered when the enstop triggers. `triggered` will be `True` if the endstop is triggered. Since the event is triggered only when the enstop triggers, `triggered` will always be True.|

#### Status

| Field | Description |
| :- | :- |
| triggered | If the endstop is currently triggered |
| type | The time of the endstop. `min` indicates that the endstop is located at the origin of the axis. `max` indicates that the endstop is located at the end of the axis. |
| axis | The axis to which the endstop is attached. |
| pin | The name of the endstop pin. |
| pin_addr | The address of the pin status word. Unlike pin control words, the pin status word reports the endstop status through this memory location. This can make reading the endstop status much faster. |

### Axis

The axis object emulates a machine axis. The axis keeps the linear posistion of the toolhead along its
travel distance. This is calculated based on the position of the motor(s) attached to the axis and the
emulation's kinematics model.

#### Available Commands

The axis object does not support any commands.

#### Events

| Event | Data | Description |
| :- | :- | :- |
| AXIS_HOMED | axis | Triggered when the axis is at the homed position. For axis with a `min` endstop, this will be when the toolhead position is at the axis origin. For axis with a `max` endstop, this will be the when the toolhead is at the maximum position. `axis` is the axis type that triggered the event. |

#### Status

| Field | Description |
| :- | :- |
| homed | Is the axis at the home position? |
| min | The axis origin position. Normally, this will be `0`. However, in the case of Delta kinematics, this will be the height (in mm) when the arm actuators will be located when the end effector is at Z0.0. |
| max | The maximum absolute value (in mm) that the axis can reach. This is `min` + `length`, where `length` comes from the `[kinematics]` configuration. |
| type | The axis type. One of `AXIS_TYPE_X`, `AXIS_TYPE_Y`, `AXIS_TYPE_Z`, `AXIS_TYPE_E`, `AXIS_TYPE_A`, `AXIS_TYPE_B`, or `AXIS_TYPE_C`. |
| position | The current position along the axis. For kinematics other than Delta, this is the same as the toolhead's position along the axis. For Delta, this is the position along the tower travel and not the toolhead's position. |
| motors | The names of the motor objects attached to the axis. |
| endstop | The name of the endstop object attached to the axis. |

### Probe

The probe object emulates a surface probe. The probe is attached to a set of axis with configurable
offset from the position of the toolhead.

#### Available Commands

The probe object does not support any commands.

#### Events

| Event | Data | Description |
| :- | :- | :- |
| PROBE_TRIGGERED | position | Event is triggered when the probe triggers. `position` is the position the probe's axes when it triggered. |

#### Status

| Field | Description |
| :- | :- |
| triggered | Is the probe triggered? |
| offsets | The offsets of the probe from each of the axis. This is a list with 7 elements, one for each axis type. Offsets in the list are only valid for axis to which the probe is attached. |
| position | The probes current position. |
| pin | The name of the probe pin. |
| pin_addr | The address of the pin status word. |

### Toolhead

The toolhead object tracks the position of the machine's toolhead in 3 dimentional space. The position
is determined based on the current axis position and kinematics model being used.

#### Available Commands

The toolhead object does not support any commands.

#### Events

| Event | Data | Description |
| :- | :- | :- |
| TOOLHEAD_ORIGIN | position | Triggered when the toolhead reaches the "origin" (X=0, Y=0, Z=0). `position` will be the position of the toolhead along each of the 7 axes. |

#### Status

| Field | Description |
| :- | :- |
| axes | A list of the axis to which the toolhead is attached. The list has 7 elements, one for each axis type. Valid entries will have one of the axis types above. Invalid entries will have the value of `AXIS_TYPE_MAX` (`7`). |
| position | The toolhead's position along each of the 7 axis. |

### PWM

PWM objects emulates HW PWM controllers. It is configured with a frequency defined by the HW controller
being used. The frequency, in combination with a configured duty cycle, define the PWM cycle.

#### Available Commands

<table>
  <thead><tr><th colspan=3>set_params prescaler=&lt;int&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set PWM parameters.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>prescaler</td><td>This prescaler is used to define the controller clock ticks and increment the PWM's internal counters.</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>set_object klass=&lt;int&gt; name=&lt;string&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set the object controller by the PWM object.</td></tr>
  <tr><td rowspan=3>Arguments</td><td>klass</td><td>The klass of the object. This should be a
  digital pin object klass.</td></tr>
  <tr><td>name</td><td>The name of the object.</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>set_duty_cycle duty_cycle=&lt;int&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set PWM's duty cycle. The duty cycle is the number of counts
  of the internal PWM counter for which the controlled pin will be set to ON.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>duty_cycle</td><td>The duty cycle value.</td></tr>
</table>

#### Events

The PWM object does not support any events.

#### Status

| Field | Description |
| :- | :- |
| counter | The maximum value that the internal counter can reach before resetting to 0. |
| duty_cycle | The current duty_cycle of the PWM control. |
| on | Is the controller pin current ON. |
| pin | The name of the pin being controlled by the PWM object. |

## Virtual Objects

### Display

The display virtual object emulates an LCD display screen connected to the machine through an SPI
interface.

#### Available Commands

<table>
  <thead><tr><th colspan=3>read len=&lt;int&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Read data from display device.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>len</td><td>Number of bytes to read.</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>write is_data=0|1 data=&lt;bytes&gt;</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Write to display device. This command is used to writ both
  commands and data, depending on the value of `is_data`.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>is_data</td><td>`0` if writing commands, `1` otherwise.</td></tr>
  <tr><td>data</td><td>The data to be written to the device.</td></tr>
</table>

<table>
  <thead><tr><th colspan=3>reset</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Reset the display. when this command is received, the display
  device should reset all internal state to it's default values.</td></tr>
  <tr><td rowspan=2>Arguments</td><td></td><td></td></tr>
</table>

#### Events

The display object does not support any events.

#### Status

| Field | Description |
| :- | :- |
| type | The type of the display device. |
| cs_pin | The name of the chip select pin. |
| reset_pin | The name of the reset pin. |
| data_pin | The name of the data pin. This is the pin that controls if the written bytes are commands or data. |
| spi_miso_pin | The name of the SPI MISO pin. |
| spi_mosi_pin | The name of the SPI MOSI pin. |
| spi_sclk_pin | The name of the SPI SCLK pin. |
| width | The width (in pixels) of the display. |
| height | The height (in pixels) of the display. |
| data | The content of the display's memory. |

### Digital Pin

The digital pin object emulates a digital HW pin. It stores the value of that pin as eighter `True` (for
HIGH) or `False` (for LOW).

#### Available Commands

<table>
  <thead><tr><th colspan=3>set state=True|False</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set the state of the digital pin.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>state</td><td>`True` for HIGH, `False` for LOW.</td></tr>
</table>

#### Events

The digital pin object does not support any events.

#### Status

| Field | Description |
| :- | :- |
| state | The current state of the emulated pin. |
| pin | The name of the emulated pin. |

### Encoder

Encoder objects emulate rotary encoders. They emulate the two pins that rotary encoders would use
to signal movement and its direction. When the object is sent a `pulses` command, it toggles both
pins in an alternating fashion. Which pin is toggle first depends on the direction of the encoder's
movement.

#### Available Commands

<table>
  <thead><tr><th colspan=3>pulses count=&lt;int&gt; direction=0|1</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Generate `count` movement pulses in the direction specified
  by `direction`.</td></tr>
  <tr><td rowspan=2>Arguments</td><td>count</td><td>The number of pulses to generate. This will cause
  the encoder object to toggle each pin this many times.</td></tr>
  <tr><td>direction</td><td>The direction of the movement. `0` for clockwise, `1` for counter-clockwise.
  </td></tr>
</table>

#### Events

The encoder object does not support any events.

#### Status

| Field | Description |
| :- | :- |
| pin_a | The name of the first control pin. |
| pin_b | The name of the second control pin. |
| state | A dictionary containing the current state of both pins. |

### Neopixel

The Neopixel object is a simple object that emulates multi-color, individually-addressable LEDs.
The object can emulate various color orders/types (RGB, GRB, RGBW, etc.).

A single neopixel object can support up to 1024 LEDs.

#### Available Commands

<table>
  <thead><tr><th colspan=3>set index=&lt;int&gt; color=[r,g,b,w]</th></tr></thead>
  <tr><td>Description</td><td colspan=2>Set the color of one of the LEDs in the set/chain</td></tr>
  <tr><td rowspan=2>Arguments</td><td>index</td><td>The position of the LED.</td></tr>
  <tr><td>color</td><td>The color for the LED. This is a list of 4 values in the range 0-255
  representing the four color channels Red, Green, Blue, and White. For LEDs that do not have
  white diode, the White value can </td></tr>
</table>

#### Events

The neopixel object does not support any events.

#### Status

| Field | Description |
| :- | :- |
| count | The number of LEDs in the set/chain. |
| type | The type of the LEDs (RGB, GRB, RGBW, etc.) |
| colors | A list of collor sets for each of the LEDs in the chain. |
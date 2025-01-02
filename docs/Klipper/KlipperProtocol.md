# Klipper MCU Protocol

The Klipper firmware is broken up into two parts - the host controller and MCU
firmware. The host controller does the heavy lifting by processing commands,
computing and scheduling moves, which the MCU firmware just executes the commands
send to it by the host controller.

There isn't much information about the Klipper MCU protocol besides a description
of the protocol frame format and some of the used commands. Of course, the
interesting part about the protocol are the meaning and purpose of the commands
along with the required responses.

## Klipper Protocol Frame

The frame format that Klipper uses to send commands to the MCU firmware is
described in the Klipper documentation (). What is not described is how frames
are processed on the MCU side.

A single frame can contain multiple commands. There is no delimiter between the
individual commands. Instead, the command's ID is used to determine how much of
the frame's data is to be parsed for the current command.

The frame processing flow is described below:
* Each frame has it's own sequence number. The sequence numbering starts with
sequency number 1. The MCU firware verifies that the sequence number of the frame
that it has received matches the expected serial number.
  * If the sequence number matches, the frame's data is processed and and ACK is
    sent **after** the commands within the frame data have been processed. The
    purpose of the ACK is to tell the host that all commands sent upto and including
    the current frame have been executed.
  * If the sequence number does not match or there was an issue processing one or
  more of the sent commands, the MCU sends back a NACK message with the sequence
  number of the last successfully processed frame.

## Description of the Klipper protocol

The frame data encoding requires that commands are encoded with unique IDs. In
order for the host and MCU to communicate successfully, they both have to agree
on the IDs for each of the supported commands. This is done during that
"identification" phase of the MCU initialization process.

As part of the MCU firmware build, all supported commands are assigned a
unique ID. This ID can be any positive integer. Two IDs are reserved for the
*identify* command and the *identify_response* response. This is needed in
order to succesfully transfer the rest of the command IDs. The *identify_response*
response uses the ID `0` and the *identify* command uses the ID `1`.

### MCU Identification

The host/MCU communication begins with the host "identifying" the MCU. During
this process the *identify* command is sent by the host and the MCU responds with
the *identify_response*. Refer to the 
[Command Reference](/docs/Klipper/CommandReference.md) for a description of the
commands.

The exchange of the identification data allows the Klipper host to identify and
use the correct command and response IDs, as well as, format the messages
correctly.

After identification information has been exchanged Klipper host finalizes the
configuration and sets a configuration CRC, which the controller will return
when queried for its configuration state. During the configuration finalization,
the controller is supposed to allocate its "move" queue. This is the queue on
which commands will be queued. The controller will indicate the size of the queue
when the host queries the controller's configuration state. The host uses this
size to ensure that the commands the host sends do not overflow the queue.

Once the configuration has been finalized, the host requests the controller's
uptime and then starts to periodically query for the controller's clock value.
This is used to synchronize the host and controller time scales, which is needed
for the host to correctly setup and track timing.

### Controller configuration

The next phase is to configure the controller.

First, Klipper sends a command to tell the controller to allocate a certain number
of OIDs. OIDs are unique IDs for each object (pin, syncronization tracker, etc.)
that will configured on the controller. Klipper communicates using these OIDs so
the correct object can be identified by both the host and the controller.

Once the OIDs have been allocated, Klipper host sends a series of configuration
commands that associate controller pins as defined in the Klipper configuration file
and sets initial object settings if applicable.

### Object Protocol

Depending on the defined objects, Klipper uses different command/response exchanges
to control and query the objects, as well as perform actions are requested by the
GCode.

#### Analog Input Pins

Analog input pins are used to read analog state from the controller. The most common
example of this is temperature sensor readings. The controller uses an ADC to convert
analog sample values to digital values, which are sent back to the host.

To get analog input updates, Klipper sets up a cycle that reads the pin's
ADC-converted value several times before sending the data back to the Klipper host.
The cycle is setup as such:

* The firmware reads the value every N controller ticks.
* The firmware reads X number of values before sending the response back to the host.
* After X samples have been take, the firmware wait for M controller ticks before
restarting the sampling.
* All X sample values are added up and the response contains the sum value.

#### Digital Pin

Digital pins can be both input and output pins. For example, an endstop's digital pin
is an input pin and Klipper checks the pin state, while a fan digital pin is an
output pin which Klipper controls.

Input digital pins are used for endstops and buttons, while output digital pins are
used for fans, heaters, etc.

An output digital pin can be updated (immediatesly sets the value of the pin) or
scheduled for update at some later time. Klipper can also setup a software PWM cycle,
which toggles the pin at a specified interval.

#### Endstops

Endstops are input digital pins that are used to interrupt motor movements when the
pin is "triggered" (flips its value).

Endstops are used in combination with stepper and TRsync commands during axis homing.
More on them later.

#### Steppers

Klipper host controls the machine's stepper motors directly. This means that Klipper
host computes the number of steps required for a particular movement. It also computes
the interval between steps in order to achive the desired acceleration, speed, and
deceleration of the motor.

To do this, Klipper hosts sends commands that tell the firmware to perform a certain
amount of steps at the specified time interval. It can also specify a constans number
of ticks which are added to the interval. This results in a change of speed of the
motor as the interval between stpes either shricks or becomes larger.

#### TRSync

The TRSync object is an object that the Klipper firmware uses to synchronize other
firmware objects with each other. It is mainly used in the homing of axis where the
axis motor(s) have to keep moving until and endstop is triggered.

TRSync objects are setup to state at a specific interval and to expire at a specific
time. The exparation is provided so the process has a finate time that Klipper host
can control.

The TRsync object is used to periodically reports state to the Klipper host and call
object (usually stepper(s)) callbacks when the endstop is triggered.

The state reported to the klipper host is the reason for the trigger or that the
exparation time has been reached without a trigger.

## Axis Homing

Axis homing is described here seperately because it is one of the more complex operations
that Klipper performs. It requires the interfaction between three different parts of the
Klipper firmware - steppers, endstops, and trsync synchronizers.

The first step in homing an axis is to setup the TRSync synchronizer. Klipper host sets
it up with the report interval and the expartion reason (used if the synchronizer expires).

Next, the stepper(s) is configured to use the TRSync object that was setup for the homing.
At this point, the stepper configures the synchronizer to call a stepper callback that
would halt the stepper movement.

The next step is to set the exparation time of the synchronizer so the stepper movements
don't continue indefinitely if the endstop does not trigger for some reason.

The last step before starting to move the stepper(s) is to tell the endstop to start the
homing process. This starts another perioding cycle that keeps checking the state of the
endstop. When the endstop triggers, it signals the synchronizer which, in turn, calls
the stepper callback to halt the stepper movements.

Lastly, Klipper host starts sending stepper move commands. These commands keep being sent
until the host receive a message from the synchronizer that the trigger has happened.
While the steppers are moving, the host also keeps extending the TRSync exparation timeout
based on the state reported to the host by the TRSync.

### Axis Homing Command Sequence

Below is an example of the axis homing process. In this case, Klipper has
already created the following objects:

| Object Type | OID |
| - | - |
| Stepper | 2 |
| Endstop | 3 |
| TRsync | 4 |
| Digital Pin | 14 |

In the sequence below `request` refers to a command sent by Klipper host to the
controller, while `response` is the response sent by the controller to Klipper host.
For the meaning of each of the command/response parameters, refer to the 
[Klipper Command Reference](/docs/Klipper/CommandReference.md).

```
request: trsync_start {'oid': 4, 'report_clock': 342803047, 'report_ticks': 900000 'expire_reason': 4}
request: stepper_stop_on_trigger {'oid': 2, 'trsync_oid': 4}
request: trsync_set_timeout {'oid': 4, 'clock': 345803047}
request: endstop_home {'oid': 3, 'clock': 342803047, 'sample_ticks': 180, 'sample_count': 4, 'rest_ticks': 15000, 'pin_value': 1, 'trsync_oid': 4, 'trigger_reason': 1}
request: queue_digital_out {'oid': 14, 'clock': 342830075, 'on_ticks': 1}
request: set_next_step_dir {'oid': 2, 'dir': 0}
response: trsync_state oid=4 can_trigger=1 trigger_reason=0 clock=342803392
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
response: trsync_state oid=4 can_trigger=1 trigger_reason=0 clock=343703520
request: trsync_set_timeout {'oid': 4, 'clock': 346703520}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
response: trsync_state oid=4 can_trigger=1 trigger_reason=0 clock=344603520
request: trsync_set_timeout {'oid': 4, 'clock': 347603520}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
response: trsync_state oid=4 can_trigger=1 trigger_reason=0 clock=345503616
request: trsync_set_timeout {'oid': 4, 'clock': 348503616}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
response: trsync_state oid=4 can_trigger=1 trigger_reason=0 clock=346403616
request: trsync_set_timeout {'oid': 4, 'clock': 349403616}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}

...

request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
request: trsync_set_timeout {'oid': 4, 'clock': 1394572608}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
response: trsync_state oid=4 can_trigger=1 trigger_reason=0 clock=1392472704
request: trsync_set_timeout {'oid': 4, 'clock': 1395472704}
request: queue_step {'oid': 2, 'interval': 15000, 'count': 40, 'add': 0}
response: trsync_state oid=4 can_trigger=0 trigger_reason=1 clock=1392880512
request: trsync_trigger {'oid': 4, 'reason': 2}
response: trsync_state oid=4 can_trigger=0 trigger_reason=1 clock=0
request: endstop_home {'oid': 3, 'clock': 0, 'sample_ticks': 0, 'sample_count': 0, 'rest_ticks': 0, 'pin_value': 0, 'trsync_oid': 0, 'trigger_reason': 0}
request: trsync_trigger {'oid': 4, 'reason': 2}
response: trsync_state oid=4 can_trigger=0 trigger_reason=1 clock=0
request: stepper_get_position {'oid': 2}
response: stepper_position oid=2 pos=-38330
request: endstop_query_state {'oid': 3}
response: endstop_state oid=3 homing=False next_clock=1392893208 pin_value=1
request: reset_step_clock {'oid': 2, 'clock': 0}
```
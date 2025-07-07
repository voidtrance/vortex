# Vortex Emulator User Guide
## How To Use The Emulator
The first thing that is required in order to use the emulator is a configuration
file listing all of the objects that the emulator is to create. For further
information about creating configuration files and object configuration, see the
[configuration guide](/docs/Configuration.md).

Once the configuration file has been created, the emulator can be started using
the desired HW controller and frontend.

When it starts, the frontend will create a serial interface at `/tmp/vortex`.
Please note that frontend are free to change the path to the serial interface in
order to provide a path that the emulator client can interface with.

This serial interface can be used to send command data to the frontend. Depending
of the frontend used, the command data can be simple GCode commands, direct HW
object commands, or any data that the instantiated frontend can process.

For detailed information on the emulator's operation, see the 
[architecture description](/docs/Architecture.md) document.

## Emulator Logging
The emulator includes a logging facility, which can be used to display log messages
from various parts of the emulator.

The available logging levels are:
  * `ERROR` - Error message. These usually indicate fatal conditions or errors, which will
  prevent the emulator from running correctly.
  * `WARNING`- Warning messages. These may indicate an issue but are not fatal. The
  emulator will normally contunue to work.
  * `INFO` - Informational messages.
  * `VERBOSE` - More verbose messages. Not a high volume.
  * `DEBUG` - Debugging messages. This level of messages are very high volume but provide
  the highest level of information.

### Filtering
Emulator elements have their own logging name, which is used when filtering messages.
  * `vortex` is the general emulator logging name.
  * `vortex.frontend` is used for log messages from the frontend.
  * `vortex.frontend.<facility>` is used for any helper facility used by the frontend.
  * `vortex.core` is used for messages from the emulator core.
  * `vortex.core.<object klass>` are messages for each of the object types.
  * `vortex.core.<object klass>.<object name>` are messages from specific objects.

When logging is enabled, log messages can be filtered by any of the above names.
Multiple filters can be given on the command line in order to display messages from
multiple elements.

In addition to specific names, there are a couple of special forms for filtering
messages:

   * Normally, specifying a filter will display any messages at that level and below.
   For example, using the filter `vortex.core` will display messages from the core and
   all objects of all types. However, if messages only from the core are to be display,
   without messages from objects, the filter `vortex.core.` (note the period at the
   end of the filter) can be used.
   * The wildcard (`*`) symbols is supported at any level of the filter name. For
   example, the filter `vortex.core.*.x` will display any messages from all objects
   with the name `x` regardless of their type. Note that using the filter
   `vortex.core.*` (the wildcard at the end of the filter) is the same as using the
   filter `vortex.core`.

### Core Timing
Time control of the emulator supports two different methods - built-in time control
and time control through a Linux kernel module.

Using the kernel module provides better controller clock granularity and marginally
reduces the CPU utilization. If it is possible to install third-party kernel modules
on the system that is being used to run the emulation, it is recommeded to use this
method.

The built-in time control does not require any external helpers/modules/programs.
However, it has higher latency due to the number of system calls that are required.
This results in a higher controller clock granularity.

The emulator will auto-detect which method should be used.

For installation steps of the kernel module, see 
[Building And Installing The Kernel Module](/docs/Installationmd#building-and-installing-the-kernel-module)

## Available Tools
Vortex includes a couple of useful tools when using or, even, developing the
emulator:

### *monitor.py*

This is a graphical tool that shows state, available commands and events for
all emulated objects. It can be used to monitor the state of the emulator in
real time.

![monitor](/docs/images/monitor.png)

### *emulator_track.py*
This tool is designed to query the emulator for the position of the toolhead
and heater temperature values and then create graphs displaying that information.

It was created in order to visually see whether the Klipper firmware emulation
was doing what it was supposed todo - emulate printing of objects. When the
print emulation is done, the graph can be used to check if the shape of the
"printed" object matches expectations.

```
usage: emulator_track.py [-h] [--graph GRAPH] [--csv CSV] [--data DATA] [--real-time]

options:
  -h, --help     show this help message and exit
  --graph GRAPH  Graph filename
  --csv CSV      Output file for toolhead coordinates
  --data DATA    Toolhead coordinates data
  --real-time    Create dynamic graph
```

### *heater_sim.py*
This tool is useful for simulation of heater configuration parameters. It can be
used for:

* simulating and graphing the heater's temperature graph based on the settings in a
configuration file and constant maximum power input,
* tuning PID control values for the heaters define in the configuration file
based on their settings,
* simulating and graphing heater behavior based on PID values.

The PID tuning option should be used before running the emulator in order to get
control values, which can be copied to the configuration file. If those values are
not provided the heaters will fail to initialize.

```
usage: heater_sim.py [-h] -C CONFIG [--heater HEATER] [--compare COMPARE] [--output OUTPUT] [--runtime RUNTIME] [--down] [--pid-tune]
                     [--target TARGET] [--steps STEPS] [--pid-control] [--temp TEMP] [--kp KP] [--ki KI] [--kd KD]

options:
  -h, --help         show this help message and exit
  -C CONFIG          Emulator configuration file. This option is required so heater settings can be read.
  --heater HEATER    Heater name to work with. If not specified the tool will use all heaters in the configuration file.
  --compare COMPARE  With this option, the tool will compare temperatures read from a file with temperatures simulated based on
                     configuration file values. This is useful for verifying heater behavior in the emulation. A graph with both curves
                     will be generated
  --output OUTPUT    Output graph filename.
  --runtime RUNTIME  Simulation runtime in seconds. If comparing, the runtime will be computed based on the runtime in the file.
  --down             If set, the simulation's power will be set to 0 half way through the runtime.
  --pid-tune         Run PID tuning cycles and generate PID values.

PID tuning parameters:
  --target TARGET    Target temperature for PID tuning.
  --steps STEPS      Cycle count

PID control parameters:
  --pid-control      Run PID control test. This will simulate heater behavior based on PID control values.
  --temp TEMP        Temperate target to be maintained by the PID controller.
  --kp KP            PID control KP value. If this value is given, it will override the value in the configuration file.
  --ki KI            PID control KI value. If this value is given, it will override the value in the configuration file.
  --kd KD            PID control KD value. If this value is given it will override the value in the configuration file.
```
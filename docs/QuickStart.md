# Quick Start Guide

## General Operation
Vortex is comprised of three major parts - the emulated machine
controller, emulation controller, and command processing frontend.

Machine controllers use a controller core (written in C for
performance reason), which handles HW objects.

Vortex machines are defined using a configration file that lists the
objects to be created by the controller core and how they are linked
together.

When the emulator is started, the emulation controller creates the
machine contoller and frontend instances. Next, the machine controller
creates the HW and initalized them, after which machine controller core
starts update cycles, which allow each object to update its internal
state.

Each HW object defines its own set of configuration parameters, commands,
and status information.

After the machine controller has been started, the emulation controller
starts the frontend processor, which starts accepting commands, processing
them into HW object commands, and submitting them to the emulator command
queue. When objects complete commands, command completions are sent back
to the frontend.

HW objects also provide their own set of events, which various parts of
the emulator (including other HW objects) can subscribe to.

## Starting The Emulator
The Vortex emulator executable supports the following command line options:

```
usage: vortex_run.py [-h] [-f FRONTEND] [-s] [-c CONTROLLER] [-F FREQUENCY] [-T PROCESS_FREQUENCY] [-P] [-d LEVEL] [--filter FILTER]
                     [-l LOGFILE] [--extended-logging] [-R] -C CONFIG

options:
  -h, --help            show this help message and exit
  -C, --config CONFIG   HW object configuration file. This argument is required. (default: None)

Frontend Options:
  -f, --frontend FRONTEND
                        The frontend that will be started for the emulation. (default: direct)
  -s                    Enable sequential mode. In this mode, the frontent will execute one command at a time rather than submit commands
                        to the command queue as they are received. (default: False)

Controller Options:
  -c, --controller CONTROLLER
                        The HW controller to be used for the emulation. This argument is required. (default: None)
  -F, --frequency FREQUENCY
                        Frequency of control loop. This control loop is the main emulator control loop. It's the one that updates
                        controller clock and emulation runtime. Higher values provide more precise emulation, at the cost of CPU load.
                        (default: 1MHz)
  -T, --process-frequency PROCESS_FREQUENCY
                        This is the frequency with which the core's event processing threads updates will run. The event processing
                        thread are responsible for processing command submission and completion, event processing, etc. (default: 100KHz)
  -P, --set-priority    Set the priority of the emulator to real-time. This will make the emulator run with higher priority than other
                        processes on the system. This is useful for more precise emulation but may affect system performance as the
                        emulator will take up more CPU cycles. (default: False)

Debug Options:
  -d, --debug LEVEL     Set logging level. Higher logging levels will provide more information but will also affect conroller timing
                        more. (default: INFO)
  --filter FILTER       Filter log messages by the specified module/object. Filter format is a dot-separated hierarchy of
                        modules/objects. For example, the filter 'vortex.core.stepper.X' will only show log messages from the core HW
                        stepper object with name 'X'. '*' can be used to match all modules/objects at the particular level. This option
                        can be used multiple times to filter multiple modules. The filter is applied to the module name and not the
                        logger name. (default: [])
  -l, --logfile LOGFILE
                        Log messages are sent to the file specified by this option. (default: None)
  --extended-logging    Enable extended debugging. When enabled, log messages will also contain the source of the message (filename and
                        line number). (default: False)
  -R, --remote          Start remote API server thread. This thread processes requests from the monitoring application. (default: False)
```

## Examples
To start the emulator using the GCode frontend with `VERBOSE` logging level:
```
vortex_run.py -f gcode -d VERBOSE -C config.cfg
```

To start the emulator with the Klipper frontend, with control loop frequency of 1KHz:
```
vortex_run.py -f klipper -F 1KHz -C config.cfg
```

To start the emulator which `DEBUG` logging level and display only stepper messages:
```
vortex_run.py -f klipper -d DEBUG --filter vortex.core.stepper
```
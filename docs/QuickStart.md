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
usage: vortex.py [-h] [-f FRONTEND] [-s] [-c CONTROLLER] [-F FREQUENCY] [-T TIMER_FREQUENCY] [-P]
                 [-d {NOTSET,DEBUG,VERBOSE,INFO,WARNING,ERROR,CRITICAL}] [--filter FILTER] [-l LOGFILE] [--extended-logging]
                 [-M] -C CONFIG

options:
  -h, --help            show this help message and exit
  -C CONFIG, --config CONFIG
                        HW object configuration file. This argument is required. (default: None)

Frontend Options:
  -f FRONTEND, --frontend FRONTEND
                        The frontend that will be started for the emulation. (default: direct)
  -s                    Enable sequential mode. In this mode, the frontent will execute one command at a time rather than submit
                        commands to the command queue as they are received. (default: False)

Controller Options:
  -c CONTROLLER, --controller CONTROLLER
                        The HW controller to be used for the emulation. This argument is required. (default: None)
  -F, --frequency FREQUENCY
                        This is the frequency with which the object updates will run. (default: 100kHZ)
  -T, --timer-frequency TIMER_FREQUENCY
                        Frequency of time control loop. The time control loop is the main emulator control loop. It's the on
                        that updates controller clock and emulation runtime. Higher values provide more precise emulation but at
                        the cost of CPU load. (default: 1MHz)
  -P, --set-priority    Set the priority of the emulator to real-time. This will make the emulator run with higher priority than
                        other processes on the system. This is useful for more precise emulation but may affect system
                        performance as the emulator will take up more CPU cycles. (default: False)

Debug Options:
  -d, --debug {NOTSET,DEBUG,VERBOSE,INFO,WARNING,ERROR,CRITICAL}
                        Set logging level. Higher logging levels will provide more information but will also affect conroller
                        timing more. (default: INFO)
  --filter FILTER       Filter log messages by the specified module/object. Filter format is a dot-separated hierarchy of
                        modules/objects. For example, the filter 'core.stepper.X' will only show log messages from the core HW
                        stepper object with name 'X'. '*' can be used to match all modules/objects at the particular level. This
                        option can be used multiple times to filter multiple modules. The filter is applied to the module name
                        and not the logger name. (default: [])
  -l, --logfile LOGFILE
                        Log messages are sent to the file specified by this option. (default: None)
  --extended-logging    Enable extended debugging. When enabled, log messages will also contain the source of the message
                        (filename and line number). (default: False)
  -M, --monitor         Start monitoring server thread. This thread processes requests from the monitoring application.
                        (default: False)
```

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
onject commands, or any data that the instantiated frontend can process.

For detailed information on the emulator's operation, see the 
[architecture description](/docs/Architecture.md) document.
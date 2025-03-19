# Vortex Architecture

## Overview
Vortex's architecture is comprised of three major parts - emulation contoller,
HW controller, and frontend.

The emulation controller is the main control object. It's purpose is to start
and stop the HW controller and frontend, and plumb the controller objects to
the frontend objects.

The HW controller emulates the actual hardware in the machine. It creates HW
object based on the content of the configuration file.

The frontend's responsibility is to accept commands from the user, translate
them to HW object commands, submit them to the command queue, and process any
responses to the user.

## HW Controller Architecture
HW controllers are an abstraction that is supposed to roughly translate to a
machine's control board/HW.

The higher level HW controller is a Python class that is a subclass of the
Vortex core module. The core module is a CPython module. The reason why it's
not pure Python will be explain later down.

HW controllers use the configuration file to create and maintain a set of
HW objects. Each HW object type is suppose to emulate a specific type of HW
making up the emulated machine. For example, there are stepper motor,endstop,
probe, and heater objects among others.

Each HW object defines its own set of commands, events, and status. Commands
are used to tell the HW object what action to perform, events are used to
asynchronously notify other parts of the emulation about HW object events,
and report status.

### Types Of Objects
Vortex defines two different types of objects - HW objects and virtual objects.

HW objects emulate the behavior of real HW entities. As such, they require
periodic updates of their intenal states. For performance reasons, all HW
objects are implemented in C and are part of the HW controller core.

Virtual objects don't need to keep internal state. More precisely, their
internal state does not require periodic updates. The internal state is
updated based on submitted commands or is compiled and maintained from states
of other objects. Just as normal objects, virtual objects can define their
own commands and/or events. They can also wait for command completions and
register for event notifications.

### Controller Core
The HW controller core is a CPython module that provides meachnisms for
creating and managing core HW objects. It is written in C to provide better
performance for the update cycle. The main reason for using C is that it
is not subject to the Python GIL, which is debilitating when trying to
reach certain high update frequencies.

The controller core handles HW object management, command processing,
event and command completions.

The controller core starts a set of threads to perform the various core
actions - update threads, a timer thread, and a processor thread. The
update threads purpose is to continously update the HW object state.
There is one thread per HW object. This way there is no serialization in
the updates of all objects. The processor thread handles command
submission between HW objects, command completions, and events. The timer
thread maintains all of the timers the emulator has registered for and
triggers timer handlers.

There is a separate processor thread in order to allow the update
threads to run as fast as possible in order achieve high update
frequencies.

#### Emulation and Controller Frequencies
Each HW controller defines the controller's clock frequency. This is the
frequency with which the actual HW processor run on and can be obtained
from the processor's data sheet.

The emulation control loops run at a different frequency which is
configuration through a command line parameter. There is a main control
thread, which runs at that frequency and is used to wake up any other
threads.

The elapsed controller clock ticks are computed based on the elapsed
wall clock time between control thread loop interations and the defined
controller frequency.

What this means is that the emulator controller clock can only attain a
granularity based on the control thread frequency.

To better understand this, here is an example:

If the HW controller frequency is defined as 1Mhz, each clock tick takes
1000ns. If the control thread frequency is give as 1KHz, it runs once
every 1ms. Therefore, the HW controller clock granularity will be 1000
ticks per control loop interation. In other words, the HW controller
clock will advance is steps of 1000 ticks each control loop iteration.

For emaulation combinations (HW controller, frontend, client) that
require higher HW controller clock precision, the emulator should be
started using a higher update frequency.

Note that higher update frequencies result in higher CPU usage due to
the control thread running more frequently.

##### Thread Scheduling Priority
Thread scheduling policy plays an important role in the clock tick
update frequency.

The main control thread uses `nanosleep()` to sleep for some time
between iterations. The sleep time is determined by the control thread
frequency value specified on the command line.

On Linux, the default thread scheduling policy is `SCHED_OTHER`.
Furthermore, by default, a non-priviledge users cannot change either
the scheduling policy or the thread priority. With default policy and
priority, a call to `nanosleep()` with a duration of 1ns ends up
taken 50us. This means that the best control thread frequency that can
be achieved is 20KHz.

On the other hand, if `SCHED_RR` is used, the latency if `nanosleep()`
with a sleep period of 1ns drops to 2000ns, which is 0.5MHz.

To allow the emulator to switch thread scheduling policy, the following
command should be executed in the shell where the emulator will be
started from, prior to starting it:

```
# sudo prlimit --rtprio=99:99 --pid $$
```

### Core HW Objects

## Frontend Architecture
The frontends' purpose is to read command data from the Vortex serial pipe
and convert them to object commands. Each frontend accepts a different
input data for conversion. For example, the `direct` frontend accepts
direct object commands and the `gcode` frontend accepts GCode commands.

The frontends will parse the input data and after converion, queue the
object commands on the frontend's command queue. After the command is
queued, they can continue processing input data, wait for the command
completion or wait for an object event before proceeding.

If needed, frontends are also responsible for sending result data back to
the client.

The base frontend class provides a lot of the boilerplate support like
creating the Vortex serial pipe, creating interal objects holding emulation
and object data that is used for object and command lookup, handling the
pipe read loop, etc.

## Emulation

## Interaction Between Emulator Entities

### Emulation, Frontends, And Controllers

### Interaction between HW objects
Core HW objects can interact with each other thourgh the same mechanisms
as other parts of the system. When HW objects are created the core provides
each HW object instance with function pointers which can be used to lookup
other objects, submit commands for other objects, receive command completion
and event notifications, and query object status.

One thing to note is that this is only available to core HW objects and not
virtual objects. Virtual objects can lookup and query objects but they cannot
submit commands or receive event notifications.

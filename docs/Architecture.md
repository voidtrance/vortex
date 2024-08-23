# Vortex Architecture

## Overview
Vortex is architecture is comprised of three major parts - emulation contoller,
HW controller, and frontend.

The emulation controller is the main control object. It's purpose is to start
and stop the HW controller and frontend, provide event registration facilities,
and process the command queue.

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
makeing up the emulated machine. For example, there are stepper motor,
endstop, probe, and heater objects among others.

Each HW object defines its own set of commands, events, and status. Commands
are used to tell the HW object what action to perform, events are used to
asynchronously notify other parts of the emulation about HW object events,
and report status.

### Types Of Objects
Vortex defines two different types of objects - HW objects and virtual objects.

HW objects emulate the behavior of real HW entities. As such, they require
periodic update of their intenal states. For performance reasons, all HW
objects are implemented as C code and are part of the HW controller core.

Virtual objects are objects which don't keep internal state. More precisely,
their internal state does not require periodic updates. The internal state is
compiled and maintained from states of other objects. Just as normal objects,
virtual objects can define their own commands and/or events. They can also
wait for command completions and register for event notifications.

### Controller Core
The HW controller core is a CPython module that provides meachinsms for
creating and managing core HW objects. It is written in C to provide better
performance for the update cycle. The main reason for using C is that it
is not subject to the Python GIL, which is debilitating when trying to
reach certain small update frequencies.

The controller core handles HW object management, command processing,
event and command completiong handling.

The controller core starts two separate threads - the update thread and
the processor thread. The update thread's purpose is to continously
update the HW object state. The processor thread handles command
submission between HW objects, command completions, and events.

There is a separate processor thread in order to allow the update
thread to run as fast as possible in order to be able to achieve high
update frequencies.

A goal of the controller core is to simulate the clock frequencies of
the emulated controller board. As such, the update thread attempts
to update all HW objects within the time of a single controll board
clock tick.

A potential improvement which can allow high controller frequencies is
to start a separate thread per HW object. This should result in better
performance as HW object update won't have to wait for the update of
all other HW objects.

### Core HW Objects

## Frontend Architecture
The frontends' purpose is to read command data from the Vortex serial pipe
and convert them to object commands. Each frontend accepts a different
input data for conversion. For example, the `direct` frontend accepts
direct object commands and the `gcode` frontend accepts GCode commands.

The frontends will parse the input data and after converion, queue the
object commands on the emulator's command queue. After the command is
queue, they can continue processing input data, wait for the command
completion or eait for an object event before proceeding.

If needed, frontends are also responsible for sending result data back to
the client.

The base frontend class provides a lot of the boilerplate support like
creating the Vortex serial pipe, creating interal objects hodling emulation
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

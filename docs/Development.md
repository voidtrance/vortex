# Vortex Emulator Development Guide

## Core Library
The Vortex core library is a shared library that provides some
utility functionality that can be used by HW objects. Each HW
shared object file is linked against this library.

### Allocation Cache
The goal of the Vortex core and HW objects is to do the object
update cycle as quickly as possible in order to support high
controller frequencies.

To help with this, the allocation cache is an object cache that
should speed up object allocations and freeing.

HW objects can create a cache for a particular data structure/object.
Upon creation, a certain number of these structure/objects will be
pre-allocated. When a HW object tries to allocate from the cache,
one of the pre-allocated structures/objects is returned. If the
set of pre-allocated structures/objects is exhausted, the cache will
attempt to extend the cache. HW object should receive an allocation
error only when there are no free stuctures/objects and the cache
could not be extended.

The allocation cache defines the following API:

* `object_cache_t` is an opaque type representing the cache.
* `int object_cache_create(object_cache_t **cache, size_t object_size)`
creates a new object allocation cache. `cache` will be initialized with
the cache data and `object_size` is the size of the allocation object.
* `void *object_cache_alloc(object_cache_t *cache)` will "allocate" an
object from the cache. It returns an object pointer if the allocation
is successfull or `NULL`.
* `void object_cache_free(void *object)` frees an cache object.
* `void object_cache_destory(object_cache_t *cache)` frees the cache and
all its objects.

### Random Number Generators
The random number generators are a set of convinience functions,
which extended the standard random number generations with helpers
that can allocate numbers of a particular type or within a particular
range.

Random number generators define the following API:

* `int random_int(void)`
* `int random_int_limit(int min, int max)`
* `unsigned int random_uint(void)`
* `unsigned int random_uint_limit(unsigned int min, unsigned int max)`
* `uint64_t random_uint64(void)`
* `uint64_t random_uint64_limit(uint64_t min, uint64_t max)`
* `float random_float(void)`
* `float random_float_limit(float min, float max)`
* `double random_double(void)`
* `double random_double_limit(double min, double max)`

The `random_<type>()` variants will return a random number of type
`<type>` that is between `0` and the maximum value of the type.

The `random_<type>_limit()` variants will return a random number of
type `<type>` that is between the values of `min` and `max`.

### Timers
Timers are a facility that allows users to schedule callback that get
called at or after a specific time. The time is measured in controller
clock ticks.

Timers are implemented as part of the emulator core and provide APIs
for both the core objects and Python users.

#### Core Object API
The Core Object API uses the `core_timer_t` type to specify timers. Users
have to fill out an instance of the scruture and call the APIs passing it
as an argument. The structure is defined as such:

```c
typedef struct {
    uint64_t (*callback)(uint64_t ticks, void *data);
    void *data;
} core_timer_t;
```

where `callback` is the callback function to be called when the timer expires
and `data` is a pointer to private data that will be passed to the callback.

* `core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout)`
will register a timer callback to be called on or after `timeout`. The API will
return an opaque handle that will be pass to other timer APIs.
* `int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout)` will
rescheule a timer callback to be called on or after `timeout`. The API will
return `0` on success or `-1` on failure.
* `void core_timer_unregister(core_timer_handle_t handle)` will unregister a
registered timer.

#### Python API
The Python timer API is defined as:

* `vortex.core.register_timer(callback, timeout)` - register the callback `callback`
to be called on or after `timeout`. The API will return a timer handle.
* `vortex.core.reschedule_timer(timer)` - rescheuled the timer `timer`. `timer` is a
timer handle returned by `vortex.core.register_timer()`.
* `vortex.core.unregister_timer(timer)` - unregister the timer `timer`, which is a
timer handle returned by `vortex.core.register_timer()`.

## Adding New HW Objects
HW objects are implemented as C shared libraries which
get loaded on demand based on the object definitions in
the emulator configuration file.

### HW Object Implementation
All HW objects source code is placed in the `src/core/objects`
directory. Usually, each HW object will have it's own source
(`.c`) file and header (`.h`) file.

The header file contains definitions that will be needed by
the core or other objects in order to interact with the new HW
object. This includes command enumarations, command argument
structures, and object status structure.

The source file contains the implemenation of the new HW object.

#### HW Object Implementation Details
Each HW object defines its own data structure which represents
an instance of the HW object. The first member of each HW object
data structure must be the generic object member:

```c
struct my_object {
    core_object_t object;
    ...
}
```

The `core_object_t` structure has the following definition:

```c
/*
 * Common object structure. Objects should wrap
 * this structure in their own object-specific
 * structure.
 * If wrapped, this structure should be the
 * first member of the object-specific
 * structure.
 */
struct core_object {
    core_object_type_t type;
    const char *name;
    LIST_ENTRY(core_object) entry;

    int (*init)(core_object_t *object);
    void (*reset)(core_object_t *object);
    int (*exec_command)(core_object_t *object, core_object_command_t *cmd);
    void (*get_state)(core_object_t *object, void *);
    /*
     * Object update callback. This callback will be called
     * by the timing loop to update the object's state.
     *    - ticks are the number of controller clock ticks that have
     *      elapsed since the last update. The rate of change of
     *      this value depends on the controller's running frequency.
     *    - runtime is the absolute wall clock runtime (in ns) of
     *      the emulator.
     */
    void (*update)(core_object_t *object, uint64_t ticks, uint64_t runtime);
    void (*destroy)(core_object_t *object);

    core_call_data_t call_data;
};
```

When a new instance of the HW object is created, it must fill in
the content of the `core_object_t` structure as part of its creation.

The following members of `core_object_t` must be set:
 * `type` is set to the type of the core object. Adding new types will
 be described later.
 * `name` is set to the name of the object passed in to the object
 creation function.
 * `reset` is set to a function which will reset the state of the
 instance.
 * `update` is set to the function which will update the instance state.
 * `destroy` is set to the function that will destory the object and
 free all its memory.

The `entry` and `call_data` members are for internal use.

All other members are optional. Below are descriptions of their purpose:

* `init` is a function that will initialize the instance. The different
between creating and initializing an instance is that initialization is
done after all objects have been created. Therefore, object that need to
lookup other objects can successfully do that without the need to worry
about object creation sequences.
* `exec_command` is a function that will accept and "execute" commands
sent to the object instance. Executing commands should not be a blocking
process. In other words, when this function is called, it should update
the instance state to record the submitted command and then execute the
command in the object's `update` function.
* `get_state` is a function that will return the object instance's state.

#### Adding New HW Object Types
Adding new HW objects involves several steps described below.

##### Adding New Types To `auto-types.h.in`
Each new HW object types has to be added to several data structures in
`src/core/objects/auto-types.h.in`.

1. The `core_object_type_t` enumeration has to be updated by adding the
new type. Note that the type has to be added before the `@EXTRA_TYPES@`
member.
2. The new type has to be added to the `ObjectTypeExportNames` array. The
new entry should take the form 
`[OBJECT_TYPE_MY_TYPE] = stringify(OBJECT_TYPE_MY_TYPE),`. The new
type should be added prior to the `@EXTRA_TYPE_EXPORT_NAMES@` line.
3. Lastly, the object's name has to be added to the `ObjectTypeNames`
array. The new name should be added prior to the `@EXTRA_TYPE_NAMES@`
line.

#### Adding New HW Object Events to `auto-events.h.in`
If the new HW object defines any new events, those events have to added
to the list of events in `src/core/auto-events.h.in`:

1. Add the new event type, following the naming convention, to the
`core_object_event_type_t` enumeration. The new event type should be added
prior to the `@EXTRA_EVENTS@` line.
2. Add the new event type name to the array `OBJECT_EVENT_NAMES`. The
new event type name should be added prior to the `@EXTRA_EVENT_NAMES@`
line.

##### Adding New Types To `object_defs.py`
`object_defs.py`, which is in `controller/objects/`, contains Python
structure definitions which are used to translate C data structures into
structures that Python can uderstand and use. For this the `ctypes` module
is used to define structures for each HW object type.

Each new HW object must define its own class as a subclass of the
`ObjectDef` class. The HW object class must define `ctypes.Structure`
subtypes for the object's configuration, status, events, and command
argument C structures. The `ctypes.Structure` fields types much match
exactly the types of the corresponding C structure.

##### Building New Types
Newly added HW objects will be built into shared objects automatically.
The Vortex build infrastructure will search for HW objects and will
add them to the build set.

#### Handling Command Completions And Events
In order to perform certain actions like command completion notifications
and event submissions, the core defines a set of helpers which can be used
to perform such actions.

These helpers are the following:

##### CORE_LOOKUP_OBJECT(obj, type, name)</td>
Description: Look up other instantiated objects.

Arguments:
* `obj` is the object doing the lookup.
* `type` is the type of object to lookup
* `name` is the name of the object to lookup.

Return: A `core_object_t *` pointer to the object or `NULL` if not found.

##### CORE_CMD_SUBMIT(obj, target, cmd_id, handler, args)
Description: Submit a command for another HW objects

Arguments:
* `obj` is the object submitting the command.
* `target` is the `core_object_t` pointer to the target object.
* `cmd_id` is the target's command ID.
* `handler` is the command completion handler. If this is `NULL` no command
completion notification will be made.
* `args` is a pointer to the target's command arguments. Note that the caller
must not free this pointer.

Return: A `uint64_t` command ID which can be used to identify the submitted
command.

##### CORE_CMD_COMPLETE(obj, id, status)
Description: Send a command completion notification.

Arguments:
* `obj` is the object doing the lookup.
* `id` is the command ID passed to the object through the `core_command_t` structure.
* `status` is the status code with which the command has completed.

Return: None

##### CORE_EVENT_REGISTER(obj, type, event, name, handler)
Description: Register for event notifications.

Arguments:
* `obj` is the object registering for the event notifications.
* `type` is the type of the object which defines the event.
* `event` is the event type for which to register.
* `name` is the name of the object to which the registration is made. If 
other objects of type `type` issue matching events, `obj` will not be
notified.
* `handler` is the event notification handler callback function.

Return: `0` on successful registartion, `-1` otherwise.

##### CORE_EVENT_UNREGISTER(obj, type, event, name)
Description: Unregister for event notifications.

Arguments:
* `obj` is the object which is unregistering.
* `type` is the type of object from which to unregister.
* `event` is the event type from which to unregister.
* `name` is the object name from which to unregister.

Return: `0` on success, `-1` otherwise.

##### CORE_EVENT_SUBMIT(obj, event, data)
Description: Issue a HW object event.

Arguments:
* `obj` is the object issuing the event.
* `event` is the event which is being issued.
* `data` is pointer to the event's data. Note that the caller must not free
this pointer.

## Adding New Virtual Objects
To add a new virtual objects a new Python file should be created in
`controllers/objects/`.

### Defining The Virtual Object

All virtual objects should follow the template below:

```python
import vortex.controllers.objects.vobj_base as vobj
from vortex.controllers.types import ModuleTypes

class MyVirtualObject(vobj.VirtualObjectBase):
    type = ModuleTypes.NEW_TYPE
    commands = [(id, args, defaults)]
    events = [event_type]
```

The `type` value is the virtual object's type, which should be a
`ModuleTypes` enumeration value that does not already exit. This
value will be added to the core's object types, and in turn, to
the `ModuleTypes` enumeration automatically.

`commands` is a list of tuples where `id` is the object command ID,
`args` is a dictionary that describes the command arguments, and `defaults`
is a tuple containing default values for each of the args_struct members.

`events` is a of object event IDs (ModuleEvents enumeration values).
Just like the `type` value, the virtual object's events will automatically
be added to all appropriate places.

The following is an example of a virtual object that implements a :

```python
import vortex.controllers.objects.vobj_base as vobj
from vortex.controllers.types import ModuleTypes

class MyVirtualObject(vobj.VirtualObjectBase):
    type = ModuleTypes.NEW_TYPE
    commands = [(0, {'opt1': }, defaults)]
    events = [ModuleEvents.COMMAND_COMPLETE]
    def __init__(self):
        super().__init__(self)
        self.run_command[0] = self.my_virtual_obj_command
    def exec_command(self, cmd_id, cmd, args):
        super().exec_command(cmd_id, cmd, args)
        status = self.run_command[cmd](args)
        self.event_submit(ModuleEvents.COMMAND_COMPLETE,
                        {"status": status})
        self.complete_command(cmd_id, status)
    def my_virtual_obj_command(self, args):
        return 0
```

## Debugging
### Emulator Logging
To enable emulator logging, use the `-d` command line option. The emulator accepts the
following debug levels:

* `INFO` - Informational messages.
* `VERBOSE` - Additional message with increased verbosity.
* `DEBUG` - Debug message. This is the most verbose level, producing a high volume of
messages from all modules/objects/etc.
* `WARNING` - Warning message. These are message that are not errors but the user should
be aware of.
* `ERROR` - Error messages. These usually result in the emulator terminating.
* `CRITICAL` - Critical errors. The emulator always terminates on such errors.

By default, log messages are displayed in the console. However, with the `--logfile`
command line option, they can be redirected to a file specified by the option.

If the `--extended-logging` command line option is given, log messages also include the
log module/object name and the filename and line number where the message was issued.

### Message Filtering
Each emulator module/object uses a differnt logging name in order to differentiate which
object/module issues the message. The logging names use the following format:

```
<module>[.<object type>][.<object name>]
```

Some examples for the different sections are:
* `<module>` can be `core` or `frontend`.
* `<object type>` can be `stepper`, `axis`, or `endstop`.
* `<object name>` can be `axisX`, or `stepperX`.

Emulator logging includes support for log message filtering. Filters are given by the
`--filter` command line option. Filters use the same format as the logging name. When
issuing log message, the logging facility will compare the logging name to all filters.
If any of the filters match, the message will be displayed.

When not all section of the filter are specified, all message that match that filter
will be displayed. For example, the filter `core.stepper` will display message from
all HW stepper objects. On the other hand, `core.stepper.stepperX` will display
messages only from the stepper HW object with the name `stepperX`.

Filters also support the `*` wildcard character, which matches any value for the section
where it is found. For example, `core.*.stepperX` will match all massages from any HW
objects with the name `stepperX`.

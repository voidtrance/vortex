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

| API | Description |
| :- | :- |
| `int object_cache_create(object_cache_t **cache, size_t object_size)` | Creates a new object llocation cache. `cache` will be initialized with the cache data and `object_size` is the size of the allocation  object. |
| `void *object_cache_alloc(object_cache_t *cache)` | Allocate an object from the cache. It returns an object pointer if the allocation is successfull or `NULL`. |
| `void object_cache_free(void *object)` | Free an cache object. |
| `void object_cache_destory(object_cache_t *cache)` | Frees the cache and all its objects. |

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
Timers is a facility that allows users to schedule callback that get
called at or after a specific time. The time is measured in controller
clock ticks.

Timers are implemented as part of the emulator core and provide APIs
for both the core objects and the Python layer.

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

| API | Description |
| :- | :- |
| `core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout)` | Register a timer  callback to be called on or after `timeout`. The API will return an opaque handle that will be pass to other timer APIs. |
| `int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout)` | Rescheule a timer callback to be called on or after `timeout`. The API will return `0` on success or `-1` on failure. |
| `void core_timer_unregister(core_timer_handle_t handle)` | Unregister a registered timer. |

#### Python API
The Python timer API is defined as:

| API | Description |
| :- | :- |
| `vortex.core.register_timer(callback, timeout)` | Register the callback `callback` to be called on or after `timeout`. The API will return a timer handle. |
| `vortex.core.reschedule_timer(timer)` | Rescheuled the timer `timer`. `timer` is a timer handle returned by `vortex.core.register_timer()`. |
| `vortex.core.unregister_timer(timer)` | Unregister the timer `timer`, which is a timer handle returned by `vortex.core.register_timer()`. |

### Atomic Operations

The core library has made available a set of APIs for hanlding atomic operations.
The APIs are a more convinient way to use GCC's builtin atomic operations. Both a C
and a Python API are available:

There are APIs that operate on 8, 16, 32, and 64 bit values. In the list below `type`
is one of `uint8_t`, `uint16_t`, `uint32_t`, or `uint64_t`. The name of the various
APIs is based on the the width of the value on which they operate. Therefore, `<size>`
is one of `8`, `16`, `32`, or `64`:

#### Core C API
| API | Description |
| :- | :- |
| `type atomic<size>_load(void)` | Atomically read and return a value. |
| `void atomic<size>_store(type *ptr, type value)`| Atomically write the value `value` into a the variable pointed to by `ptr`. |
| `type atomic<size>_exchange(type *ptr, type value)` | Atomically exchange the current value of the variable pointed to by `ptr` with the value `value` and return the old value.
| `type atomic<size>_compare_exchange(type *ptr, type oldval, type newval)` |  Atomically compare and exchange the 
| `type atomic<size>_add(type *ptr, type value)` | Atomically add `value` to the variable pointed to bye `ptr` and return the new value. |
| `type atomic<size>_sub(type *ptr, type value)` | Atomically subtract `value` from the variable pointed to by `ptr` and return the new value. |
| `type atomic<size>_inc(type *ptr)` | Atomicaly increment the value of the variable pointed to by `ptr` by one and return the new value. |
| `type atomic<size>_dec(type *ptr)` | Atomically decrement the value of the varibale pointed to by `ptr` by one and return the new value. |
| `type atomic<size>_and(type *ptr, type value)` | Perform a bitwise AND operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the new value. |
| `type atomic<size>_load_and(type *ptr, type value)` | Perform a bitwise AND operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the original value. |
| `type atomic<size>_or(type *ptr, type value)` | Perform a bitwise OR operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the new value. |
| `type atomic<size>_load_or(type *ptr, type value)` | Perform a bitwise OR operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the original value. |
| `type atomic<size>_xor(type *ptr, type value)` | Perform a bitwise XOR operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the new value. |
| `type atomic<size>_load_xor(type *ptr, type value)` | Perform a bitwise XOR operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the original value. |
| `type atomic<size>_not(type *ptr)` | Perform a bitwise NOT operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the new value. |
| `type atomic<size>_load_not(type *ptr)` | Perform a bitwise NOT operation on the value of the variable pointed by `ptr` and `value` and store it. Returns the original value. |

#### Python API

The core library includes a Python module which exposes all of the above atomic
operations through a Python class. To use atomic operations through Python, the
`vortex.core.lib.atomics` module needs to be imported. It contains the
`Atomic` class:

`class Atomic(size, value=0, var=None)`

&nbsp;&nbsp;&nbsp;&nbsp;Create an instance of an Atomic object. `size` is the width of
the underlying C variable. `value` is the intial value of the atomic variable. If there
is an existing variable passed from the core to the Python layer, its address can be
given as the `var` value.

##### Properties
`value`

&nbsp;&nbsp;&nbsp;&nbsp;Accessing this property will atomically read and return the
value of the variable

##### Available Operations
For the operations below, assume that a `Atomic()` instance has been created with
`var = Atomic(8)`. All the operations are perform atomically.

`var()`

&nbsp;&nbsp;&nbsp;&nbsp;Calling the instance will read and return the value of the variable.

`var == other`

&nbsp;&nbsp;&nbsp;&nbsp;Compare the value of the instance to another value. The other
value can be another `Atomic()` instance of an integer value.

`var += other`

&nbsp;&nbsp;&nbsp;&nbsp;Add `other` to the value of `var`. `other` can be another instance of
`Atomic()` or an integer.

`var -= other`

&nbsp;&nbsp;&nbsp;&nbsp;Subtract `other` from the value of `var`. `other` can be another
instance of `Atomic()` or an integer.

`var |= other`

&nbsp;&nbsp;&nbsp;&nbsp;Bitwise OR the value of `var` with `other`. `other` can be another
instance of `Atomic()` or an integer.

`var &= other`

&nbsp;&nbsp;&nbsp;&nbsp;Bitwise AND the value of `var` with `other`. `other` can be another
instance of `Atomic()` or an integer.

`var ^= other`

&nbsp;&nbsp;&nbsp;&nbsp;Bitwise XOR (exclusive OR) the value of `var` with `other`.
`other` can be another instance of `Atomic()` or an integer.

`~var`

&nbsp;&nbsp;&nbsp;&nbsp;Bitwise NOT (invert) the value of `var`.

`var.inc()`

&nbsp;&nbsp;&nbsp;&nbsp;Increment the value of `var` by 1.

`var.dec()`

&nbsp;&nbsp;&nbsp;&nbsp;Decrement the value of `var` by 1.

`var.exchange(other)`

&nbsp;&nbsp;&nbsp;&nbsp;Exchange the value of `var` with `other`. `other` can be another
instance of `Atomic()` or an integer.

`var.cmpexg(expected, new)`

&nbsp;&nbsp;&nbsp;&nbsp;Compare the value of `var` to `expected` and, if equal, exchage
it with `new`. Both `expected` and `new` can be either instances of `Atomic()` or
integers.

## Adding New Controllers

Controller implementations are located in the `controllers/` directory. Each controller
is a subclass if `vortex.controllers.Controller`.

## Adding New Frontends

Frontend implementations are located in the `frontends/` directory. Each frontend
implementation should be in its own sub-directory under `frontends/` and all its files
should also be placed there.

Frontend implementations should all be a sub-class of `vortex.frontends.BaseFrontend`.
They should all implement the `_process_command()` method. This method accepts a single
argument - `data` - which is the data sent to the frontend instance through the
`/tmp/vortex` socket.

Additionally, frontend can override any of the `BaseFrontend`'s methods in order to
implement custom functionality.

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
    /*
     * The klass of the object. This is set by the
     * object creation function.
     */
    core_object_klass_t klass;

    /*
     * The object name. Set during object creation.
     */
    const char *name;

    /*
     * Object update frequency in HZ. This is how
     * frequently the `update` callback will be called.
     */
    uint64_t update_frequency;

    /*
     * This member is for internal use.
     */
    LIST_ENTRY(core_object) entry;

    /*
     * Initialize the object.
     * All objects are initialized before the update
     * loop begins.
     */
    int (*init)(core_object_t *object);

    /*
     * Reset the object state.
     * This function is called when the emulator is
     * reset.
     */
    void (*reset)(core_object_t *object);

    /*
     * Object command execution function.
     * This function is called when a command is
     * submitted to the object.
     *    - cmd is the command to execute.
     *    - return value is the command ID of the
     *      command that was executed. If the command
     *      failed, the return value should be
     *      CMD_ERROR_PREFIX | error_code.
    */
    int (*exec_command)(core_object_t *object, core_object_command_t *cmd);

    /*
     * Object state retrieval function.
     * This function is called when the object
     * state is requested.
     *    - state is a pointer to the state structure
     *      that will be filled by the object.
     */
    void (*get_state)(core_object_t *object, void *state);

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

    /*
     * Destory the object.
     * This function should free all object resources.
     */
    void (*destroy)(core_object_t *object);

    /*
     * This is structure is for internal use only.
     */
    core_call_data_t call_data;
};
```

When a new instance of the HW object is created, it must fill in
the content of the `core_object_t` structure as part of its creation.

The following members of `core_object_t` must be set:
 * `klass` is set to the klass of the core object. Adding new klasses will
 be described later.
 * `name` is set to the name of the object passed in to the object
 creation function.
 * `reset` is set to a function which will reset the state of the
 instance.
 * `update` is set to the function which will update the instance state.
 * `destroy` is set to the function that will destory the object and
 free all its memory.

The `entry` and `call_data` members are for internal use.

All other members are optional.

#### Adding New HW Object Klasses
Adding new HW objects involves several steps described below.

##### Adding New Klasses To `auto-klass.h.in`
Each new HW object klass has to be added to several data structures in
`src/core/objects/auto-klass.h.in`.

1. The `core_object_klass_t` enumeration has to be updated by adding the
new klass. Note that the klass has to be added before the `@EXTRA_KLASS@`
member.
2. The new klass has to be added to the `ObjectKlassExportNames` array. The
new entry should take the form 
`[OBJECT_KLASS_MY_KLASS] = stringify(OBJECT_KLASS_MY_KLASS),`. The new
klass should be added prior to the `@EXTRA_KLASS_EXPORT_NAMES@` line.
3. Lastly, the object's name has to be added to the `ObjectKlassNames`
array. The new name should be added prior to the `@EXTRA_KLASS_NAMES@`
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

##### Adding New Klasses To `object_defs.py`
`object_defs.py`, which is in `controller/objects/`, contains Python
structure definitions which are used to translate C data structures into
structures that Python can uderstand and use. For this the `ctypes` module
is used to define structures for each HW object klass.

Each new HW object must define its own class as a subclass of the
`ObjectDef` class. The HW object class must define `ctypes.Structure`
subtypes for the object's configuration, status, events, and command
argument C structures. The `ctypes.Structure` fields types much match
exactly the types of the corresponding C structure.

##### Building New Klasses
Newly added HW objects will be built into shared objects automatically.
The Vortex build infrastructure will search for HW objects and will
add them to the build set.

#### Handling Command Completions And Events
In order to perform certain actions like command completion notifications
and event submissions, the core defines a set of helpers which can be used
to perform such actions.

These helpers are the following:

##### CORE_LOOKUP_OBJECT(obj, klass, name)</td>
Description: Look up other instantiated objects.

Arguments:
* `obj` is the object doing the lookup.
* `klass` is the klass of object to lookup
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

##### CORE_CMD_COMPLETE(obj, id, status, data)
Description: Send a command completion notification.

Arguments:
* `obj` is the object doing the lookup.
* `id` is the command ID passed to the object through the `core_command_t` structure.
* `status` is the status code with which the command has completed.
* `data` is a pointer to a data structure for any data that the command needs to return.
The data structure should be allocated on the heap and will be freed by the core when the
completion is processed.

Return: None

##### CORE_EVENT_REGISTER(obj, klass, event, name, handler)
Description: Register for event notifications.

Arguments:
* `obj` is the object registering for the event notifications.
* `klass` is the klass of the object which defines the event.
* `event` is the event type for which to register.
* `name` is the name of the object to which the registration is made. If 
other objects of klass `klass` issue matching events, `obj` will not be
notified.
* `handler` is the event notification handler callback function.

Return: `0` on successful registartion, `-1` otherwise.

##### CORE_EVENT_UNREGISTER(obj, klass, event, name)
Description: Unregister for event notifications.

Arguments:
* `obj` is the object which is unregistering.
* `klass` is the klass of object from which to unregister.
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
from vortex.core import ObjectKlass

class MyVirtualObject(vobj.VirtualObjectBase):
    klass = ObjectKlass.NEW_KLASS
    commands = [(id, args, defaults)]
    events = [event_type]
```

The `klass` value is the virtual object's klass, which should be a
`ObjectKlass` enumeration value that does not already exit. This
value will be added to the core's object klasses, and in turn, to
the `ObjectKlass` enumeration automatically.

`commands` is a list of tuples where `id` is the object command ID,
`args` is a dictionary that describes the command arguments, and `defaults`
is a tuple containing default values for each of the args_struct members.

`events` is a of object event IDs (ModuleEvents enumeration values).
Just like the `type` value, the virtual object's events will automatically
be added to all appropriate places.

The following is an example of a virtual object that implements a :

```python
import vortex.controllers.objects.vobj_base as vobj
from vortex.core import ObjectKlass
from vortex.core import ObjectEvents

class MyVirtualObject(vobj.VirtualObjectBase):
    klass = ObjectKlass.NEW_KLASS
    commands = [(0, {'opt1': }, defaults)]
    events = [ObjectEvents.COMMAND_COMPLETE]
    def __init__(self):
        super().__init__(self)
        self.run_command[0] = self.my_virtual_obj_command
    def exec_command(self, cmd_id, cmd, args):
        super().exec_command(cmd_id, cmd, args)
        status = self.run_command[cmd](args)
        self.event_submit(ObjectEvents.COMMAND_COMPLETE,
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
<module>[.<object klass>][.<object name>]
```

Some examples for the different sections are:
* `<module>` can be `core` or `frontend`.
* `<object klass>` can be `stepper`, `axis`, or `endstop`.
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

### Submitting Log Messages
The Python layer uses customized Logger objects for logging purposes. It is modified to
implement the filtering described above.

To add logging to Python layer code, a `VortexLogger` object must be created first:

```python
from vortex.frontends import BaseFrontend
import vortex.lib.logging as logging

class MyFrontendClass(BaseFrontend):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("vortex.myfrontend")

    def _process_command(self, data):
        self.logger.debug("Received data: %s", data)
```

The name of the Logger is passed to `logging.getLogger()` and is used for filtering
log messages.

The emulator also hooks up the Python logging to all of the C code, as well. When
the core initializes, it creates a `VortexLogger()` object for the core, itself, as
well as a separate logger for each HW object. The name of the core logger is
`vortex.core` and the name of the loggers for each HW object is
`vortex.core.<object klass>.<object name>`.
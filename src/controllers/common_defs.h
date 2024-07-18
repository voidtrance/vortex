#ifndef __OBJECTS_COMMON_DEFS_H__
#define __OBJECTS_COMMON_DEFS_H__
#include "objects/object_defs.h"
#include "events.h"

typedef core_object_t *(*object_lookup_cb_t)(const core_object_type_t,
					     const char *, void *);
typedef void (*complete_cb_t)(const char *, int, void *);

/*
 * Data structure given to all the objects.
 */
typedef struct {
    object_lookup_cb_t object_lookup;
    void *object_lookup_data;

    /* Callback that object call when a command is complete */
    complete_cb_t completion_callback;

    /* Data that objects have to pass to the completion callback */
    void *completion_data;

    /* Function that object can call to register for object events */
    event_register_t event_register;

    /* Data that objects have to pass to the event_register function. */
    void *event_register_data;

    /* Function to call when unregistering for object events */
    event_register_t event_unregister;

    /* Data that objects have to pass to the event_unregister function. */
    void *event_unregister_data;

    /* Function to issue an object event. */
    event_submit_t event_submit;

    /* Data that the object has to pass to the event_submit function. */
    void *event_submit_data;
} core_call_data_t;

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

#define CORE_LOOKUP_OBJECT(obj, type, name)				\
    (((core_object_t *)(obj))->call_data.object_lookup(			\
	(type), (name),							\
	((core_object_t *)(obj))->call_data.object_lookup_data))
#define CORE_CMD_COMPLETE(obj, id, status)				\
    (((core_object_t *)(obj))->call_data.completion_callback(		\
	(id), (status),	((core_object_t *)(obj))->call_data.completion_data))
#define CORE_EVENT_REGTSIER(obj, type, event, name, handler)		\
    (((core_object_t *)(obj))->call_data.event_register(		\
	(type), (event), (name), ((core_object_t *)(obj)), (handler),	\
	((core_object_t *)(obj))->call_data.event_register_data))
#define CORE_EVENT_UNREGISTER(obj, type, event, name)			\
    (((core_object_t *)(obj))->call_data.event_unregister(		\
	(type), (event), (name), ((core_object_t *)(obj)), (handler),	\
	((core_object_t *)(obj))->call_data.event_unregister_data))
#define CORE_EVENT_SUBMIT(obj, type, id, data)				\
    (((core_object_t *)(obj))->call_data.event_submit(			\
	(type), (id), &(data),						\
	((core_object_t *)(obj))->call_data.event_submit_data))

static inline core_object_id_t core_object_to_id(core_object_t *object) {
    return (core_object_id_t)object;
}

static inline core_object_t *core_id_to_object(core_object_id_t id) {
    if (id != CORE_OBJECT_ID_INVALID)
	return (core_object_t *)id;
    return NULL;
}

static inline void core_object_destroy(core_object_t *object) {
    free((char *)object->name);
}

#endif

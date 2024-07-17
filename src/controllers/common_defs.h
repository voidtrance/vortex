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

#endif

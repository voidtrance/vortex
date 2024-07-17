#ifndef __EVENTS_H__
#define __EVENTS_H__
#include "objects/object_defs.h"

/*
 * Each object that provides any events has to create
 * an entry in this enum with the event type.
 */
typedef enum {
    OBJECT_EVENT_HEATER_TEMP_REACHED,
    OBJECT_EVENT_MAX,
} core_object_event_type_t;

const char *OBJECT_EVENT_NAMES[] = {
    [OBJECT_EVENT_HEATER_TEMP_REACHED] = "HEATER_TEMP_REACHED",
};

/*******
 * Event data structure definitions.
 *
 * Each event will have a matching data structure that
 * describes the data the event will provide.
 */
typedef struct {
    float temp;
} heater_temp_reached_event_data_t;

/*
 * Object event handler type.
 * Object event handlers are called to handle events from
 * any of the objects. The arguments to the event handlers
 * are:
 *    - The object registered for the event.
 *    - The name of the object issuing the event.
 *    - The event type.
 *    - The event data.
 */
typedef void (*event_handler_t)(core_object_t *, const char *,
				const core_object_event_type_t, void *);

/*
 * Signature of call to (un)register for an object event.
 * The arguments are:
 *    - the event type to register for,
 *    - name of the object issuing the event,
 *    - object registering for the event,
 *    - the object's event handler function,
 *    - the data that needs to be passed.
 */
typedef int (*event_register_t)(const core_object_type_t,
				const core_object_event_type_t, const char *,
                                core_object_t *, event_handler_t,
				void *);

/*
 * Signature of call to issue an event.
 * The arguments are:
 *    - the event type being issued,
 *    - the ID of the issuing object,
 *    - a pointer to the event data structure,
 *    - the data that needs to be passed.
 */
typedef int (*event_submit_t)(const core_object_event_type_t,
			      const core_object_id_t id, void *, void *);


#endif

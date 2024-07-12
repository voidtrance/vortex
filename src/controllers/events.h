#ifndef __EVENTS_H__
#define __EVENTS_H__
#include "objects/object_defs.h"

/*
 * Each object that provides any events has to create
 * an entry in this enum with the event type.
 */
typedef enum {
    OBJECT_EVENT_MAX,
} core_object_event_t;

/*******
 * Event data structure definitions.
 *
 * Each event will have a matching data structure that
 * describes the data the event will provide.
 */


typedef void (*event_handler_t)(core_object_t *, const core_object_event_t,
                                const char *, void *);

/*
 * Signature of call to (un)register for an object event.
 * The arguments are:
 *    - the event type to register for,
 *    - name of the object issuing the event,
 *    - object registering for the event,
 *    - the object's event handler function,
 *    - the data that needs to be passed.
 */
typedef int (*event_register_t)(const core_object_event_t, const char *,
                                core_object_t *, event_handler_t,
				void *);

/*
 * Signature of call to issue an event.
 * The arguments are:
 *    - the event type being issued,
 *    - the name of the issuing object,
 *    - a pointer to the event data structure,
 *    - the data that needs to be passed.
 */
typedef int (*event_submit_t)(const core_object_event_t, const char *,
			      void *, void *);


#endif

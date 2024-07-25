/*
 * gEmulator - GCode machine emulator
 * Copyright (C) 2024  Mitko Haralanov
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
#ifndef __EVENTS_H__
#define __EVENTS_H__
#include <stdint.h>
#include <stdbool.h>
#include "objects/object_defs.h"

/*
 * Each object that provides any events has to create
 * an entry in this enum with the event type.
 */
typedef enum {
    OBJECT_EVENT_STEPPER_MOVE_COMPLETE,
    OBJECT_EVENT_HEATER_TEMP_REACHED,
    OBJECT_EVENT_ENDSTOP_TRIGGER,
    OBJECT_EVENT_AXIS_HOMED,
    OBJECT_EVENT_MAX,
} core_object_event_type_t;

const char *OBJECT_EVENT_NAMES[] = {
    [OBJECT_EVENT_STEPPER_MOVE_COMPLETE] = "STEPPER_MOVE_COMPLETE",
    [OBJECT_EVENT_HEATER_TEMP_REACHED] = "HEATER_TEMP_REACHED",
    [OBJECT_EVENT_ENDSTOP_TRIGGER] = "ENDSTOP_TRIGGER",
    [OBJECT_EVENT_AXIS_HOMED] = "AXIS_HOMED",
};

/*******
 * Event data structure definitions.
 *
 * Each event will have a matching data structure that
 * describes the data the event will provide.
 */
typedef struct {
    uint64_t steps;
} stepper_move_comeplete_event_data_t;

typedef struct {
    float temp;
} heater_temp_reached_event_data_t;

typedef struct {
    bool triggered;
} endstop_trigger_event_data_t;

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

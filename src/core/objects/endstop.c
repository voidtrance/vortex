/*
 * vortex - GCode machine emulator
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
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <cache.h>
#include "../common_defs.h"
#include "object_defs.h"
#include "../events.h"
#include "endstop.h"
#include "axis.h"

typedef enum {
    ENDSTOP_TYPE_MIN,
    ENDSTOP_TYPE_MAX,
    ENDSTOP_TYPE_END,
} endstop_type_t;

const char *endstop_type_names[] = {
    [ENDSTOP_TYPE_MIN] = "min",
    [ENDSTOP_TYPE_MAX] = "max",
};

typedef struct {
    const char type[4];
    const char axis[64];
} endstop_config_params_t;

typedef struct {
    core_object_t object;
    core_object_t *axis;
    const char *axis_name;
    endstop_type_t type;
    bool triggered;
} endstop_t;

static object_cache_t *endstop_event_cache;

static void endstop_update(core_object_t *object, uint64_t ticks,
			   uint64_t runtime);

static void endstop_reset(core_object_t *object) {
    endstop_update(object, 0, 0);
}

static int endstop_init(core_object_t *object) {
    endstop_t *endstop = (endstop_t *)object;

    endstop->axis = CORE_LOOKUP_OBJECT(endstop, OBJECT_TYPE_AXIS,
				       endstop->axis_name);
    if (!endstop->axis)
	return -1;

    endstop_update(object, 0, 0);
    return 0;
}

static void endstop_update(core_object_t *object, uint64_t ticks,
			   uint64_t runtime) {
    endstop_t *endstop = (endstop_t *)object;
    endstop_trigger_event_data_t *event;
    axis_status_t status;
    bool state = endstop->triggered;

    endstop->axis->get_state(endstop->axis, &status);
    if ((endstop->type == ENDSTOP_TYPE_MIN && status.position == 0) ||
	(endstop->type == ENDSTOP_TYPE_MAX && status.position == status.length))
	endstop->triggered = true;
    else
        endstop->triggered = false;

    if (state != endstop->triggered) {
	event = object_cache_alloc(endstop_event_cache);
	if (!event)
	    return;

	event->triggered = endstop->triggered;
	CORE_EVENT_SUBMIT(endstop, OBJECT_EVENT_ENDSTOP_TRIGGER, event);
    }
}

static void endstop_status(core_object_t *object, void *status) {
    endstop_t *endstop = (endstop_t *)object;
    endstop_status_t *s = (endstop_status_t *)status;

    s->triggered = endstop->triggered;
    strncpy((char *)s->type, endstop_type_names[endstop->type], 3);
}

static void endstop_destroy(core_object_t *object) {
    endstop_t *endstop = (endstop_t *)object;

    object_cache_destroy(endstop_event_cache);
    core_object_destroy(object);
    free((char *)endstop->axis_name);
    free(endstop);
}

endstop_t *object_create(const char *name, void *config_ptr) {
    endstop_t *endstop;
    endstop_config_params_t *config = (endstop_config_params_t *)config_ptr;
    endstop_type_t type;

    endstop = calloc(1, sizeof(*endstop));
    if (!endstop)
	return NULL;

    if (object_cache_create(&endstop_event_cache,
			     sizeof(endstop_trigger_event_data_t))) {
	free(endstop);
	return NULL;
    }

    endstop->object.type = OBJECT_TYPE_ENDSTOP;
    endstop->object.name = strdup(name);
    endstop->object.init = endstop_init;
    endstop->object.update = endstop_update;
    endstop->object.reset = endstop_reset;
    endstop->object.get_state = endstop_status;
    endstop->object.destroy = endstop_destroy;
    endstop->axis_name = strdup(config->axis);

    for (type = 0; type < ENDSTOP_TYPE_END; type++) {
	if (!strncmp(config->type, endstop_type_names[type],
		     strlen(endstop_type_names[type]))) {
	    endstop->type = type;
	    break;
	}
    }

    return endstop;
}

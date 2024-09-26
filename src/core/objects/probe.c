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
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <time.h>
#include <kinematics.h>
#include "../debug.h"
#include "../common_defs.h"
#include "../events.h"
#include "object_defs.h"
#include "probe.h"
#include "toolhead.h"
#include <cache.h>
#include <random.h>

typedef struct {
    const char toolhead[64];
    float offset[AXIS_TYPE_MAX];
    float range;
} probe_config_params_t;


typedef struct {
    core_object_t object;
    core_object_t *toolhead;
    const char *toolhead_name;
    float offsets[AXIS_TYPE_MAX];
    double position[AXIS_TYPE_MAX];
    float range;
    float fuzz;
    bool triggered;
} probe_t;

static object_cache_t *probe_event_cache = NULL;

static int probe_init(core_object_t *object) {
    probe_t *probe = (probe_t *)object;

    probe->toolhead = CORE_LOOKUP_OBJECT(probe, OBJECT_TYPE_TOOLHEAD,
					 probe->toolhead_name);
    if (!probe->toolhead) {
	log_error(probe, "Did not find toolhead object '%s'",
		  probe->toolhead_name);
	return -ENOENT;
    }

    return 0;
}

static void probe_get_state(core_object_t *object, void *state) {
    probe_t *probe = (probe_t *)object;
    probe_status_t *s = (probe_status_t *)state;

    memset(s, 0, sizeof(*s));
    memcpy(s->position, probe->position, sizeof(s->position));
    memcpy(s->offsets, probe->offsets, sizeof(s->offsets));
    s->triggered = probe->triggered;
}

static void probe_update(core_object_t *object, uint64_t ticks,
			 uint64_t runtime) {
    probe_t *probe = (probe_t *)object;
    toolhead_status_t status;
    bool within_range = true;
    size_t i;

    probe->toolhead->get_state(probe->toolhead, &status);
    for (i = 0; i < AXIS_TYPE_MAX; i++) {
	log_debug(probe, "Toolhead axis %u: %.15f", i, status.position[i]);
	probe->position[i] = status.position[i] + probe->offsets[i];
	within_range &= status.position[i] <= probe->fuzz;
    }

    if (within_range) {
        probe_trigger_event_data_t *data;
        bool state = probe->triggered;

        probe->triggered = true;

	// Send event only when probe is triggered.
	if (!state) {
	    data = object_cache_alloc(probe_event_cache);
	    if (data) {
		memcpy(data->position, probe->position, sizeof(data->position));
		CORE_EVENT_SUBMIT(probe, OBJECT_EVENT_PROBE_TRIGGERED, data);
	    }
	}
    } else {
	if (probe->triggered)
	    probe->fuzz = random_float_limit(0, probe->range);

        probe->triggered = false;
    }
}

static void probe_destroy(core_object_t *object) {
    probe_t *probe = (probe_t *)object;

    core_object_destroy(object);
    object_cache_destroy(probe_event_cache);
    free((char *)probe->toolhead_name);
    free(probe);
}

probe_t *object_create(const char *name, void *config_ptr) {
    probe_t *probe;
    probe_config_params_t *config = (probe_config_params_t *)config_ptr;
    size_t i;

    probe = calloc(1, sizeof(*probe));
    if (!probe)
	return NULL;

    probe->object.type = OBJECT_TYPE_PROBE;
    probe->object.name = strdup(name);
    probe->object.init = probe_init;
    probe->object.update = probe_update;
    probe->object.get_state = probe_get_state;
    probe->object.destroy = probe_destroy;
    probe->toolhead_name = strdup(config->toolhead);
    memcpy(probe->offsets, config->offset, sizeof(probe->offsets));
    probe->range = config->range;

    if (object_cache_create(&probe_event_cache,
			    sizeof(probe_trigger_event_data_t))) {
	core_object_destroy(&probe->object);
	free(probe);
	return NULL;
    }

    return probe;
}

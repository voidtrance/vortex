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
#include "../debug.h"
#include "../common_defs.h"
#include "../events.h"
#include "object_defs.h"
#include "probe.h"
#include "axis.h"
#include <cache.h>
#include <random.h>

typedef struct {
    float z_offset;
    float range;
} probe_config_params_t;

typedef struct {
    core_object_t object;
    core_object_t *z_axis;
    float z_offset;
    float position;
    float range;
    bool triggered;
} probe_t;

static object_cache_t *probe_event_cache = NULL;

static int probe_init(core_object_t *object) {
    probe_t *probe = (probe_t *)object;

    probe->z_axis = CORE_LOOKUP_OBJECT(probe, OBJECT_TYPE_AXIS, "z");
    if (!probe->z_axis) {
	log_error(probe, "Did not find a Z axis");
	return -ENOENT;
    }

    return 0;
}

static void probe_get_state(core_object_t *object, void *state) {
    probe_t *probe = (probe_t *)object;
    probe_status_t *s = (probe_status_t *)state;

    s->position = probe->position;
    s->triggered = probe->triggered;
}

static void probe_update(core_object_t *object, uint64_t ticks,
			 uint64_t runtime) {
    probe_t *probe = (probe_t *)object;
    axis_status_t status;
    float fuzz = random_float_limit(0, probe->range);
    bool state = probe->triggered;

    probe->z_axis->get_state(probe->z_axis, &status);
    log_debug(probe, "z axis position: %f", status.position);
    if (status.position <= probe->z_offset + fuzz) {
	probe_trigger_event_data_t *data;

	probe->triggered = true;
	probe->position = status.position;

	// Send event only when probe is triggered.
	if (!state) {
	    data = object_cache_alloc(probe_event_cache);
	    if (data) {
		data->position = probe->position;
		CORE_EVENT_SUBMIT(probe, OBJECT_EVENT_PROBE_TRIGGERED,
				  core_object_to_id((core_object_t *)probe),
				  data);
	    }
	}
    } else {
        probe->triggered = false;
    }
}

static void probe_destroy(core_object_t *object) {
    probe_t *probe = (probe_t *)object;

    core_object_destroy(object);
    object_cache_destroy(probe_event_cache);
    free(probe);
}

probe_t *object_create(const char *name, void *config_ptr) {
    probe_t *probe;
    probe_config_params_t *config = (probe_config_params_t *)config_ptr;

    probe = calloc(1, sizeof(*probe));
    if (!probe)
	return NULL;

    probe->object.type = OBJECT_TYPE_PROBE;
    probe->object.name = strdup(name);
    probe->object.init = probe_init;
    probe->object.update = probe_update;
    probe->object.get_state = probe_get_state;
    probe->object.destroy = probe_destroy;
    probe->z_offset = config->z_offset;
    probe->range = config->range;

    if (object_cache_create(&probe_event_cache,
			    sizeof(probe_trigger_event_data_t))) {
	core_object_destroy(&probe->object);
	free(probe);
	return NULL;
    }

    return probe;
}

/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2025 Mitko Haralanov
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
#include <pthread.h>
#include <logging.h>
#include <common_defs.h>
#include <events.h>
#include "object_defs.h"
#include "probe.h"
#include "toolhead.h"
#include <cache.h>
#include <random.h>

typedef struct {
    const char toolhead[TOOLHEAD_NAME_SIZE];
    float offset[AXIS_TYPE_MAX];
    const char **axes;
    float range;
    char pin[8];
} probe_config_params_t;

typedef struct {
    core_object_t object;
    core_object_t *toolhead;
    const char *toolhead_name;
    float offsets[AXIS_TYPE_MAX];
    double position[AXIS_TYPE_MAX];
    bool axis_valid[AXIS_TYPE_MAX];
    float range;
    float fuzz;
    char pin[PIN_NAME_SIZE];
    uint8_t pin_word;
    bool triggered;
    pthread_mutex_t lock;
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

    probe->fuzz = random_float_limit(0, probe->range);
    return 0;
}

static void probe_get_state(core_object_t *object, void *state) {
    probe_t *probe = (probe_t *)object;
    probe_status_t *s = (probe_status_t *)state;

    memset(s, 0, sizeof(*s));
    strncpy(s->pin, probe->pin, sizeof(s->pin));
    memcpy(s->offsets, probe->offsets, sizeof(s->offsets));
    pthread_mutex_lock(&probe->lock);
    memcpy(s->position, probe->position, sizeof(s->position));
    s->triggered = probe->triggered;
    s->pin_addr = (unsigned long)&probe->pin_word;
    pthread_mutex_unlock(&probe->lock);
}

static void probe_update(core_object_t *object, uint64_t ticks,
                         uint64_t runtime) {
    probe_t *probe = (probe_t *)object;
    toolhead_status_t status;
    bool state = probe->triggered;
    size_t i;

    probe->toolhead->get_state(probe->toolhead, &status);
    pthread_mutex_lock(&probe->lock);
    probe->triggered = true;
    for (i = 0; i < AXIS_TYPE_MAX; i++) {
        if (!probe->axis_valid[i])
            continue;

        probe->position[i] =
            ((double *)&status.position)[i] + probe->offsets[i];
        probe->triggered &= ((double *)&status.position)[i] <= probe->fuzz;
    }

    probe->pin_word = !!probe->triggered;
    pthread_mutex_unlock(&probe->lock);

    if (probe->triggered && !state) {
        probe_trigger_event_data_t *data;

        data = object_cache_alloc(probe_event_cache);
        if (data) {
            memcpy(data->position, probe->position, sizeof(data->position));
            CORE_EVENT_SUBMIT(probe, OBJECT_EVENT_PROBE_TRIGGERED, data);
        }
    } else if (!probe->triggered && state) {
        probe->fuzz = random_float_limit(0, probe->range);
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
    const char **axis;

    probe = calloc(1, sizeof(*probe));
    if (!probe)
        return NULL;

    probe->object.type = OBJECT_TYPE_PROBE;
    probe->object.name = strdup(name);
    probe->object.init = probe_init;
    probe->object.update = probe_update;
    probe->object.update_frequency = 5000; /* 5 kHz */
    probe->object.get_state = probe_get_state;
    probe->object.destroy = probe_destroy;
    probe->toolhead_name = strdup(config->toolhead);
    memcpy(probe->offsets, config->offset, sizeof(probe->offsets));
    probe->range = config->range;
    strncpy(probe->pin, config->pin, sizeof(probe->pin));
    pthread_mutex_init(&probe->lock, NULL);

    if (object_cache_create(&probe_event_cache,
                            sizeof(probe_trigger_event_data_t))) {
        core_object_destroy(&probe->object);
        free(probe);
        return NULL;
    }

    axis = config->axes;
    while (*axis) {
        axis_type_t type = kinematics_axis_type_from_char(*axis[0]);

        probe->axis_valid[type] = true;
        axis++;
    }

    return probe;
}

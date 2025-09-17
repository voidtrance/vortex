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
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <cache.h>
#include <errno.h>
#include <utils.h>
#include <math.h>
#include <kinematics.h>
#include <common_defs.h>
#include <debug.h>
#include "object_defs.h"
#include <events.h>
#include "toolhead.h"
#include "axis.h"

#define PRECISION 2
static float precision_factor;

typedef struct {
    const char axes[AXIS_TYPE_MAX];
    const char attachment[AXIS_TYPE_MAX];
} toolhead_config_params_t;

typedef struct {
    core_object_t *obj;
    axis_type_t type;
} toolhead_axis_t;

typedef struct {
    core_object_t object;
    axis_type_t *axes;
    toolhead_axis_t *attachment;
    coordinates_t position;
    bool single_event_guard;
    size_t n_axes;
    size_t n_attached;
} toolhead_t;

static object_cache_t *toolhead_event_cache = NULL;

static inline double get_axis_position(const coordinates_t *positions,
                                       axis_type_t type) {
    switch (type) {
    case AXIS_TYPE_X:
        return positions->x;
    case AXIS_TYPE_Y:
        return positions->y;
    case AXIS_TYPE_Z:
        return positions->z;
    case AXIS_TYPE_A:
        return positions->a;
    case AXIS_TYPE_B:
        return positions->b;
    case AXIS_TYPE_C:
        return positions->c;
    case AXIS_TYPE_E:
        return positions->e;
    default:
        return 0.0; // Invalid axis type
    }
}

static inline void set_axis_position(coordinates_t *positions, axis_type_t type,
                                     double position) {
    switch (type) {
    case AXIS_TYPE_X:
        positions->x = position;
        break;
    case AXIS_TYPE_Y:
        positions->y = position;
        break;
    case AXIS_TYPE_Z:
        positions->z = position;
        break;
    case AXIS_TYPE_A:
        positions->a = position;
        break;
    case AXIS_TYPE_B:
        positions->b = position;
        break;
    case AXIS_TYPE_C:
        positions->c = position;
        break;
    case AXIS_TYPE_E:
        positions->e = position;
        break;
    default:
        break;
    }
}

static int toolhead_init(core_object_t *object) {
    toolhead_t *toolhead = (toolhead_t *)object;
    axis_status_t status;
    core_object_t **axes;
    core_object_t **axis_ptr;
    size_t i;

    axes = CORE_LIST_OBJECTS(toolhead, OBJECT_KLASS_AXIS);
    if (!axes) {
        log_error(toolhead, "No axis list");
        return -ENOENT;
    }

    for (i = 0; i < toolhead->n_attached; i++) {
        axis_ptr = axes;
        do {
            core_object_t *axis = *axis_ptr;

            if (!axis)
                break;

            axis->get_state(axis, &status);
            if (status.type == toolhead->attachment[i].type) {
                toolhead->attachment[i].obj = axis;
                break;
            }

            axis_ptr++;
        } while (axis_ptr);

        if (!toolhead->attachment[i].obj) {
            log_error(toolhead, "Could not find axis of type %u",
                      toolhead->attachment[i].type);
            return -1;
        }
    }

    free(axes);
    return 0;
}

static void toolhead_update(core_object_t *object, uint64_t ticks,
                            uint64_t runtime) {
    toolhead_t *toolhead = (toolhead_t *)object;
    toolhead_origin_event_data_t *event;
    coordinates_t axis_positions = { 0 };
    axis_status_t status;
    bool at_origin = true;
    size_t i;

    for (i = 0; i < toolhead->n_attached; i++) {
        core_object_t *axis = toolhead->attachment[i].obj;
        axis_type_t type = toolhead->attachment[i].type;

        axis->get_state(axis, &status);
        set_axis_position(&axis_positions, type, status.position);
    }

    if (kinematics_get_toolhead_position(&axis_positions,
                                         &toolhead->position)) {
        log_error(toolhead, "Failed to get toolhead position");
        return;
    }

    log_debug(toolhead, "position: %.5f, %.5f, %.5f, %.5f, %.5f, %.5f, %.5f",
              toolhead->position.x, toolhead->position.y, toolhead->position.z,
              toolhead->position.a, toolhead->position.b, toolhead->position.c,
              toolhead->position.e);
    for (i = 0; i < toolhead->n_axes; i++) {
        double axis_position = get_axis_position(&toolhead->position, toolhead->axes[i]);

        axis_position = round(axis_position * precision_factor);
        axis_position = (double)((long)axis_position) / precision_factor;
        log_debug(toolhead, "     position %c: %f", kinematics_axis_type_to_char(toolhead->axes[i]),
                  axis_position);
        if (axis_position > (1 / precision_factor)) {
            at_origin = false;
            break;
        }
    }

    if (!at_origin && toolhead->single_event_guard)
        toolhead->single_event_guard = false;

    log_debug(toolhead, "at_origin: %u, single_event_guard: %u", at_origin,
              toolhead->single_event_guard);
    if (at_origin && !toolhead->single_event_guard) {
        event = object_cache_alloc(toolhead_event_cache);
        if (event) {
            memcpy(event->position, &toolhead->position,
                   sizeof(event->position));
            log_debug(toolhead, "TOOLHEAD_ORIGIN triggered");
            CORE_EVENT_SUBMIT(toolhead, OBJECT_EVENT_TOOLHEAD_ORIGIN, event);
            toolhead->single_event_guard = true;
        }
    }
}

static void toolhead_status(core_object_t *object, void *status) {
    toolhead_t *toolhead = (toolhead_t *)object;
    toolhead_status_t *s = (toolhead_status_t *)status;
    size_t i;

    memset(s, 0, sizeof(*s));
    memcpy(&s->position, &toolhead->position, sizeof(toolhead->position));
    for (i = 0; i < ARRAY_SIZE(s->axes); i++) {
        if (i < toolhead->n_axes)
            s->axes[i] = toolhead->axes[i];
        else
            s->axes[i] = AXIS_TYPE_MAX;
    }
}

static void toolhead_destroy(core_object_t *object) {
    toolhead_t *toolhead = (toolhead_t *)object;

    object_cache_destroy(toolhead_event_cache);
    free(toolhead->attachment);
    free(toolhead->axes);
    core_object_destroy(object);
    free(toolhead);
}

toolhead_t *object_create(const char *name, void *config_ptr) {
    toolhead_t *toolhead;
    toolhead_config_params_t *config = (toolhead_config_params_t *)config_ptr;
    size_t n_axis;

    toolhead = calloc(1, sizeof(*toolhead));
    if (!toolhead)
        return NULL;

    if (object_cache_create(&toolhead_event_cache,
                            sizeof(toolhead_origin_event_data_t))) {
        free(toolhead);
        return NULL;
    }

    toolhead->object.klass = OBJECT_KLASS_TOOLHEAD;
    toolhead->object.name = strdup(name);
    toolhead->object.init = toolhead_init;
    toolhead->object.update = toolhead_update;
    toolhead->object.update_frequency = 1000; /* 1kHz */
    toolhead->object.get_state = toolhead_status;
    toolhead->object.destroy = toolhead_destroy;

    toolhead->n_axes = strlen(config->axes);
    toolhead->axes = calloc(toolhead->n_axes, sizeof(*toolhead->axes));
    if (!toolhead->axes) {
        free((char *)toolhead->object.name);
        free(toolhead);
        return NULL;
    }

    for (n_axis = 0; n_axis < toolhead->n_axes; n_axis++) {
        toolhead->axes[n_axis] =
            kinematics_axis_type_from_char(config->axes[n_axis]);
    }

    toolhead->n_attached = strlen(config->attachment);
    toolhead->attachment =
        calloc(toolhead->n_attached, sizeof(*toolhead->attachment));
    if (!toolhead->attachment) {
        free(toolhead->axes);
        free((char *)toolhead->object.name);
        free(toolhead);
        return NULL;
    }

    for (n_axis = 0; n_axis < toolhead->n_attached; n_axis++) {
        toolhead->attachment[n_axis].type =
            kinematics_axis_type_from_char(config->attachment[n_axis]);
    }

    precision_factor = pow(10, PRECISION);
    return toolhead;
}

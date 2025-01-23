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
#include <errno.h>
#include <utils.h>
#include <kinematics.h>
#include <common_defs.h>
#include "object_defs.h"
#include <events.h>
#include "toolhead.h"
#include "axis.h"

typedef struct {
    const char **axes;
} toolhead_config_params_t;

typedef struct {
    core_object_t *obj;
    axis_type_t type;
} toolhead_axis_t;

typedef struct {
    core_object_t object;
    toolhead_axis_t *axes;
    double position[AXIS_TYPE_MAX];
    size_t n_axes;
} toolhead_t;

static object_cache_t *toolhead_event_cache;

static int toolhead_init(core_object_t *object) {
    toolhead_t *toolhead = (toolhead_t *)object;
    axis_status_t status;
    core_object_t **axes;
    core_object_t **axis_ptr;
    size_t i;

    axes = CORE_LIST_OBJECTS(toolhead, OBJECT_TYPE_AXIS);
    if (!axes) {
        log_error(toolhead, "No axis list");
        return -ENOENT;
    }

    for (i = 0; i < toolhead->n_axes; i++) {
        axis_ptr = axes;
        do {
            core_object_t *axis = *axis_ptr;

            axis->get_state(axis, &status);
            if (status.type == toolhead->axes[i].type) {
                toolhead->axes[i].obj = axis;
                toolhead->position[i] = status.position;
                break;
            }
            axis_ptr++;
        } while (axis_ptr);

        if (!toolhead->axes[i].obj) {
            log_error(toolhead, "Could not find axis of type %u",
                      toolhead->axes[i].type);
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
    axis_status_t status;
    bool at_origin = true;
    size_t i;

    for (i = 0; i < toolhead->n_axes; i++) {
        core_object_t *axis = toolhead->axes[i].obj;
        axis_type_t type = toolhead->axes[i].type;

        axis->get_state(axis, &status);
        toolhead->position[type] = status.position;
        at_origin &= toolhead->position[type] == 0.0;
    }

    log_debug(toolhead, "position: %.15f, %.15f, %.15f",
              toolhead->position[0], toolhead->position[1],
              toolhead->position[2]);
    if (at_origin) {
        event = object_cache_alloc(toolhead_event_cache);
        if (event) {
            memcpy(event->position, toolhead->position,
                   sizeof(event->position));
            CORE_EVENT_SUBMIT(toolhead, OBJECT_EVENT_TOOLHEAD_ORIGIN, event);
        }
    }
}

static void toolhead_status(core_object_t *object, void *status) {
    toolhead_t *toolhead = (toolhead_t *)object;
    toolhead_status_t *s = (toolhead_status_t *)status;
    size_t i;

    memset(s, 0, sizeof(*s));
    memcpy(s->position, toolhead->position, sizeof(toolhead->position));
    for (i = 0; i < ARRAY_SIZE(s->axes); i++) {
        if (i < toolhead->n_axes)
            s->axes[i] = toolhead->axes[i].type;
        else
            s->axes[i] = AXIS_TYPE_MAX;
    }
}

static void toolhead_destroy(core_object_t *object) {
    toolhead_t *toolhead = (toolhead_t *)object;

    object_cache_destroy(toolhead_event_cache);
    core_object_destroy(object);
    free(toolhead);
}

toolhead_t *object_create(const char *name, void *config_ptr) {
    toolhead_t *toolhead;
    toolhead_config_params_t *config = (toolhead_config_params_t *)config_ptr;
    const char *axis;
    size_t n_axis = 0;

    toolhead = calloc(1, sizeof(*toolhead));
    if (!toolhead)
        return NULL;

    if (object_cache_create(&toolhead_event_cache,
                            sizeof(toolhead_origin_event_data_t))) {
        free(toolhead);
        return NULL;
    }

    toolhead->object.type = OBJECT_TYPE_TOOLHEAD;
    toolhead->object.name = strdup(name);
    toolhead->object.init = toolhead_init;
    toolhead->object.update = toolhead_update;
    toolhead->object.get_state = toolhead_status;
    toolhead->object.destroy = toolhead_destroy;

    axis = *config->axes;
    while (axis)
        axis = config->axes[++n_axis];

    toolhead->axes = calloc(n_axis, sizeof(*toolhead->axes));
    if (!toolhead->axes) {
        free((char *)toolhead->object.name);
        free(toolhead);
        return NULL;
    }

    toolhead->n_axes = n_axis;
    for (n_axis = 0; n_axis < toolhead->n_axes; n_axis++) {
        toolhead->axes[n_axis].type =
            kinematics_axis_type_from_char(*config->axes[n_axis]);
    }

    return toolhead;
}

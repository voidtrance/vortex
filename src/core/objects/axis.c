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
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <math.h>
#include <time.h>
#include "../debug.h"
#include "../common_defs.h"
#include "../events.h"
#include "axis.h"
#include "endstop.h"
#include "object_defs.h"
#include "stepper.h"
#include <utils.h>
#include <cache.h>
#include <random.h>

#define AXIS_NO_LENGTH (-1.0)

typedef struct {
    const char *name;
    core_object_t *obj;
    double position;
    bool move_complete;
    bool enabled;
} axis_motor_t;

typedef struct {
    float length;
    double travel_per_step;
    const char **steppers;
    const char endstop[64];
} axis_config_params_t;

typedef struct {
    core_object_t object;
    axis_motor_t *motors;
    size_t n_motors;
    const char *endstop_name;
    core_object_t *endstop;
    bool homed;
    bool endstop_is_max;
    float length;
    double travel_per_step;
    double position;
} axis_t;

typedef int (*command_func_t)(core_object_t *object, void *args);

static object_cache_t *axis_event_cache = NULL;

static void axis_event_handler(core_object_t *object, const char *name,
			       const core_object_event_type_t event,
			       void *data);

static void axis_reset(core_object_t *object) {
    axis_t *axis = (axis_t *)object;

    axis->homed = false;

    if (axis->length == AXIS_NO_LENGTH) {
      axis->homed = true;
      axis->position = 0.0;
    } else {
      axis->position = random_float_limit(0, axis->length);
    }
}

static int axis_init(core_object_t *object) {
    axis_t *axis = (axis_t *)object;
    endstop_status_t status;
    size_t i;

    for (i = 0; i < axis->n_motors; i++) {
	axis->motors[i].obj = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_STEPPER,
						 axis->motors[i].name);
	if (!axis->motors[i].obj)
	    return -ENODEV;

	axis->motors[i].move_complete = true;
    }

    if (axis->endstop_name) {
	axis->endstop = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_ENDSTOP,
					   axis->endstop_name);
	if (!axis->endstop)
	    return -ENODEV;

	axis->endstop->get_state(axis->endstop, &status);
	if (!strncmp(status.type, "max", 3))
	    axis->endstop_is_max = true;
	else
	    axis->endstop_is_max = false;
    }

    CORE_EVENT_REGISTER(axis, OBJECT_TYPE_ENDSTOP, OBJECT_EVENT_ENDSTOP_TRIGGER,
			axis->endstop_name, axis_event_handler);
    axis_reset(object);
    return 0;
}

static void axis_event_handler(core_object_t *object, const char *name,
                               const core_object_event_type_t event,
                               void *data) {
    endstop_trigger_event_data_t *event_data =
	(endstop_trigger_event_data_t *)data;
    axis_t *axis = (axis_t *)object;

    if (!axis->homed && event == OBJECT_EVENT_ENDSTOP_TRIGGER &&
	event_data->triggered)
	axis->homed = true;
}

static void axis_update(core_object_t *object, uint64_t ticks,
			uint64_t runtime) {
    axis_t *axis = (axis_t *)object;
    stepper_status_t stepper_status;
    double average_position = 0;
    size_t i;

    /* TODO: need to figure out how to limit the stepper
     * from going past the axis length. Some possibilities:
     *    - have the stepper query the endstop trigger status.
     *    - have the axis somehow set limits on the number of
     *      steps the stepper can perform.
     */

    for (i = 0; i < axis->n_motors; i++)
        axis->motors[i].obj->get_state(axis->motors[i].obj, &stepper_status);

    /*
     * Average out the axis position based on the position of
     * motor.
     */
    for (i = 0; i < axis->n_motors; i++) {
        average_position += (stepper_status.steps * axis->travel_per_step) -
                            axis->motors[i].position;
        axis->motors[i].position = stepper_status.steps * axis->travel_per_step;
    }

    axis->position += (average_position / axis->n_motors);

    log_debug(axis, "position: %.15f, homed: %u, command: %u",
	      axis->position, axis->homed);

    if (axis->length != AXIS_NO_LENGTH) {
	if (!axis->endstop_is_max && axis->position <= 0)
	    axis->position = 0;
	else if (axis->endstop_is_max && axis->position >= axis->length)
	    axis->position = axis->length;
    }
}

static void axis_status(core_object_t *object, void *status) {
    axis_t *axis = (axis_t *)object;
    axis_status_t *s = (axis_status_t *)status;
    size_t i;

    s->homed = axis->homed;
    s->length = axis->length;
    s->position = axis->position;
    s->travel_per_step = axis->travel_per_step;
    memset(s->motors, 0, sizeof(s->motors));
    for (i = 0; i < axis->n_motors; i++) {
        strncpy(s->motors[i], axis->motors[i].name, ARRAY_SIZE(s->motors[i]));
    }
}

static void axis_destroy(core_object_t *object) {
    axis_t *axis = (axis_t *)object;
    size_t i;

    core_object_destroy(object);
    object_cache_destroy(axis_event_cache);
    free((char *)axis->endstop_name);
    for (i = 0; i < axis->n_motors; i++)
	free((char *)axis->motors[i].name);
    free(axis->motors);
    free(axis);
}

axis_t *object_create(const char *name, void *config_ptr) {
    axis_t *axis;
    axis_config_params_t *config = (axis_config_params_t *)config_ptr;
    const char *stepper;
    size_t i = 0;

    if (object_cache_create(&axis_event_cache,
			    sizeof(axis_homed_event_data_t)))
	return NULL;

    axis = calloc(1, sizeof(*axis));
    if (!axis) {
	object_cache_destroy(axis_event_cache);
	return NULL;
    }

    axis->object.type = OBJECT_TYPE_AXIS;
    axis->object.name = strdup(name);
    axis->object.init = axis_init;
    axis->object.update = axis_update;
    axis->object.reset = axis_reset;
    axis->object.get_state = axis_status;
    axis->object.destroy = axis_destroy;
    if (config->endstop[0] != '\0')
	axis->endstop_name = strdup(config->endstop);

    /* First, we have to find out how many motors are
     * defined.
     */
    stepper = *config->steppers;
    while (stepper) {
	stepper = config->steppers[++i];
    }

    axis->motors = calloc(i, sizeof(*axis->motors));
    if (!axis->motors) {
	object_cache_destroy(axis_event_cache);
	free((char *)axis->endstop_name);
	free(axis);
	return NULL;
    }

    axis->n_motors = i;
    for (i = 0; i < axis->n_motors; i++)
	axis->motors[i].name = strdup(config->steppers[i]);

    axis->travel_per_step = config->travel_per_step;
    axis->length = config->length;
    axis->homed = false;

    return axis;
}

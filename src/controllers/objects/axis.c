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
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include "../common_defs.h"
#include "../events.h"
#include "object_defs.h"
#include "axis.h"
#include "stepper.h"
#include "endstop.h"

typedef struct {
    uint16_t length;
    float mm_per_step;
    const char stepper[64];
    const char endstop[64];
} axis_config_params_t;

typedef struct {
    core_object_t object;
    core_call_data_t *call_data;
    const char *motor_name;
    core_object_t *motor;
    const char *endstop_name;
    core_object_t *endstop;
    bool homed;
    bool endstop_is_max;
    float length;
    float mm_per_step;
    float position;
} axis_t;

static int axis_init(core_object_t *object) {
    axis_t *axis = (axis_t *)object;
    endstop_status_t status;

    axis->motor = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_STEPPER,
				     axis->motor_name);
    if (!axis->motor)
	return -1;

    if (axis->endstop_name) {
	axis->endstop = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_ENDSTOP,
					   axis->endstop_name);
	if (!axis->endstop)
	    return -1;
    }

    axis->endstop->get_state(axis->endstop, &status);
    if (strncmp(status.type, "max", 3))
	axis->endstop_is_max = true;

    return 0;
}

static void axis_update(core_object_t *object, uint64_t ticks,
			uint64_t runtime) {
    axis_t *axis = (axis_t *)object;
    stepper_status_t stepper_status;

    /* TODO: need to figure out how to limit the stepper
     * from going past the axis length. Some possibilities:
     *    - have the stepper query the endstop trigger status.
     *    - have the axis somehow set limits on the number of
     *      steps the stepper can perform.
     */
    axis->motor->get_state(axis->motor, &stepper_status);
    axis->position = stepper_status.steps * axis->mm_per_step;
    if (!axis->endstop_is_max && axis->position <= 0) {
	axis->homed = true;
	axis->position = 0;
    } else if (axis->endstop_is_max && axis->position >= axis->length) {
	axis->homed = true;
	axis->position = axis->length;
    }
}

static void axis_status(core_object_t *object, void *status) {
    axis_t *axis = (axis_t *)object;
    axis_status_t *s = (axis_status_t *)status;

    s->homed = axis->homed;
    s->length = axis->length;
    s->position = axis->position;
}

static void axis_destroy(core_object_t *object) {
    axis_t *axis = (axis_t *)object;

    core_object_destroy(object);
    free((char *)axis->endstop_name);
    free((char *)axis->motor_name);
    free(axis);
}

axis_t *object_create(const char *name, void *config_ptr) {
    axis_t *axis;
    axis_config_params_t *config = (axis_config_params_t *)config_ptr;

    axis = calloc(1, sizeof(*axis));
    if (!axis)
	return NULL;

    axis->object.type = OBJECT_TYPE_AXIS;
    axis->object.name = strdup(name);
    axis->object.init = axis_init;
    axis->object.update = axis_update;
    axis->object.get_state = axis_status;
    axis->object.destroy = axis_destroy;
    axis->endstop_name = strdup(config->endstop);
    axis->motor_name = strdup(config->stepper);
    axis->mm_per_step = config->mm_per_step;

    return axis;
}

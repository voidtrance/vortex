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
#include <errno.h>
#include <math.h>
#include <time.h>
#define CORE_UPDATE_RATE_LIMIT 40000
#include "../debug.h"
#include "../common_defs.h"
#include "../events.h"
#include "axis.h"
#include "endstop.h"
#include "object_defs.h"
#include "stepper.h"

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
    uint64_t command_id;
    uint16_t axis_command_id;
    bool waiting_to_move;
    bool endstop_is_max;
    float length;
    float mm_per_step;
    float position;
} axis_t;

typedef int (*command_func_t)(core_object_t *object, void *args);

static int axis_move(core_object_t *object, void *args);
static int axis_home(core_object_t *object, void *args);
static void axis_event_handler(core_object_t *object, const char *name,
			       const core_object_event_type_t type, void *args);

static const command_func_t command_handlers[] = {
    [AXIS_COMMAND_MOVE] = axis_move,
    [AXIS_COMMAND_HOME] = axis_home,
};

static int axis_init(core_object_t *object) {
    axis_t *axis = (axis_t *)object;
    endstop_status_t status;

    axis->motor = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_STEPPER,
				     axis->motor_name);
    if (!axis->motor)
	return -ENODEV;

    if (axis->endstop_name) {
	axis->endstop = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_ENDSTOP,
					   axis->endstop_name);
	if (!axis->endstop)
	    return -ENODEV;
    }

    axis->endstop->get_state(axis->endstop, &status);
    if (strncmp(status.type, "max", 3))
	axis->endstop_is_max = true;

    if (CORE_EVENT_REGISTER(axis, OBJECT_TYPE_STEPPER,
			    OBJECT_EVENT_STEPPER_MOVE_COMPLETE,
			    axis->motor_name, axis_event_handler))
	return -EINVAL;

    axis->axis_command_id = AXIS_COMMAND_MAX;
    return 0;
}

static void axis_stepper_command_handler(uint64_t cmd_id, int result,
					 void *arg) {
    axis_t *axis = (axis_t *)arg;
    axis->axis_command_id = AXIS_COMMAND_MAX;
    axis->command_id = 0;
}

static int axis_move(core_object_t *object, void *args) {
    axis_t *axis = (axis_t *)object;
    axis_move_command_opts_t *opts = (axis_move_command_opts_t *)args;
    struct stepper_move_args *stepper_args;

    if (opts->distance == 0)
	return 0;

    stepper_args = calloc(1, sizeof(*stepper_args));
    if (!stepper_args)
        return -ENOMEM;

    stepper_args->steps = fabs(opts->distance) / axis->mm_per_step;
    log_debug(axis, "move: distance: %f, steps: %u",
	      opts->distance, stepper_args->steps);
    stepper_args->direction = opts->distance < 0 ? MOVE_DIR_BACK : MOVE_DIR_FWD;

    /* We don't care for the command ID.  */
    (void)CORE_CMD_SUBMIT(axis, axis->motor, STEPPER_COMMAND_MOVE,
			  axis_stepper_command_handler, stepper_args);
    return 0;
}

static void axis_event_handler(core_object_t *object, const char *name,
			       const core_object_event_type_t type,
			       void *args) {
    axis_t *axis = (axis_t *)object;

    if (axis->homed)
	return;

    if (strncmp(name, axis->motor_name, strlen(name)) ||
	type != OBJECT_EVENT_STEPPER_MOVE_COMPLETE)
	return;

    axis->waiting_to_move = false;
}

static int axis_home(core_object_t *object, void *args) {
    axis_t *axis = (axis_t *)object;

    log_debug(axis, "homing axis: %u, %u, %f, %f", axis->homed,
	      axis->waiting_to_move, axis->position, axis->length);
    return 0;
}

static int axis_exec_command(core_object_t *object,
			     core_object_command_t *cmd) {
    axis_t *axis = (axis_t *)object;

    if (axis->command_id)
	return -EBUSY;

    axis->command_id = cmd->command_id;
    axis->axis_command_id = cmd->object_cmd_id;
    return command_handlers[cmd->object_cmd_id](object, cmd->args);
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
    if (!axis->endstop_is_max && axis->position <= 0)
	axis->position = 0;
    else if (axis->endstop_is_max && axis->position >= axis->length)
	axis->position = axis->length;

    log_debug(axis, "position: %f", axis->position);

    switch (axis->axis_command_id) {
    case AXIS_COMMAND_HOME:
	if (!axis->homed) {
            if ((axis->endstop_is_max && axis->position == axis->length) ||
                (axis->position == 0)) {
              axis->homed = true;
              axis->axis_command_id = AXIS_COMMAND_MAX;
	      CORE_CMD_COMPLETE(axis, axis->command_id, 0);
	      axis->command_id = 0;
            } else {
		axis_move_command_opts_t opts;

		if (!axis->waiting_to_move) {
		    if (axis->endstop_is_max)
			opts.distance = (axis->length - axis->position);
		    else
			opts.distance = -axis->position;

		    log_debug(axis, "distance: %f", opts.distance);
		    axis->waiting_to_move = true;
		    axis_move(object, &opts);
		}
            }
        }
    default:
        break;
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
    axis->object.exec_command = axis_exec_command;
    axis->object.get_state = axis_status;
    axis->object.destroy = axis_destroy;
    axis->endstop_name = strdup(config->endstop);
    axis->motor_name = strdup(config->stepper);
    axis->mm_per_step = config->mm_per_step;

    return axis;
}

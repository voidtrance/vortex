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
    uint64_t id;
    uint16_t cmd_id;
} axis_stepper_command_info_t;

typedef struct {
    core_object_t object;
    axis_motor_t *motors;
    size_t n_motors;
    const char *endstop_name;
    core_object_t *endstop;
    axis_stepper_command_info_t *comps;
    bool homed;
    uint64_t command_id;
    uint16_t axis_command_id;
    bool waiting_to_move;
    bool endstop_is_max;
    float length;
    double travel_per_step;
    double position;
    double target_position;
} axis_t;

typedef int (*command_func_t)(core_object_t *object, void *args);

static object_cache_t *stepper_args_cache = NULL;
static object_cache_t *axis_event_cache = NULL;

static int axis_move(core_object_t *object, void *args);
static int axis_home(core_object_t *object, void *args);
static void axis_event_handler(core_object_t *object, const char *name,
			       const core_object_event_type_t type, void *args);

static const command_func_t command_handlers[] = {
    [AXIS_COMMAND_MOVE] = axis_move,
    [AXIS_COMMAND_HOME] = axis_home,
};

static void axis_reset(core_object_t *object) {
    axis_t *axis = (axis_t *)object;

    axis->axis_command_id = AXIS_COMMAND_MAX;
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

        if (CORE_EVENT_REGISTER(axis, OBJECT_TYPE_STEPPER,
                                OBJECT_EVENT_STEPPER_MOVE_COMPLETE,
                                axis->motors[i].name, axis_event_handler))
            return -EINVAL;
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

    axis_reset(object);
    return 0;
}

static void axis_stepper_command_handler(uint64_t cmd_id, int result,
					 void *arg) {
    axis_t *axis = (axis_t *)arg;
    axis_stepper_command_info_t *info = NULL;
    size_t i;

    log_debug(axis, "Command %lu complete: %d", cmd_id, result);
    for (i = 0; i < axis->n_motors; i++) {
	info = &axis->comps[i];
	log_debug(axis, "cmd: %lu", info->id);
	if (info->id == cmd_id)
	    break;
    }

    if (i == axis->n_motors)
	return;

    log_debug(axis, "cmd: %lu, cmd_id: %u", info->id, info->cmd_id);
    switch (info->cmd_id) {
    case STEPPER_COMMAND_ENABLE:
	axis->motors[i].enabled = true;
	break;
    case STEPPER_COMMAND_MOVE:
	if (axis->position == axis->target_position)
	    axis->axis_command_id = AXIS_COMMAND_MAX;
    default:
	break;
    }

    info->id = 0;
    info->cmd_id = 0;
}

static void axis_motor_move(axis_t *axis, size_t motor_idx,
                           struct stepper_move_args *args) {
    axis_motor_t *motor = &axis->motors[motor_idx];
    axis->comps[motor_idx].cmd_id = STEPPER_COMMAND_MOVE;
    axis->comps[motor_idx].id = CORE_CMD_SUBMIT(axis, motor->obj,
						STEPPER_COMMAND_MOVE,
						axis_stepper_command_handler,
						args);
}

static int axis_move(core_object_t *object, void *args) {
    axis_t *axis = (axis_t *)object;
    axis_move_command_opts_t *opts = (axis_move_command_opts_t *)args;
    struct stepper_move_args *stepper_args;
    stepper_status_t motor_status;
    double distance;
    size_t i;

    if (!axis->homed) {
	log_error(axis, "Axis '%s' is not homed.", axis->object.name);
	return -EINVAL;
    }

    if (axis->length != AXIS_NO_LENGTH && (opts->position < 0 ||
					   opts->position > axis->length))
	return -EINVAL;

    axis->target_position = opts->position;
    distance = axis->target_position - axis->position;

    if (axis->length == AXIS_NO_LENGTH) {
	/* Implicitly enable motors for infinite axes */
	for (i = 0; i < axis->n_motors; i++) {
            struct stepper_enable_args *args = malloc(sizeof(*args));

            if (!args)
              return -ENOMEM;

            args->enable = true;
	    axis->comps[i].cmd_id = STEPPER_COMMAND_ENABLE;
	    axis->comps[i].id = CORE_CMD_SUBMIT(axis, axis->motors[i].obj,
						STEPPER_COMMAND_ENABLE,
						axis_stepper_command_handler,
						args);
        }
    } else {
	/* Check that all motors are enabled. */
	for (i = 0; i < axis->n_motors; i++) {
	    axis->motors[i].obj->get_state(axis->motors[i].obj, &motor_status);
	    if (!motor_status.enabled) {
		log_error(axis, "Axis motor '%s' is not enabled.",
			  axis->motors[i].name);
		return -1;
	    }
	}
    }

    for (i = 0; i < axis->n_motors; i++) {
        stepper_args = calloc(1, sizeof(*stepper_args));
        if (!stepper_args)
            return -ENOMEM;

        stepper_args->steps = fabs(distance) / axis->travel_per_step;
        log_debug(axis, "move: distance: %f, steps: %u", distance,
                  stepper_args->steps);
        stepper_args->direction = distance < 0 ? MOVE_DIR_BACK : MOVE_DIR_FWD;

        axis_motor_move(axis, i, stepper_args);
    }

    return 0;
}

static void axis_event_handler(core_object_t *object, const char *name,
			       const core_object_event_type_t type,
			       void *args) {
    axis_t *axis = (axis_t *)object;
    size_t i;

    if (axis->homed)
	return;

    for (i = 0; i < axis->n_motors; i++) {
	if (strncmp(name, axis->motors[i].name, strlen(name)) ||
	    type != OBJECT_EVENT_STEPPER_MOVE_COMPLETE)
	    continue;
	axis->motors[i].move_complete = true;
    }
}

static int axis_home(core_object_t *object, void *args) {
    axis_t *axis = (axis_t *)object;
    struct stepper_enable_args *enable_args;
    size_t i;

    log_debug(axis, "homing axis: %u, %u, %f, %f", axis->homed,
	      axis->waiting_to_move, axis->position, axis->length);
    if (axis->length != AXIS_NO_LENGTH)
	axis->target_position = axis->endstop_is_max ? axis->length : 0;

    for (i = 0; i < axis->n_motors; i++) {
	enable_args = malloc(sizeof(*enable_args));
        enable_args->enable = true;
	axis->comps[i].cmd_id = STEPPER_COMMAND_ENABLE;
	axis->comps[i].id = CORE_CMD_SUBMIT(axis,
					    axis->motors[i].obj,
					    STEPPER_COMMAND_ENABLE,
					    axis_stepper_command_handler,
					    enable_args);
    }

    return 0;
}

static int axis_exec_command(core_object_t *object,
			     core_object_command_t *cmd) {
    axis_t *axis = (axis_t *)object;
    int ret;

    if (axis->command_id)
	return -EBUSY;

    axis->command_id = cmd->command_id;
    axis->axis_command_id = cmd->object_cmd_id;
    ret = command_handlers[cmd->object_cmd_id](object, cmd->args);
    if (ret != 0)
	axis->command_id = 0;
    return ret;
}

static void axis_update(core_object_t *object, uint64_t ticks,
			uint64_t runtime) {
    axis_t *axis = (axis_t *)object;
    stepper_status_t stepper_status;
    double average_position = 0;
    size_t i;

    if (!axis->homed && axis->axis_command_id != AXIS_COMMAND_HOME)
	return;

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

    log_debug(axis, "axis %s position: %.20f, homed: %u, command: %u",
	      axis->object.name, axis->position, axis->homed,
	      axis->axis_command_id);
    if (axis->length != AXIS_NO_LENGTH) {
	if (!axis->endstop_is_max && axis->position <= 0)
	    axis->position = 0;
	else if (axis->endstop_is_max && axis->position >= axis->length)
	    axis->position = axis->length;
    }

    switch (axis->axis_command_id) {
    case AXIS_COMMAND_HOME:
	if (!axis->homed) {
            if ((axis->endstop_is_max && axis->position == axis->length) ||
                (!axis->endstop_is_max && axis->position == 0)) {
		axis_homed_event_data_t *data;

		axis->homed = true;
		axis->axis_command_id = AXIS_COMMAND_MAX;
		CORE_CMD_COMPLETE(axis, axis->command_id, 0);
		axis->command_id = 0;

		data = object_cache_alloc(axis_event_cache);
		if (data) {
		    data->axis = axis->object.name;
		    CORE_EVENT_SUBMIT(axis, OBJECT_EVENT_AXIS_HOMED,
				      core_object_to_id((core_object_t *)axis),
				      data);
		}
            } else {
		for (i = 0; i < axis->n_motors; i++) {
                  struct stepper_move_args *args;

		  if (!axis->motors[i].enabled)
		      continue;

		  args = object_cache_alloc(stepper_args_cache);
		  if (!args)
		      continue;

                  if (axis->motors[i].move_complete) {
		      double distance;

		      if (axis->endstop_is_max) {
			  distance = axis->length - axis->position;
			  args->direction = MOVE_DIR_FWD;
		      } else {
			  distance = axis->position;
			  args->direction = MOVE_DIR_BACK;
		      }

		      args->steps = (uint32_t)(distance / axis->travel_per_step);
		      if (!args->steps) {
			  axis->position += axis->endstop_is_max ? distance :
			      -distance;
			  object_cache_free(args);
			  break;
		      }

                      axis->motors[i].move_complete = false;
		      axis_motor_move(axis, i, args);
                  }
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
    object_cache_destroy(stepper_args_cache);
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

    if (object_cache_create(&stepper_args_cache,
			    sizeof(struct stepper_move_args)))
	    return NULL;

    if (object_cache_create(&axis_event_cache,
			    sizeof(axis_homed_event_data_t))) {
	object_cache_destroy(stepper_args_cache);
	return NULL;
    }

    axis = calloc(1, sizeof(*axis));
    if (!axis)
	return NULL;

    axis->object.type = OBJECT_TYPE_AXIS;
    axis->object.name = strdup(name);
    axis->object.init = axis_init;
    axis->object.update = axis_update;
    axis->object.reset = axis_reset;
    axis->object.exec_command = axis_exec_command;
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
	free((char *)axis->endstop_name);
	free(axis);
	return NULL;
    }

    axis->n_motors = i;
    for (i = 0; i < axis->n_motors; i++)
	axis->motors[i].name = strdup(config->steppers[i]);

    axis->comps = calloc(axis->n_motors, sizeof(*axis->comps));
    if (!axis->comps) {
	for (i = 0; i < axis->n_motors; i++)
	    free((char *)axis->motors[i].name);
	free(axis->motors);
	free((char *)axis->endstop_name);
	free(axis);
	return NULL;
    }

    axis->travel_per_step = config->travel_per_step;
    axis->length = config->length;
    axis->homed = false;

    return axis;
}

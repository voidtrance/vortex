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
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "../debug.h"
#include "object_defs.h"
#include "../common_defs.h"
#include "../utils.h"
#include "stepper.h"

typedef struct {
    uint32_t steps_per_rotation;
    uint32_t microsteps;
    const char clock_speed[64];
    const char driver[16];
} stepper_config_params_t;

typedef struct {
    core_object_t object;
    core_object_command_t *current_cmd;
    uint16_t steps_per_rotation;
    uint8_t microsteps;
    uint64_t last_timestep;
    float current_step;
    float steps;
    float rps;
    float spns;
    stepper_move_dir_t dir;
    bool enabled;
} stepper_t;

void stepper_update(core_object_t *object, uint64_t ticks, uint64_t timestep);
int stepper_exec(core_object_t *object, core_object_command_t *cmd);
int stepper_enable(core_object_t *object, void *args);
int stepper_move(core_object_t *object, void *args);
void stepper_status(core_object_t *object, void *status);
void stepper_destroy(core_object_t *object);

typedef int (*command_func_t)(core_object_t *object, void *args);

static const command_func_t command_handlers[] = {
    [STEPPER_COMMAND_ENABLE] = stepper_enable,
    [STEPPER_COMMAND_MOVE] = stepper_move,
};

stepper_t *object_create(const char *name, void *config_ptr) {
    stepper_t *stepper;
    stepper_config_params_t *config = (stepper_config_params_t *)config_ptr;
    uint32_t clock_speed = 0;

    stepper = calloc(1, sizeof(*stepper));
    if (!stepper)
	return NULL;

    stepper->object.type = OBJECT_TYPE_STEPPER;
    stepper->object.update = stepper_update;
    stepper->object.get_state = stepper_status;
    stepper->object.destroy = stepper_destroy;
    stepper->object.exec_command = stepper_exec;
    stepper->object.name = strdup(name);
    stepper->steps_per_rotation = config->steps_per_rotation;
    stepper->microsteps = config->microsteps;

    clock_speed = str_to_hertz(config->clock_speed);

    // TMC2209: RPS = (VACTUAL[2209] * fCLK[Hz] / 2^24) / microsteps / spr
    // TMC5560: RPS = (VACTUAL[5560] *(fCLK[Hz]/2 / 2^23)) / microsteps / spr
    stepper->rps = (float)clock_speed / stepper->microsteps /
	stepper->steps_per_rotation;
    stepper->spns = (stepper->steps_per_rotation * stepper->rps) /
	SEC_TO_NSEC(1);

    return stepper;
}

int stepper_enable(core_object_t *object, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_enable_args *opts = (struct stepper_enable_args *)args;

    stepper->enabled = !!opts->enable;
    CORE_CMD_COMPLETE(stepper, stepper->current_cmd->command_id, 0);
    stepper->current_cmd = NULL;
    return 0;
}

int stepper_move(core_object_t *object, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_move_args *opts = (struct stepper_move_args *)args;

    if (!stepper->enabled) {
	stepper->current_cmd = NULL;
	return -1;
    }

    stepper->dir = opts->direction;
    stepper->steps = opts->steps;
    log_debug(stepper, "Stepper %s moving %f steps in %u",
	      stepper->object.name, stepper->steps, stepper->dir);
    return 0;
}

int stepper_exec(core_object_t *object, core_object_command_t *cmd) {
    stepper_t *stepper = (stepper_t *)object;
    int ret;

    if (stepper->current_cmd)
	return -1;

    stepper->current_cmd = cmd;
    ret = command_handlers[cmd->object_cmd_id](object, cmd->args);
    return ret;
}

void stepper_status(core_object_t *object, void *status) {
    stepper_status_t *s = (stepper_status_t *)status;
    stepper_t *stepper = (stepper_t *)object;

    s->enabled = stepper->enabled;
    s->steps = stepper->current_step;
    s->spr = stepper->steps_per_rotation;
    s->microsteps = stepper->microsteps;
}

void stepper_update(core_object_t *object, uint64_t ticks, uint64_t timestep) {
    stepper_t *stepper = (stepper_t *)object;
    uint64_t delta  = timestep - stepper->last_timestep;

    if (stepper->steps > 0.0) {
	float steps = stepper->spns * delta;

	if (steps > stepper->steps)
	    steps = stepper->steps;
	if (stepper->dir == MOVE_DIR_BACK)
	    stepper->current_step -= steps;
	else
	    stepper->current_step += steps;
	stepper->steps -= steps;
    } else if (stepper->current_cmd) {
	stepper_move_comeplete_event_data_t *data;

	CORE_CMD_COMPLETE(stepper, stepper->current_cmd->command_id, 0);
        stepper->current_cmd = NULL;
        stepper->steps = 0.0;

        data = malloc(sizeof(*data));
	if (data) {
	    data->steps = stepper->current_step;
	    CORE_EVENT_SUBMIT(stepper, OBJECT_EVENT_STEPPER_MOVE_COMPLETE,
			      core_object_to_id((core_object_t *)stepper),
			      data);
	}
    }

    stepper->last_timestep = timestep;
}

void stepper_destroy(core_object_t *object) {
    stepper_t *stepper = (stepper_t *)object;

    core_object_destroy(object);
    free(stepper);
}

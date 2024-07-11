#define PY_SSIZE_T_CLEAN
#include "common_defs.h"
#include "../utils.h"
#include <Python.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

typedef enum { MOVE_DIR_NONE, MOVE_DIR_FWD, MOVE_DIR_BACK } stepper_move_dir_t;

enum {
    STEPPER_COMMAND_ENABLE,
    STEPPER_COMMAND_MOVE,
    STEPPER_COMMAND_MAX,
};

typedef struct {
    uint32_t steps_per_rotation;
    uint32_t microsteps;
    const char clock_speed[64];
    const char driver[16];
} stepper_config_params_t;

typedef struct {
    core_object_t object;
    complete_cb_t complete_cb;
    void *complete_data;
    core_object_command_t *current_cmd;
    uint64_t last_timestep;
    float current_step;
    float steps;
    float rps;
    float spns;
    stepper_move_dir_t dir;
    bool enabled;
} Stepper_t;

struct stepper_enable_args {
    int enable;
};

struct stepper_move_args {
    stepper_move_dir_t direction;
    uint32_t steps;
};

struct stepper_status {
    uint8_t enabled;
    uint64_t steps;
};

void stepper_update(core_object_t *object, uint64_t timestep);
int stepper_exec(core_object_t *object, core_object_command_t *cmd);
int stepper_enable(core_object_t *object, void *args);
int stepper_move(core_object_t *object, void *args);
void *stepper_status(core_object_t *object);
void stepper_destroy(core_object_t *object);

typedef int (*command_func_t)(core_object_t *object, void *args);

static const command_func_t command_handlers[] = {
    [STEPPER_COMMAND_ENABLE] = stepper_enable,
    [STEPPER_COMMAND_MOVE] = stepper_move,
};

Stepper_t *object_create(const char *name, void *config_ptr,
                         complete_cb_t complete, void *complete_data) {
    Stepper_t *stepper;
    stepper_config_params_t *config = (stepper_config_params_t *)config_ptr;
    uint32_t clock_speed = 0;

    stepper = calloc(1, sizeof(*stepper));
    if (!stepper)
	return NULL;

    stepper->object.type = OBJECT_TYPE_STEPPER;
    stepper->object.update = stepper_update;
    stepper->object.destroy = stepper_destroy;
    stepper->object.exec_command = stepper_exec;
    stepper->complete_cb = complete;
    stepper->complete_data = complete_data;

    clock_speed = str_to_hertz(config->clock_speed);
    printf("Stepper: %u, %u, %u\n", config->steps_per_rotation,
	   config->microsteps, clock_speed);

    // TMC2209: RPS = (VACTUAL[2209] * fCLK[Hz] / 2^24) / microsteps / spr
    // TMC5560: RPS = (VACTUAL[5560] *(fCLK[Hz]/2 / 2^23)) / microsteps / spr
    stepper->rps = (float)clock_speed / config->microsteps /
	config->steps_per_rotation;
    stepper->spns = stepper->rps / SEC_TO_NSEC(1);

    return stepper;
}

int stepper_enable(core_object_t *object, void *args) {
    Stepper_t *stepper = (Stepper_t *)object;
    struct stepper_enable_args *opts = (struct stepper_enable_args *)args;

    stepper->enabled = !!opts->enable;
    stepper->complete_cb(stepper->current_cmd->command_id, 0,
			 stepper->complete_data);
    stepper->current_cmd = NULL;
    return 0;
}

int stepper_move(core_object_t *object, void *args) {
    Stepper_t *stepper = (Stepper_t *)object;
    struct stepper_move_args *opts = (struct stepper_move_args *)args;

    if (!stepper->enabled) {
	stepper->current_cmd = NULL;
	return -1;
    }

    printf("opt: %u %u\n", opts->direction, opts->steps);
    stepper->dir = opts->direction;
    stepper->steps = opts->steps;
    return 0;
}

int stepper_exec(core_object_t *object, core_object_command_t *cmd) {
    Stepper_t *stepper = (Stepper_t *)object;
    int ret;

    if (stepper->current_cmd)
	return -1;

    stepper->current_cmd = cmd;
    ret = command_handlers[cmd->object_cmd_id](object, cmd->args);
    return ret;
}

void stepper_update(core_object_t *object, uint64_t timestep) {
    Stepper_t *stepper = (Stepper_t *)object;
    uint64_t delta  = timestep - stepper->last_timestep;

    //printf("delta: %lu, %f\n", delta, stepper->spns);
    if (stepper->steps > 0.0) {
	float steps = stepper->spns * delta;
	if (stepper->dir == MOVE_DIR_BACK)
	    stepper->current_step -= steps;
	else
	    stepper->current_step += steps;
	stepper->steps -= steps;
    } else if (stepper->current_cmd) {
	stepper->complete_cb(stepper->current_cmd->command_id, 0,
			     stepper->complete_data);
	stepper->current_cmd = NULL;
	stepper->steps = 0.0;
    }
    //printf("current steps: %lu\n", stepper->current_step);

    stepper->last_timestep = timestep;
}

void stepper_destroy(core_object_t *object) {
    Stepper_t *stepper = (Stepper_t *)object;
    free(stepper);
}

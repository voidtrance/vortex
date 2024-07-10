#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include "common_defs.h"
#include "cmd_opts_module.h"
#include "utils.h"

typedef enum {
	MOVE_DIR_NONE,
    MOVE_DIR_FWD,
    MOVE_DIR_BACK
} stepper_move_dir_t;

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
	CoreObject_t object;
	bool enabled;
	uint64_t steps;
	stepper_move_dir_t dir;
	uint64_t current_step;
	float rps;
	uint32_t spns;
} Stepper_t;

struct stepper_enable_args {
	int enable;
};

struct stepper_move_args {
	stepper_move_dir_t direction;
	uint32_t steps;
};

void stepper_update(CoreObject_t *object, uint64_t timestep);
int stepper_enable(CoreObject_t *object, void *args);
int stepper_move(CoreObject_t *object, void *args);
void stepper_destroy(CoreObject_t *object);

typedef int (*command_func_t)(CoreObject_t *object, void *args);
static const command_func_t command_handlers[] = {
	[STEPPER_COMMAND_ENABLE] = stepper_enable,
	[STEPPER_COMMAND_MOVE] = stepper_move,
};

Stepper_t *object_create(const char *name, void *config_ptr)
{
	Stepper_t *stepper;
	stepper_config_params_t *config = (stepper_config_params_t *)config_ptr;
	uint32_t clock_speed = 0;

	stepper = calloc(1, sizeof(*stepper));
	if (!stepper)
		return NULL;

	stepper->object.type = OBJECT_TYPE_STEPPER;
	stepper->object.update = stepper_update;
	stepper->object.destroy = stepper_destroy;

	clock_speed = str_to_hertz(config->clock_speed);
	printf("Stepper: %u, %u, %u\n", config->steps_per_rotation,
		   config->microsteps, clock_speed);

	// TMC2209: RPS = (VACTUAL[2209] * fCLK[Hz] / 2^24) / microsteps / spr
	// TMC5560: RPS = (VACTUAL[5560] *(fCLK[Hz]/2 / 2^23)) / microsteps / spr
	//stepper->rps = (float)clock_speed / microsteps / steps_per_rotation;

	return stepper;
}

int stepper_enable(CoreObject_t *object, void *args)
{
	Stepper_t *stepper = (Stepper_t *)object;
	struct stepper_enable_args *opts = (struct stepper_enable_args *)args;

	stepper->enabled = !!opts->enable;
	return 0;
}

int stepper_move(CoreObject_t *object, void *args)
{
	Stepper_t *stepper = (Stepper_t *)object;
	struct stepper_move_args *opts = (struct stepper_move_args *)args;

	stepper->dir = opts->direction;
	stepper->steps = opts->steps;
	return 0;
}

void stepper_update(CoreObject_t *object, uint64_t timestep)
{
	Stepper_t *stepper = (Stepper_t *)object;
}

void stepper_destroy(CoreObject_t *object)
{
	Stepper_t *stepper = (Stepper_t *)object;
	free(stepper);
}

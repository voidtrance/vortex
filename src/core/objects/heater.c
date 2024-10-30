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
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "object_defs.h"
#include "../common_defs.h"
#include "thermistor.h"
#include <utils.h>
#include "heater.h"
#include <cache.h>

#define AMBIENT_TEMP 25.0
#define MAX_RAMP_UP_DURATION 120
#define MAX_RAMP_DOWN_DURATION 240

typedef struct {
    uint16_t power;
    char pin[8];
    float max_temp;
} heater_config_params_t;

typedef struct {
    float current;
    float base;
    float set;
    float target;
    float max;
    uint64_t position;
    uint64_t duration;
    uint64_t max_ramp_duration;
} temp_data_t;

typedef struct {
    core_object_t object;
    core_object_command_t command;
    uint64_t timestep;
    temp_data_t temp_data;
    char pin[8];
} heater_t;

static object_cache_t *heater_event_cache = NULL;

static void heater_update(core_object_t *object, uint64_t ticks,
			  uint64_t timestamp);
static int heater_set_temp(core_object_t *object, core_object_command_t *cmd);
static void heater_status(core_object_t *object, void *status);
static void heater_reset(core_object_t *object);
static void heater_destroy(core_object_t *object);

heater_t *object_create(const char *name, void *config_ptr) {
    heater_t *heater;
    heater_config_params_t *config = (heater_config_params_t *)config_ptr;

    heater = calloc(1, sizeof(*heater));
    if (!heater)
	return NULL;

    heater->object.type = OBJECT_TYPE_HEATER;
    heater->object.update = heater_update;
    heater->object.reset = heater_reset;
    heater->object.destroy = heater_destroy;
    heater->object.exec_command = heater_set_temp;
    heater->object.get_state = heater_status;
    heater->object.name = strdup(name);
    heater->temp_data.position = 0;
    heater->temp_data.max_ramp_duration =
	SEC_TO_NSEC(MAX_RAMP_UP_DURATION * 100 / config->power);
    heater->temp_data.max = config->max_temp;
    strncpy(heater->pin, config->pin, sizeof(heater->pin));

    if (object_cache_create(&heater_event_cache,
			    sizeof(heater_temp_reached_event_data_t))) {
	core_object_destroy(&heater->object);
	free(heater);
	return NULL;
    }

    heater_reset((core_object_t *)heater);
    return heater;
}

static void heater_reset(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    heater->temp_data.current = AMBIENT_TEMP;
    heater->temp_data.base = heater->temp_data.current;
    heater->temp_data.target = AMBIENT_TEMP;
    heater->temp_data.position = 0;
}

static int heater_set_temp(core_object_t *object, core_object_command_t *cmd) {
    heater_t *heater = (heater_t *)object;
    struct heater_set_temperature_args *args;
    float ratio;

    if (cmd->object_cmd_id != HEATER_COMMAND_SET_TEMP)
	return -1;

    args = (struct heater_set_temperature_args *)cmd->args;
    if (args->temperature < 0 || args->temperature > heater->temp_data.max)
	return -1;

    // If a command is still running, immediately complete it.
    if (heater->command.command_id)
      CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);

    heater->command = *cmd;
    heater->temp_data.position = 0;
    heater->temp_data.base = heater->temp_data.current;
    heater->temp_data.target = max(args->temperature, AMBIENT_TEMP);

    if (heater->temp_data.target == heater->temp_data.current) {
	CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);
	return 0;
    }

    /* Ramping up duration is a percentage of the max ramp up
     * duration (which is a function of the heater's power).
     *
     * Ramping down is based on a static duration. This should
     * better emulate real-world temperature drops.
     *
     * Both ramp up and down final durations depend on the ratio
     * of the target temp to the max heater temp.
     */
    if (heater->temp_data.target < heater->temp_data.base)
	heater->temp_data.duration = SEC_TO_NSEC(MAX_RAMP_DOWN_DURATION);
    else
	heater->temp_data.duration = heater->temp_data.max_ramp_duration;

    ratio = (heater->temp_data.max - heater->temp_data.current) /
	heater->temp_data.max;
    heater->temp_data.duration *= ratio;

    log_debug(heater, "base: %.15f, target: %.15f, temp: %.15f",
	      heater->temp_data.base, heater->temp_data.target,
	      heater->temp_data.current);
    return 0;
}

static void heater_status(core_object_t *object, void *status) {
    heater_status_t *s = (heater_status_t *)status;
    heater_t *heater = (heater_t *)object;

    s->temperature = heater->temp_data.current;
    s->max_temp = heater->temp_data.max;
    strncpy(s->pin, heater->pin, sizeof(s->pin));
}

static float sinusoidal_inout(float value) {
    return -0.5 * (cosf(M_PI * value) - 1);
}

static void interpolate(temp_data_t *data, uint64_t time_delta) {
    float step_val;

    if (data->position + time_delta < data->duration)
	data->position += time_delta;
    else
	data->position = data->duration;
    step_val = (float)data->position / data->duration;
    if (data->base <= data->target) {
	data->current = (data->base + (data->target - data->base) *
			 sinusoidal_inout(step_val));
    } else {
	data->current = (data->base - (data->base - data->target) *
			 sinusoidal_inout(step_val));
    }

    data->current = roundf(data->current * 1000) / 1000;
}

static void heater_update(core_object_t *object, uint64_t ticks,
			  uint64_t timestep) {
    heater_t *heater = (heater_t *)object;
    uint64_t time_delta = timestep - heater->timestep;
    heater_temp_reached_event_data_t *data;

    heater->timestep = timestep;
    if (heater->temp_data.current == heater->temp_data.target)
       return;

    /*
     * Use interpolation function to approximate temperature
     * ramp.
     */
    interpolate(&heater->temp_data, time_delta);

    log_debug(heater, "heater %s temp: %f", heater->object.name,
	      heater->temp_data.current);
    if (heater->temp_data.current != heater->temp_data.target)
	return;

    CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);
    heater->command.command_id = 0;
    heater->command.object_cmd_id = HEATER_COMMAND_MAX;

    data = object_cache_alloc(heater_event_cache);
    if (data) {
        data->temp = heater->temp_data.current;
        CORE_EVENT_SUBMIT(heater, OBJECT_EVENT_HEATER_TEMP_REACHED, data);
    }
}

static void heater_destroy(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    core_object_destroy(object);
    object_cache_destroy(heater_event_cache);
    free(heater);
}

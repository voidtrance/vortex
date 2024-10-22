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
    float max_temp;
} heater_config_params_t;

typedef struct {
    core_object_t object;
    core_object_command_t command;
    uint64_t timestep;
    float set_temp;
    float target_temp;
    float base_temp;
    float temp;
    float max_temp;
    uint64_t max_ramp_duration;
    uint64_t pos;
    uint64_t ramp_duration;
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
    heater->pos = 0;
    heater->max_ramp_duration = SEC_TO_NSEC(MAX_RAMP_UP_DURATION * 100 /
					    config->power);
    heater->max_temp = config->max_temp;

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

    heater->temp = AMBIENT_TEMP;
    heater->base_temp = heater->temp;
    heater->target_temp = AMBIENT_TEMP;
    heater->pos = 0;
}

static int heater_set_temp(core_object_t *object, core_object_command_t *cmd) {
    heater_t *heater = (heater_t *)object;
    struct heater_set_temperature_args *args;

    if (cmd->object_cmd_id != HEATER_COMMAND_SET_TEMP)
	return -1;

    // If a command is still running, immediately complete it.
    if (heater->command.command_id)
	CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);

    heater->command = *cmd;
    args = (struct heater_set_temperature_args *)cmd->args;
    if (args->temperature < 0 || args->temperature > heater->max_temp)
	return -1;

    heater->pos = 0;
    heater->base_temp = heater->temp;
    heater->target_temp = max(args->temperature, AMBIENT_TEMP);

    /* Ramping up duration is a percentage of the max ramp up
     * duration (which is a function of the heater's power).
     *
     * Ramping down is based on a static duration. This should
     * better emulate real-world temperature drops.
     *
     * Both ramp up and down final durations depend on the ratio
     * of the target temp to the max heater temp.
     */
    if (heater->target_temp < heater->base_temp)
	heater->ramp_duration = SEC_TO_NSEC(MAX_RAMP_DOWN_DURATION);
    else
	heater->ramp_duration = heater->max_ramp_duration;

    heater->ramp_duration *= (heater->target_temp / heater->max_temp);

    log_debug(heater, "base: %.15f, target: %.15f, temp: %.15f",
	      heater->base_temp, heater->target_temp, heater->temp);
    return 0;
}

static void heater_status(core_object_t *object, void *status) {
    heater_status_t *s = (heater_status_t *)status;
    heater_t *heater = (heater_t *)object;

    s->temperature = heater->temp;
    s->max_temp = heater->max_temp;
}

static float powout(float value, uint8_t p) {
    if (value == 0 || value == 1)
	return value;
    return 1 - powf(1 - value, p);
}

static float linear(float value) {
    return value;
}

static float sinusoidal_inout(float value) {
    return -0.5 * (cosf(M_PI * value) - 1);
}

static float interpolate(uint64_t *p_pos, float base, float limit,
                         uint64_t time_delta, uint64_t dur) {
    float step_val;
    uint64_t pos = *p_pos;
    float val;

    if (pos + time_delta < dur)
        pos += time_delta;
    else
        pos = dur;
    step_val = (float)pos / dur;
    if (base <= limit)
	val = (base + (limit - base) * sinusoidal_inout(step_val));
    else
	val = (base - (base - limit) * linear(step_val));

    *p_pos = pos;
    return val;
}

static void heater_update(core_object_t *object, uint64_t ticks,
			  uint64_t timestep) {
    heater_t *heater = (heater_t *)object;
    uint64_t time_delta = timestep - heater->timestep;
    heater_temp_reached_event_data_t *data;
    uint64_t duration;

    heater->timestep = timestep;
    if (heater->temp == heater->target_temp)
       return;

    /*
     * Use interpolation function to approximate temperature
     * ramp.
     */
    heater->temp = interpolate(&heater->pos, heater->base_temp,
			       heater->target_temp, time_delta,
			       heater->ramp_duration);
    heater->temp = roundf(heater->temp * 1000) / 1000;
    log_debug(heater, "heater %s temp: %f", heater->object.name, heater->temp);

    if (heater->temp != heater->target_temp)
	return;

    CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);
    heater->command.command_id = 0;
    heater->command.object_cmd_id = HEATER_COMMAND_MAX;

    data = object_cache_alloc(heater_event_cache);
    if (data) {
        data->temp = heater->temp;
        CORE_EVENT_SUBMIT(heater, OBJECT_EVENT_HEATER_TEMP_REACHED, data);
    }
}

static void heater_destroy(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    core_object_destroy(object);
    object_cache_destroy(heater_event_cache);
    free(heater);
}

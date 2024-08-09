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

#define AMBIENT_TEMP 25

typedef struct {
    uint16_t power;
} heater_config_params_t;

typedef struct {
    core_object_t object;
    core_object_command_t command;
    uint64_t timestep;
    float set_temp;
    float target_temp;
    float base_temp;
    float temp;
    uint64_t ramp_duration;
    uint64_t pos;
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
    heater->ramp_duration = SEC_TO_NSEC(120.0 * 100 / config->power);

    if (object_cache_create(&heater_event_cache,
			    sizeof(heater_temp_reached_event_data_t))) {
	core_object_destroy(&heater->object);
	free(heater);
	return NULL;
    }

    return heater;
}

static void heater_reset(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    heater->base_temp = heater->temp;
    heater->target_temp = AMBIENT_TEMP;
}

static int heater_set_temp(core_object_t *object, core_object_command_t *cmd) {
    heater_t *heater = (heater_t *)object;
    struct heater_set_temperature_args *args;

    if (cmd->object_cmd_id != HEATER_COMMAND_SET_TEMP)
	return -1;

    heater->command = *cmd;
    args = (struct heater_set_temperature_args *)cmd->args;
    if (args->temperature < AMBIENT_TEMP)
	return -1;

    heater->set_temp = args->temperature;
    if (heater->set_temp > AMBIENT_TEMP) {
        heater->base_temp = AMBIENT_TEMP;
        heater->target_temp = heater->set_temp;
    } else {
	heater->base_temp = heater->temp;
	heater->target_temp = AMBIENT_TEMP;
    }

    return 0;
}

static void heater_status(core_object_t *object, void *status) {
    heater_status_t *s = (heater_status_t *)status;
    heater_t *heater = (heater_t *)object;

    s->temperature = heater->temp;
}

static float powout(float value, uint8_t p) {
    if (value == 0 || value == 1)
	return value;
    return 1 - powl(1 - value, p);
}

static float interpolate(uint64_t *p_pos, float base, float limit,
			 uint64_t time_delta, uint64_t dur) {
    float step_val;
    uint64_t pos = *p_pos;
    float val;

    if (base <= limit)
	pos = min(pos + time_delta, dur);
    else
	pos = max(pos - time_delta, 0);
    step_val = (float)pos / dur;
    if (base <= limit)
	val = (base + (limit - base) * powout(step_val, 3));
    else
	val = (base - (base - limit) * powout(step_val, 5));

    *p_pos = pos;
    return val;
}

static void heater_update(core_object_t *object, uint64_t ticks,
			  uint64_t timestep) {
    heater_t *heater = (heater_t *)object;
    uint64_t time_delta = timestep - heater->timestep;
    heater_temp_reached_event_data_t *data;

    heater->timestep = timestep;
    if (heater->set_temp == 0.0 || heater->temp == heater->set_temp)
       return;

    /*
     * Use interpolation function to approximate temperature
     * ramp.
     */
    heater->temp = interpolate(&heater->pos, heater->base_temp,
			       heater->target_temp, time_delta,
			       heater->ramp_duration);
    heater->temp = roundl(heater->temp * 100) / 100;
    log_debug(heater, "heater %s temp: %f", heater->object.name, heater->temp);

    if (heater->temp != heater->target_temp)
	return;

    CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);

    data = object_cache_alloc(heater_event_cache);
    if (data) {
        data->temp = heater->temp;
        CORE_EVENT_SUBMIT(heater, OBJECT_EVENT_HEATER_TEMP_REACHED,
                          core_object_to_id((core_object_t *)heater), data);
    }
}

static void heater_destroy(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    core_object_destroy(object);
    object_cache_destroy(heater_event_cache);
    free(heater);
}

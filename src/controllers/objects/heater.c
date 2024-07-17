#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "object_defs.h"
#include "../common_defs.h"
#include "thermistor.h"
#include "../utils.h"
#include "heater.h"

#define AMBIENT_TEMP 25

enum {
  HEATER_COMMAND_SET_TEMP,
  HEATER_COMMAND_MAX,
};

typedef struct {
    char sensor_type[64];
    uint32_t beta_value;
    uint16_t power;
} heater_config_params_t;

struct heater_set_temperature_args {
    uint32_t temperature;
};

struct heater_status {
    uint32_t tmeperature;
    uint16_t power;
};

typedef struct {
    core_object_t object;
    core_call_data_t *call_data;
    core_object_command_t command;
    uint64_t timestep;
    thermistor_type_t type;
    uint32_t beta_value;
    float set_temp;
    float target_temp;
    float base_temp;
    float temp;
    float resistance;
    uint64_t ramp_duration;
    uint64_t pos;
    float a;
    float b;
    float c;
} heater_t;

void heater_update(core_object_t *object, uint64_t ticks, uint64_t timestamp);
int heater_set_temp(core_object_t *object, core_object_command_t *cmd);
void heater_status(core_object_t *object, void *status);
void heater_destroy(core_object_t *object);

heater_t *object_create(const char *name, void *config_ptr,
			core_call_data_t *call_data) {
    heater_t *heater;
    heater_config_params_t *config = (heater_config_params_t *)config_ptr;

    heater = calloc(1, sizeof(*heater));
    if (!heater)
	return NULL;

    heater->object.type = OBJECT_TYPE_HEATER;
    heater->object.update = heater_update;
    heater->object.destroy = heater_destroy;
    heater->object.exec_command = heater_set_temp;
    heater->object.get_state = heater_status;
    heater->object.name = strdup(name);
    heater->call_data = call_data;
    heater->pos = 0;
    heater->ramp_duration = SEC_TO_NSEC(120.0 * 100 / config->power);
    printf("duration: %lu nsec\n", heater->ramp_duration);

    if (!strncmp(config->sensor_type, "pt100", 5) ||
	!strncmp(config->sensor_type, "PT100", 5))
	heater->type = SENSOR_TYPE_PT100;
    else if (!strncmp(config->sensor_type, "pt1000", 6) ||
	     !strncmp(config->sensor_type, "PT1000", 6))
	heater->type = SENSOR_TYPE_PT1000;
    else {
	heater->type = SENSOR_TYPE_B3950;
	heater->beta_value = config->beta_value;
	calc_coefficiants(b3950_nominal_t, b3950_nominal_r,
			  heater->beta_value, &heater->a,
			  &heater->b, &heater->c);
    }

    return heater;
}

int heater_set_temp(core_object_t *object, core_object_command_t *cmd) {
    heater_t *heater = (heater_t *)object;
    struct heater_set_temperature_args *args;

    printf("got command: %u\n", cmd->object_cmd_id);
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

void heater_status(core_object_t *object, void *status) {
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

void heater_update(core_object_t *object, uint64_t ticks, uint64_t timestep) {
    heater_t *heater = (heater_t *)object;
    uint64_t time_delta = timestep - heater->timestep;

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

    switch (heater->type) {
    case SENSOR_TYPE_PT100:
	heater->resistance = pt100_resistance(heater->temp);
	break;
    case SENSOR_TYPE_PT1000:
	heater->resistance = pt1000_resistance(heater->temp);
	break;
    case SENSOR_TYPE_B3950:
	heater->resistance = beta_resistance(heater->temp, heater->a,
					     heater->b, heater->c);
    default:
	break;
    }
    //printf("resistance: %f\n");
    if (heater->temp == heater->target_temp) {
	heater_temp_reached_event_data_t data;
	data.temp = heater->temp;
	heater->call_data->event_submit(
	    OBJECT_EVENT_HEATER_TEMP_REACHED,
	    core_object_to_id((core_object_t *)heater),
	    &data, heater->call_data->event_submit_data);
	heater->call_data->completion_callback(
	    heater->command.command_id, 0, heater->call_data->completion_data);
    }
}

void heater_destroy(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    core_object_destroy(object);
    free(heater);
}

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
#include <math.h>
#include "object_defs.h"
#include "../common_defs.h"
#include "heater.h"
#include "thermistor.h"

#define KELVIN (-273.15)

typedef enum {
    SENSOR_TYPE_PT100,
    SENSOR_TYPE_PT1000,
    SENSOR_TYPE_B3950,
    SENSOR_TYPE_MAX,
} thermistor_type_t;

static float pt100_A = 3.9083e-3;
static float pt100_B = -5.775e-7;
static float pt100_C = -4.183e-12;
static float pt100_base = 100.0;
static float pt1000_base = 1000.0;

static inline float resistance_calc(float base, float temp) {
    return base * (1 + pt100_A * temp +
		   pt100_B * temp * temp +
		   (temp - 100) * pt100_C * temp * temp * temp);
}

#define b3950_nominal_r (100000.0) // in Ohms.
#define b3950_nominal_t (25.0)  // in C

static inline void calc_coefficiants(float temp, float resistance,
				     uint32_t beta, float *a,
				     float *b, float *c) {
    float inv = 1.0 / (temp - KELVIN);
    float l = log(resistance);
    *c = 0.0;
    *b = 1.0 / beta;
    *a = inv - *b * l;
}

static inline float beta_resistance(float temp, float a, float b, float c) {
    float inv = 1.0 / (temp - KELVIN);
    float l = (inv - a) / b;
    float r = exp(l);
    return r;
}

typedef struct {
    char sensor_type[64];
    char heater[64];
    uint32_t beta_value;
} thermistor_config_params_t;

typedef struct {
    core_object_t object;
    thermistor_type_t type;
    uint16_t beta;
    const char *heater_name;
    core_object_t *heater;
    float resistance;
    float a;
    float b;
    float c;
} thermistor_t;

static int thermistor_init(core_object_t *object);
static void thermistor_update(core_object_t *object, uint64_t ticks,
                              uint64_t runtime);
static void thermistor_status(core_object_t *object, void *status);
static void thermistor_destroy(core_object_t *object);

thermistor_t *object_create(const char *name, void *config_ptr) {
    thermistor_t *thermistor;
    thermistor_config_params_t *config =
	(thermistor_config_params_t *)config_ptr;

    thermistor = calloc(1, sizeof(*thermistor));
    if (!thermistor)
	return NULL;

    thermistor->object.type = OBJECT_TYPE_THERMISTOR;
    thermistor->object.init = thermistor_init;
    thermistor->object.update = thermistor_update;
    thermistor->object.destroy = thermistor_destroy;
    thermistor->object.get_state = thermistor_status;
    thermistor->object.name = strdup(name);
    thermistor->heater_name = strdup(config->heater);

    if (!strncmp(config->sensor_type, "pt100", strlen(config->sensor_type)) ||
        !strncmp(config->sensor_type, "PT100", strlen(config->sensor_type)))
        thermistor->type = SENSOR_TYPE_PT100;
    else if (!strncmp(config->sensor_type, "pt1000",
                      strlen(config->sensor_type)) ||
             !strncmp(config->sensor_type, "PT1000",
                      strlen(config->sensor_type)))
        thermistor->type = SENSOR_TYPE_PT1000;
    else {
        thermistor->type = SENSOR_TYPE_B3950;
        thermistor->beta = config->beta_value;
    }

    return thermistor;
}

static int thermistor_init(core_object_t *object) {
    thermistor_t *thermistor = (thermistor_t *)object;

    thermistor->heater = CORE_LOOKUP_OBJECT(thermistor, OBJECT_TYPE_HEATER,
					    thermistor->heater_name);
    if (!thermistor->heater)
	return -1;

    calc_coefficiants(b3950_nominal_t, b3950_nominal_r, thermistor->beta,
                      &thermistor->a, &thermistor->b, &thermistor->c);
    return 0;
}

static void thermistor_status(core_object_t *object, void *status) {
    thermistor_status_t *s = (thermistor_status_t *)status;
    thermistor_t *thermistor = (thermistor_t *)object;

    s->resistance = thermistor->resistance;
}

static void thermistor_update(core_object_t *object, uint64_t ticks,
			      uint64_t runtime) {
    thermistor_t *thermistor = (thermistor_t *)object;
    heater_status_t heater_status;

    thermistor->heater->get_state(thermistor->heater, &heater_status);

    switch (thermistor->type) {
    case SENSOR_TYPE_PT100:
	thermistor->resistance = resistance_calc(pt100_base,
						 heater_status.temperature);
	break;
    case SENSOR_TYPE_PT1000:
	thermistor->resistance = resistance_calc(pt1000_base,
						 heater_status.temperature);
	break;
    case SENSOR_TYPE_B3950:
	thermistor->resistance =
	    beta_resistance(heater_status.temperature, thermistor->a,
			    thermistor->b, thermistor->c);
    default:
	break;
    }
}

static void thermistor_destroy(core_object_t *object) {
    thermistor_t *thermistor = (thermistor_t *)object;

    core_object_destroy(object);
    free((char *)thermistor->heater_name);
    free(thermistor);
}

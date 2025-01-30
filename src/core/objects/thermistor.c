/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2025 Mitko Haralanov
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
#include <common_defs.h>
#include "heater.h"
#include "thermistor.h"

#define TO_KELVIN(x) ((x) + 273.15)

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

#define b3950_nominal_r (100000.0) // in Ohms.
#define b3950_nominal_t (25.0)  // in C

typedef enum {
    CONFIG_TYPE_NONE,
    CONFIG_TYPE_BETA,
    CONFIG_TYPE_COEFF,
} thermistor_config_type_t;

typedef struct {
    uint16_t temp;
    uint32_t resistance;
} config_temp_t;

typedef struct {
    thermistor_config_type_t type;
    uint16_t resistor;
    struct {
        uint16_t beta;
    } beta;
    config_temp_t coeff[3];
} thermistor_config_t;

typedef struct {
    char sensor_type[64];
    char heater[64];
    char pin[8];
    uint16_t max_adc;
    thermistor_config_t config;
} thermistor_config_params_t;

typedef struct {
    core_object_t object;
    thermistor_type_t type;
    uint16_t max_adc;
    uint32_t resistor;
    char pin[8];
    const char *heater_name;
    core_object_t *heater;
    float resistance;
    double a;
    double b;
    double c;
} thermistor_t;

static int thermistor_init(core_object_t *object);
static void thermistor_update(core_object_t *object, uint64_t ticks,
                              uint64_t runtime);
static void thermistor_status(core_object_t *object, void *status);
static void thermistor_destroy(core_object_t *object);

static inline float resistance_calc(float base, float temp) {
    return base * (1 + pt100_A * temp + pt100_B * temp * temp +
                   (temp - 100) * pt100_C * temp * temp * temp);
}

static inline uint16_t calc_adc_value(float resistance, uint32_t resistor,
                                      uint16_t max_adc) {
    return (uint16_t)round((resistance / ((float)resistor + resistance)) *
                           (max_adc + 1));
}

static inline void calc_coefficiants_beta(float temp, float resistance,
                                          uint32_t beta, double *a, double *b,
                                          double *c) {
    double inv = 1.0 / TO_KELVIN(temp);
    double l = log(resistance);
    *c = 0.0;
    *b = 1.0 / beta;
    *a = inv - *b * l;
}

/* Find Steinhart–Hart semiconductor resistance coefficients. */
static inline void calc_coefficiants_temp(config_temp_t *config, double *a,
										  double *b, double *c)
{
    double Y1 = 1.0 / TO_KELVIN(config[0].temp);
    double Y2 = 1.0 / TO_KELVIN(config[1].temp);
    double Y3 = 1.0 / TO_KELVIN(config[2].temp);
    double L1 = log((double)config[0].resistance);
    double L2 = log((double)config[1].resistance);
    double L3 = log((double)config[2].resistance);
    double g2 = (Y2 - Y1) / (L2 - L1);
    double g3 = (Y3 - Y1) / (L3 - L1);

    *c = ((g3 - g2) / (L3 - L2)) / (L1 + L2 + L3);
    *b = g2 - *c * (pow(L1, 2) + L1 * L2 + pow(L2, 2));
    *a = Y1 - (*b + pow(L1, 2) * *c) * L1;
}

/*
 * Use Steinhart–Hart inverse equation to compute the thermistor resistance
 * based on heater temperature.
 */
static inline float beta_resistance(double temp, double a, double b, double c)
{
	double l;

    if (c == 0.0) {
        double inv = 1.0 / TO_KELVIN(temp);

        l = (inv - a) / b;
    } else {
        double x = (1.0 / c) * (a - 1.0 / TO_KELVIN(temp));
        double y = sqrt(pow(b / (3 * c), 3) + (pow(x, 2) / 4));

        l = cbrt(y - x / 2) - cbrt(y + x / 2);
    }

    float r = exp(l);
    return r;
}

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
    thermistor->max_adc = config->max_adc;
    thermistor->resistor = config->config.resistor;
    strncpy(thermistor->pin, config->pin, sizeof(thermistor->pin));

    if (!strncasecmp(config->sensor_type, "pt1000", 6))
        thermistor->type = SENSOR_TYPE_PT100;
    else if (!strncasecmp(config->sensor_type, "pt100", 5))
        thermistor->type = SENSOR_TYPE_PT1000;
    else {
        thermistor->type = SENSOR_TYPE_B3950;
        switch (config->config.type) {
        case CONFIG_TYPE_BETA:
            calc_coefficiants_beta(b3950_nominal_t, b3950_nominal_r,
                                   config->config.beta.beta,
                                   &thermistor->a, &thermistor->b,
                                   &thermistor->c);
            break;
        case CONFIG_TYPE_COEFF:
            calc_coefficiants_temp(config->config.coeff, &thermistor->a,
                                   &thermistor->b, &thermistor->c);
            break;
        default:
            core_object_destroy(&thermistor->object);
            free(thermistor);
            return NULL;
        }
    }

    return thermistor;
}

static int thermistor_init(core_object_t *object) {
    thermistor_t *thermistor = (thermistor_t *)object;

    thermistor->heater = CORE_LOOKUP_OBJECT(thermistor, OBJECT_TYPE_HEATER,
                                            thermistor->heater_name);
    if (!thermistor->heater)
        return -1;

    return 0;
}

static void thermistor_status(core_object_t *object, void *status) {
    thermistor_status_t *s = (thermistor_status_t *)status;
    thermistor_t *thermistor = (thermistor_t *)object;

    s->resistance = thermistor->resistance;
    s->adc = calc_adc_value(thermistor->resistance, thermistor->resistor,
                            thermistor->max_adc);
    strncpy(s->pin, thermistor->pin, sizeof(s->pin));
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

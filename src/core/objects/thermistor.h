/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2026 Mitko Haralanov
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
#ifndef __THERMISTOR_H__
#define __THERMISTOR_H__
#include <stdint.h>
#include "global.h"

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
} thermistor_sensor_params_t;

typedef struct {
    char sensor_type[HEAT_SENSOR_NAME_SIZE];
    char heater[HEATER_NAME_SIZE];
    char pin[PIN_NAME_SIZE];
    uint16_t max_adc;
    thermistor_sensor_params_t config;
} thermistor_config_params_t;

typedef struct {
    float resistance;
    uint16_t adc;
    char pin[PIN_NAME_SIZE];
} thermistor_status_t;

#endif

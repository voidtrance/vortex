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
#ifndef __HEATER_H__
#define __HEATER_H__
#include <stdbool.h>
#include "global.h"
#include <stdint.h>

#define MAX_LAYER_COUNT 8

enum heater_commands {
    HEATER_COMMAND_SET_TEMP,
    HEATER_COMMAND_USE_PINS,
    HEATER_COMMAND_MAX,
};

struct heater_set_temp_args {
    float temperature;
};

struct heater_use_pins_args {
    bool enable;
};

struct heater_use_pins_data {
    unsigned long pin_addr;
};

typedef struct {
    float temperature;
    float max_temp;
    char pin[PIN_NAME_SIZE];
    unsigned long pin_addr;
} heater_status_t;

typedef struct {
    float temp;
} heater_temp_reached_event_data_t;

typedef enum {
    HEATER_LAYER_TYPE_NONE,
    HEATER_LAYER_TYPE_HEATER,
    HEATER_LAYER_TYPE_BODY,
    HEATER_LAYER_TYPE_OTHER,
    HEATER_LAYER_TYPE_MAX
} heater_layer_type_t;

typedef enum { CONV_TOP, CONV_BOTTOM, CONV_MAX } convection_type_t;

typedef struct {
    double x;
    double y;
    double z;
} heater_object_size_t;

typedef struct {
    double density;
    double capacity;
    double conductivity;
    double emissivity;
    float convection[CONV_MAX];
} heater_material_t;

typedef struct {
    heater_layer_type_t type;
    heater_material_t material;
    heater_object_size_t size;
} heater_layer_t;

typedef struct {
    uint16_t power;
    char pin[PIN_NAME_SIZE];
    float max_temp;
    float kp;
    float ki;
    float kd;
    heater_layer_t layers[MAX_LAYER_COUNT];
} heater_config_params_t;

#endif

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
#ifndef __HEATER_H__
#define __HEATER_H__
#include <stdbool.h>

enum {
    HEATER_COMMAND_SET_TEMP,
    HEATER_COMMAND_USE_PINS,
    HEATER_COMMAND_MAX,
};

struct heater_set_temperature_args {
    float temperature;
};

struct heater_use_pins_args {
    bool enable;
};

typedef struct {
    float temperature;
    float max_temp;
    char pin[8];
    unsigned long pin_addr;
} heater_status_t;

#endif

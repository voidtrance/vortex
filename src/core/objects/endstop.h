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
#ifndef __ENDSTOP_H__
#define __ENDSTOP_H__
#include <stdbool.h>
#include <kinematics.h>
#include "global.h"

typedef struct {
    bool triggered;
    const char type[4];
    kinematics_axis_type_t axis;
    char pin[PIN_NAME_SIZE];
    unsigned long pin_addr;
} endstop_status_t;

typedef struct {
    bool triggered;
} endstop_triggered_event_data_t;

typedef struct {
    const char type[4];
    const char axis;
    char pin[8];
} endstop_config_params_t;

#endif

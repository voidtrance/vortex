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
#ifndef __PROBE_H__
#define __PROBE_H__
#include <stdbool.h>
#include <kinematics.h>

typedef struct {
    bool triggered;
    float offsets[AXIS_TYPE_MAX];
    double position[AXIS_TYPE_MAX];
    char pin[8];
    unsigned long pin_addr;
} probe_status_t;

typedef struct {
    double position[AXIS_TYPE_MAX];
} probe_trigger_event_data_t;

#endif

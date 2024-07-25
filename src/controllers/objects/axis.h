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
#ifndef __AXIS_H__
#define __AXIS_H__
#include <stdint.h>
#include <stdbool.h>

enum {
    AXIS_COMMAND_MOVE,
    AXIS_COMMAND_HOME,
    AXIS_COMMAND_MAX,
};

typedef struct {
    float distance;
} axis_move_command_opts_t;

typedef struct {
    bool homed;
    float length;
    float position;
} axis_status_t;

typedef struct {
    const char *axis;
} axis_homed_event_data_t;

#endif

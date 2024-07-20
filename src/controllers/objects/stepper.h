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
#ifndef __STEPPER_H__
#define __STEPPER_H__
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    MOVE_DIR_NONE,
    MOVE_DIR_FWD,
    MOVE_DIR_BACK
} stepper_move_dir_t;

enum {
    STEPPER_COMMAND_ENABLE,
    STEPPER_COMMAND_MOVE,
    STEPPER_COMMAND_MAX,
};

struct stepper_enable_args {
    int enable;
};

struct stepper_move_args {
    stepper_move_dir_t direction;
    uint32_t steps;
};

typedef struct {
    bool enabled;
    uint64_t steps;
    uint16_t spr;
    uint8_t microsteps;
} stepper_status_t;

#endif

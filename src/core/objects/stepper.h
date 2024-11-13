/*
 * vortex - GCode machine emulator
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
    STEPPER_COMMAND_SET_SPEED,
    STEPPER_COMMAND_SET_ACCEL,
    STEPPER_COMMAND_MOVE,
    STEPPER_COMMAND_USE_PINS,
    STEPPER_COMMAND_MAX,
};

struct stepper_enable_args {
    int enable;
};

struct stepper_set_speed_args {
    double steps_per_second;
};

struct stepper_set_accel_args {
    uint32_t accel; // steps per second^2
    uint32_t decel; // steps per second^2
};

struct stepper_move_args {
    stepper_move_dir_t direction;
    uint32_t steps;
};

struct stepper_use_pin_args {
    bool enable;
};

typedef struct {
    bool enabled;
    bool use_pins;
    int64_t steps;
    uint16_t spr;
    uint8_t microsteps;
    double speed;
    double accel;
    double decel;
    uint32_t steps_per_mm;
    char enable_pin[8];
    char dir_pin[8];
    char step_pin[8];
    unsigned long pin_addr;
} stepper_status_t;

#endif

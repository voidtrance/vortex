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
#ifndef __PWM_H__
#define __PWM_H__
#include "object_defs.h"
#include <stdint.h>
#include <stdbool.h>
#include "global.h"

typedef struct {
    uint32_t counter;
    uint32_t pwm_max;
    uint32_t duty_cycle;
    bool on;
    char pin[PIN_NAME_SIZE];
} pwm_state_t;

enum {
    PWM_SET_PARAMS,
    PWM_SET_OBJECT,
    PWM_SET_DUTY_CYCLE,
};

struct pwm_set_object_args {
    core_object_type_t type;
    char object_name[OBJECT_NAME_SIZE];
};

struct pwm_set_parms_args {
    uint16_t prescaler;
};

struct pwm_set_duty_cycle_args {
    uint32_t duty_cycle;
};

#endif
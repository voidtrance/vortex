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
#include <errno.h>
#include <ctype.h>
#include <string.h>
#include "kinematics.h"
#include "cartesian.h"
#include "corexy.h"
#include "delta.h"
#include <debug.h>

int (*motor_movement_func)(coordinates_t *, coordinates_t *);
int (*axis_movement_func)(coordinates_t *, coordinates_t *);
int (*toolhead_position)(coordinates_t *, coordinates_t *);

static kinematics_config_t core_kinematics = { 0 };

static inline int none_motor_movement(coordinates_t *delta,
                                      coordinates_t *movement) {
    memset(movement, 0, sizeof(coordinates_t));
    return 0;
}

static inline int none_axis_movement(coordinates_t *delta,
                                     coordinates_t *movement) {
    return none_motor_movement(delta, movement);
}

static inline int none_toolhead_position(coordinates_t *axis_position,
                                         coordinates_t *position) {
    return none_motor_movement(axis_position, position);
}

int kinematics_init(kinematics_config_t *config) {
    memcpy(&core_kinematics, config, sizeof(*config));

    switch (core_kinematics.type) {
    case KINEMATICS_NONE:
        motor_movement_func = none_motor_movement;
        axis_movement_func = none_axis_movement;
        toolhead_position = none_toolhead_position;
        break;
    case KINEMATICS_CARTESIAN:
        motor_movement_func = cartesian_motor_movement;
        axis_movement_func = cartesian_axis_movement;
        toolhead_position = cartesian_toolhead_position;
        cartesian_init(&core_kinematics.cartesian);
        break;
    case KINEMATICS_COREXY:
        motor_movement_func = corexy_motor_movement;
        axis_movement_func = corexy_axis_movement;
        toolhead_position = corexy_toolhead_position;
        corexy_init(&core_kinematics.corexy);
        break;
    case KINEMATICS_DELTA:
        motor_movement_func = delta_motor_movement;
        axis_movement_func = delta_axis_movement;
        toolhead_position = delta_toolhead_position;
        delta_init(&core_kinematics.delta);
        break;
    default:
        return -EINVAL;
    }

    return 0;
}

kinematics_type_t kinematics_type_get(void) {
    return core_kinematics.type;
}

axis_type_t kinematics_axis_type_from_char(char type_char) {
    axis_type_t type;

    type_char = tolower(type_char);
    switch (type_char) {
    case 'x':
        type = AXIS_TYPE_X;
        break;
    case 'y':
        type = AXIS_TYPE_Y;
        break;
    case 'z':
        type = AXIS_TYPE_Z;
        break;
    case 'a':
        type = AXIS_TYPE_A;
        break;
    case 'b':
        type = AXIS_TYPE_B;
        break;
    case 'c':
        type = AXIS_TYPE_C;
        break;
    case 'e':
        type = AXIS_TYPE_E;
        break;
    default:
        type = AXIS_TYPE_MAX;
    }

    return type;
}

void *kinematics_get_config(void) {
    switch (core_kinematics.type) {
    case KINEMATICS_CARTESIAN:
        return &core_kinematics.cartesian;
    case KINEMATICS_COREXY:
        return &core_kinematics.corexy;
    case KINEMATICS_COREXZ:
        return &core_kinematics.corexz;
    case KINEMATICS_DELTA:
        return &core_kinematics.delta;
    default:
        return NULL;
    }
}

int kinematics_get_motor_movement(coordinates_t *delta,
                                  coordinates_t *movement) {
    return motor_movement_func(delta, movement);
}

int kinematics_get_axis_movement(coordinates_t *delta,
                                 coordinates_t *movement) {
    return axis_movement_func(delta, movement);
}

int kinematics_get_toolhead_position(coordinates_t *axis_positions,
                                     coordinates_t *position) {
    return toolhead_position(axis_positions, position);
}

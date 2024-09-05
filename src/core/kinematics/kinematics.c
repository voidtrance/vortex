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
#include <errno.h>
#include "kinematics.h"
#include "cartesian.h"
#include "corexy.h"

int (*motor_movement_func)(coordinates_t *, coordinates_t *);
int (*axis_movement_func)(coordinates_t *, coordinates_t *);

static kinematics_type_t core_kinematics_type = KINEMATICS_NONE;

int kinematics_type_set(kinematics_type_t type) {
    core_kinematics_type = type;

    switch (core_kinematics_type) {
    case KINEMATICS_CARTESIAN:
	motor_movement_func = cartesian_motor_movement;
	axis_movement_func = cartesian_axis_movement;
	break;
    default:
	return -EINVAL;
    }

    return 0;
}

kinematics_type_t kinematics_type_get(void) {
    return core_kinematics_type;
}

int compute_motor_movement(coordinates_t *delta, coordinates_t *movement) {
    return motor_movement_func(delta, movement);
}

int compute_axis_movement(coordinates_t *delta, coordinates_t *movement) {
    return axis_movement_func(delta, movement);
}

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
#ifndef __KINEMATICS_H__
#define __KINEMATICS_H__

typedef struct coordinates {
  double x;
  double y;
  double z;
} coordinates_t;

typedef enum {
    KINEMATICS_NONE,
    KINEMATICS_CARTESIAN,
    KINEMATICS_COREXY,
    KINEMATICS_COREXZ,
    KINEMATICS_DELTA,
    KINEMATICS_MAX,
} kinematics_type_t;

int kinematics_type_set(kinematics_type_t type);
kinematics_type_t kinematics_type_get(void);
int compute_motor_movement(coordinates_t *delta, coordinates_t *movement);
int compute_axis_movement(coordinates_t *delta, coordinates_t *movement);

#endif

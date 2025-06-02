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
#ifndef __KINEMATICS_H__
#define __KINEMATICS_H__

typedef enum {
    AXIS_TYPE_X,
    AXIS_TYPE_Y,
    AXIS_TYPE_Z,
    AXIS_TYPE_A,
    AXIS_TYPE_B,
    AXIS_TYPE_C,
    AXIS_TYPE_E,
    AXIS_TYPE_MAX,
} axis_type_t;

typedef struct coordinates {
    double x;
    double y;
    double z;
    double a;
    double b;
    double c;
    double e;
} coordinates_t;

typedef enum {
    KINEMATICS_NONE,
    KINEMATICS_CARTESIAN,
    KINEMATICS_COREXY,
    KINEMATICS_COREXZ,
    KINEMATICS_DELTA,
    KINEMATICS_MAX,
} kinematics_type_t;

typedef struct {
    float min;
    float max;
} axis_limits_t;

typedef struct {
    axis_limits_t limits[AXIS_TYPE_MAX];
} cartesian_kinematics_config_t;

#define DEG2RAD(angle) ((angle) * M_PI / 180.0f)

typedef struct {
    axis_limits_t limits[AXIS_TYPE_MAX];
    float arm_length;
    float radius;
    float tower_radius;
    float tower_angle[3];
    float z_length;
} delta_kinematics_config_t;

typedef struct {
    kinematics_type_t type;
    union {
        cartesian_kinematics_config_t cartesian;
        cartesian_kinematics_config_t corexy;
        cartesian_kinematics_config_t corexz;
        delta_kinematics_config_t delta;
    };
} kinematics_config_t;

int kinematics_init(kinematics_config_t *config);
kinematics_type_t kinematics_type_get(void);
axis_type_t kinematics_axis_type_from_char(char type_char);
void *kinematics_get_config(void);
int kinematics_get_motor_movement(coordinates_t *delta,
                                  coordinates_t *movement);
int kinematics_get_axis_movement(coordinates_t *delta, coordinates_t *movement);
int kinematics_get_toolhead_position(coordinates_t *axis_position,
                                     coordinates_t *position);

#endif

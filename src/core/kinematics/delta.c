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
#include <math.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
#include "delta.h"
#include <debug.h>

#define SQ(x) ((x) * (x))
#define TOLERANCE (1e-6)

typedef enum {
    TOWER_A,
    TOWER_B,
    TOWER_C,
    TOWER_MAX,
} tower_t;

struct tower_coord {
    float x;
    float y;
    float z;
};

typedef struct {
    delta_kinematics_config_t base_config;
    struct tower_coord tower_position[TOWER_MAX];
} delta_config_t;

static delta_config_t delta_config = { 0 };

int delta_init(delta_kinematics_config_t *config) {
    size_t tower;

    memset(config->limits, 0, sizeof(config->limits));
    for (tower = 0; tower < TOWER_MAX; tower++) {
        delta_config.tower_position[tower].x =
            config->tower_radius * cosf(DEG2RAD(config->tower_angle[tower]));
        delta_config.tower_position[tower].y =
            config->tower_radius * sinf(DEG2RAD(config->tower_angle[tower]));
        delta_config.tower_position[tower].z =
            sqrtf(SQ(config->arm_length) - SQ(config->tower_radius));
        config->limits[AXIS_TYPE_A + tower].min =
            delta_config.tower_position[tower].z;
        config->limits[AXIS_TYPE_A + tower].max =
            delta_config.tower_position[tower].z + config->z_length;
    }

    memcpy(&delta_config.base_config, config, sizeof(*config));
    return 0;
}

int delta_motor_movement(coordinates_t *delta, coordinates_t *movement) {
    memset(movement, 0, sizeof(*movement));
    movement->a = sqrt(SQ(delta_config.base_config.arm_length) -
                       SQ(delta->x - delta_config.tower_position[TOWER_A].x) -
                       SQ(delta->y - delta_config.tower_position[TOWER_A].y)) +
                  delta->z;
    movement->b = sqrt(SQ(delta_config.base_config.arm_length) -
                       SQ(delta->x - delta_config.tower_position[TOWER_B].x) -
                       SQ(delta->y - delta_config.tower_position[TOWER_B].y)) +
                  delta->z;
    movement->c = sqrt(SQ(delta_config.base_config.arm_length) -
                       SQ(delta->x - delta_config.tower_position[TOWER_C].x) -
                       SQ(delta->y - delta_config.tower_position[TOWER_C].y)) +
                  delta->z;
    return 0;
}

int delta_axis_movement(coordinates_t *delta, coordinates_t *movement) {
    *movement = *delta;
    return 0;
}

int delta_toolhead_position(coordinates_t *axis_positions,
                            coordinates_t *position) {
    // Actuator linear positions
    float LP[TOWER_MAX] = { axis_positions->a, axis_positions->b,
                            axis_positions->c };
    // Actuator endpoints (A1-A3)
    struct tower_coord AP[TOWER_MAX];

    for (int i = 0; i < TOWER_MAX; i++) {
        AP[i].x = delta_config.tower_position[i].x; // X
        AP[i].y = delta_config.tower_position[i].y; // Y
        AP[i].z = LP[i]; // Z
    }

    // Calculate using the closed-form solution
    // See: https://en.wikipedia.org/wiki/Trilateration#Three-sphere_intersection

    // Vectors between towers
    float ex[3], ey[3];
    ex[0] = AP[TOWER_B].x - AP[TOWER_A].x;
    ex[1] = AP[TOWER_B].y - AP[TOWER_A].y;
    ex[2] = AP[TOWER_B].z - AP[TOWER_A].z;
    float d = sqrtf(SQ(ex[0]) + SQ(ex[1]) + SQ(ex[2]));
    if (d < TOLERANCE)
        return -1;

    float i = ((AP[TOWER_C].x - AP[TOWER_A].x) * ex[0] +
               (AP[TOWER_C].y - AP[TOWER_A].y) * ex[1] +
               (AP[TOWER_C].z - AP[TOWER_A].z) * ex[2]) /
              d;

    ey[0] = AP[TOWER_C].x - AP[TOWER_A].x - i * ex[0] / d;
    ey[1] = AP[TOWER_C].y - AP[TOWER_A].y - i * ex[1] / d;
    ey[2] = AP[TOWER_C].z - AP[TOWER_A].z - i * ex[2] / d;
    float j = sqrtf(SQ(ey[0]) + SQ(ey[1]) + SQ(ey[2]));
    if (j < 1e-6f)
        return -1;

    // Radii
    float r1 = delta_config.base_config.arm_length;
    float r2 = delta_config.base_config.arm_length;
    float r3 = delta_config.base_config.arm_length;

    float x_val = (SQ(r1) - SQ(r2) + SQ(d)) / (2 * d);
    float y_val = (SQ(r1) - SQ(r3) + SQ(i) + SQ(j) - 2 * i * x_val) / (2 * j);
    // z can be positive or negative, choose the lower value (printer coordinate system)
    float z_sq = SQ(r1) - SQ(x_val) - SQ(y_val);
    if (z_sq < 0)
        return -1;
    float z_val = -sqrtf(z_sq);

    // Build unit vectors
    float exu[3] = { ex[0] / d, ex[1] / d, ex[2] / d };
    float eyu[3] = { ey[0] / j, ey[1] / j, ey[2] / j };
    float ezu[3] = { exu[1] * eyu[2] - exu[2] * eyu[1],
                     exu[2] * eyu[0] - exu[0] * eyu[2],
                     exu[0] * eyu[1] - exu[1] * eyu[0] };

    position->x =
        AP[TOWER_A].x + x_val * exu[0] + y_val * eyu[0] + z_val * ezu[0];
    position->y =
        AP[TOWER_A].y + x_val * exu[1] + y_val * eyu[1] + z_val * ezu[1];
    position->z =
        AP[TOWER_A].z + x_val * exu[2] + y_val * eyu[2] + z_val * ezu[2];

    return 0;
}

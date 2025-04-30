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
    float base_height[TOWER_MAX];
    coordinates_t tower_position[TOWER_MAX];
} delta_config_t;

static delta_config_t delta_config = { 0 };

int delta_init(delta_kinematics_config_t *config) {
    size_t tower;

    memset(config->limits, 0, sizeof(config->limits));
    for (tower = 0; tower < TOWER_MAX; tower++) {
        delta_config.base_height[tower] =
            sqrtf(SQ(config->arm_length) - SQ(config->tower_radius));
        config->limits[AXIS_TYPE_A + tower].min =
            delta_config.base_height[tower];
        config->limits[AXIS_TYPE_A + tower].max =
            delta_config.base_height[tower] + config->z_length;
        delta_config.tower_position[tower].x =
            config->tower_radius *
            cosf(config->tower_angle[tower] * M_PI / 180.0f);
        delta_config.tower_position[tower].y =
            config->tower_radius *
            sinf(config->tower_angle[tower] * M_PI / 180.0f);
        delta_config.tower_position[tower].z = 0.0f;
    }

    memcpy(&delta_config.base_config, config, sizeof(*config));
    for (int i = 0; i < 3; i++) {
        printf("Actuator %d: base=(%.2f, %.2f, %.2f)\n", i + 1,
               delta_config.tower_position[i].x,
               delta_config.tower_position[i].y,
               delta_config.tower_position[i].z);
    }
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
    *position = *axis_positions;
    return 0;
}

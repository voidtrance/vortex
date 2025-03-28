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

/*
 * https://corexy.com/theory.html
 */
#include "corexy.h"

int corexy_motor_movement(coordinates_t *delta, coordinates_t *movement) {
    *movement = *delta;
    movement->x = delta->x + delta->y;
    movement->y = delta->x - delta->y;
    return 0;
}

int corexy_axis_movement(coordinates_t *delta, coordinates_t *movement) {
    *movement = *delta;
    movement->x = (delta->x + delta->y) * 0.5;
    movement->y = (delta->x - delta->y) * 0.5;
    return 0;
}

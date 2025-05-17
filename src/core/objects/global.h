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
#ifndef __GLOBAL_H__
#define __GLOBAL_H__

#define PIN_NAME_SIZE 9 /* 8 chars + null */
#define OBJECT_NAME_SIZE 65
#define ENDSTOP_NAME_SIZE OBJECT_NAME_SIZE
#define MOTOR_NAME_SIZE OBJECT_NAME_SIZE
#define TOOLHEAD_NAME_SIZE OBJECT_NAME_SIZE
#define HEATER_NAME_SIZE OBJECT_NAME_SIZE
#define HEAT_SENSOR_NAME_SIZE OBJECT_NAME_SIZE

#endif
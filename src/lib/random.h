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
#ifndef __RANDOM_H__
#define __RANDOM_H__
#include <stdint.h>

#define CREATE_FUNCS(name, type)					\
    type random_##name(void);						\
    type random_##name##_limit(type min, type max);

CREATE_FUNCS(int, int32_t)
CREATE_FUNCS(uint, unsigned int)
CREATE_FUNCS(uint64, uint64_t)
CREATE_FUNCS(float, float)

#endif

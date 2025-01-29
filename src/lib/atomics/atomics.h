/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024,2025  Mitko Haralanov
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
#ifndef __ATOMICS_H__
#define __ATOMICS_H__
#include <stdint.h>

#ifndef MULTI_INCLUDE
#define DEFINE_FUNCS(size, type)                                               \
    type atomic##size##_load(type *ptr);                                       \
    void atomic##size##_store(type *ptr, type value);                          \
    type atomic##size##_exchange(type *ptr, type value);                       \
    type atomic##size##_compare_exchange(type *ptr, type oldval, type newval); \
    type atomic##size##_add(type *ptr, type value);                            \
    type atomic##size##_sub(type *ptr, type value);                            \
    type atomic##size##_inc(type *ptr);                                        \
    type atomic##size##_dec(type *ptr);                                        \
    type atomic##size##_and(type *ptr, type value);                            \
    type atomic##size##_or(type *ptr, type value);                             \
    type atomic##size##_xor(type *ptr, type value);                            \
    type atomic##size##_not(type *ptr);
#endif

DEFINE_FUNCS(8, uint8_t)
DEFINE_FUNCS(16, uint16_t)
DEFINE_FUNCS(32, uint32_t)
DEFINE_FUNCS(64, uint64_t)
#endif
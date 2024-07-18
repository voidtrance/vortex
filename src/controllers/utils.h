/*
 * gEmulator - GCode machine emulator
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
#ifndef __UTILS_H__
#define __UTILS_H__
#include <stdint.h>

#define SEC_TO_MSEC(x) ((uint64_t)(x)*1000)
#define MSEC_TO_USEC(x) SEC_TO_MSEC(x)
#define SEC_TO_USEC(x) (SEC_TO_MSEC(x) * 1000)
#define MSEC_TO_NSEC(x) SEC_TO_USEC(x)
#define SEC_TO_NSEC(x) (SEC_TO_USEC(x) * 1000)
#define KHZ_TO_HZ(x) ((x)*1000)
#define MHZ_TO_HZ(x) (KHZ_TO_HZ(x)*1000)
#define GHZ_TO_HZ(x) (MHZ_TO_HZ(x)*1000)
#define MHZ_TO_NSEC(x) (1000 / (x))
#define GHZ_TO_NSEC(x) (1/(x))
#define HZ_TO_NSEC(x) MHZ_TO_NSEC((x) / MHZ_TO_HZ(1))

#define max(a, b) ((a <= (typeof(a))b) ? b : a)
#define min(a, b) ((a <= (typeof(a))b) ? a : b)

uint32_t str_to_hertz(const char *str);

#endif

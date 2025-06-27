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
#ifndef __UTILS_H__
#define __UTILS_H__
#include <stdint.h>
#include <stddef.h>

#define __stringify(x) #x
#define stringify(x) __stringify(x)

#define likely(x) (__builtin_expect(!!(x), 1))
#define unlikely(x) (__builtin_expect(!!(x), 0))
#define container_of(ptr, type, member) ((type *)((unsigned long)(ptr) - offsetof(type, member)))

#define SEC_TO_MSEC(x) ((uint64_t)(x)*1000)
#define MSEC_TO_USEC(x) SEC_TO_MSEC(x)
#define SEC_TO_USEC(x) (SEC_TO_MSEC(x) * 1000)
#define MSEC_TO_NSEC(x) SEC_TO_USEC(x)
#define SEC_TO_NSEC(x) (SEC_TO_USEC(x) * 1000)
#define KHZ_TO_HZ(x) ((x)*1000)
#define MHZ_TO_HZ(x) (KHZ_TO_HZ(x)*1000)
#define GHZ_TO_HZ(x) (MHZ_TO_HZ(x)*1000)
#define MHZ_TO_NSEC(x) (1000 * (x))
#define GHZ_TO_NSEC(x) ((x))
#define HZ_TO_NSEC(x) (SEC_TO_NSEC(1) / (x))

#define max(a, b) ({__typeof__(a) _a = a;       \
            __typeof__(b) _b = b;               \
            _a <= _b ? _b : _a; })
#define min(a, b) ({__typeof__(a) _a = a;       \
            __typeof__(b) _b = b;               \
            _a <= _b ? _a : _b; })

static inline double clamp(double d, double min, double max) {
    const double t = d < min ? min : d;
    return t > max ? max : t;
}

#define ARRAY_SIZE(x) (sizeof(x) / sizeof(x[0]))

uint32_t str_to_hertz(const char *str);

#endif

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
#define _GNU_SOURCE
#include <pthread.h>
#include <stdlib.h>
#include <values.h>
#include "random.h"

static pthread_once_t random_init = PTHREAD_ONCE_INIT;

#define MAX_RANDOM ((1U << 31) - 1)

static void random_state_init(void) {
    struct timespec t;
    int16_t i, tries;

    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    srandom(t.tv_nsec);
    tries = (uint16_t)random() % 50;
    for (i = 0; i < tries; i++)
        (void)random();
    return;
}

#undef CREATE_FUNCS
#define CREATE_FUNCS(name, type)                                        \
    type random_##name(void) {                                          \
        pthread_once(&random_init, random_state_init);                  \
        return (type)random();                                          \
    }                                                                   \
    type random_##name##_limit(type min, type max) {                    \
        float factor;                                                   \
        pthread_once(&random_init, random_state_init);                  \
        factor = (float)random() / (float)MAX_RANDOM;                   \
        return (type)((float)min + ((float)(max - min) * factor));      \
    }

CREATE_FUNCS(int, int32_t)
CREATE_FUNCS(uint, uint32_t)
CREATE_FUNCS(uint64, uint64_t)
CREATE_FUNCS(float, float)
CREATE_FUNCS(double, double)

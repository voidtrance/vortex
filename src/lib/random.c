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
#include <pthread.h>
#include <stdlib.h>
#include <errno.h>
#include "random.h"

static pthread_once_t random_init = PTHREAD_ONCE_INIT;

static float long_to_float(long v) {
    return ((v * 1.0) / ((1U << 31) - 1));
}

static void random_state_init(void) {
    struct timespec t;
    int32_t i, tries;

    clock_gettime(CLOCK_MONOTONIC_RAW, &t);
    srandom(t.tv_nsec);
    tries = (uint32_t)(50.0 * long_to_float(random()));
    for (i = 0; i < tries; i++)
        (void)random();
    return;
}

#undef CREATE_FUNCS
#define CREATE_FUNCS(name, type)					\
    type random_##name(void) {                              \
        pthread_once(&random_init, random_state_init);			\
        return (type)random();                              \
    }                                                       \
    type random_##name##_limit(type min, type max) {        \
        float factor = random_float();                          \
        return (type)(min + (((max - min) * 1.0) / factor));		\
    }

CREATE_FUNCS(int, int32_t)
CREATE_FUNCS(uint, uint32_t)
CREATE_FUNCS(uint64, uint64_t)

float random_float(void) {
    pthread_once(&random_init, random_state_init);
    return long_to_float(random());
}

float random_float_limit(float min, float max) {
    float factor = random_float();
    return min + ((max - min) * factor);
}

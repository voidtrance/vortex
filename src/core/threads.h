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
#ifndef __THREAD_CONTROL_H__
#define __THREAD_CONTROL_H__
#include <stdint.h>
#include "common_defs.h"

typedef enum {
    CORE_THREAD_TYPE_UPDATE,
    CORE_THREAD_TYPE_TIMER,
    CORE_THREAD_TYPE_OBJECT,
    CORE_THREAD_TYPE_WORKER,
} core_thread_type_t;

typedef struct {
    union {
	struct {
	    uint64_t tick_frequency;
	    uint64_t update_frequency;
	} update;
	struct {
	    void (*callback)(uint64_t, void *);
	    void *data;
	} timer;
	struct {
	    core_object_t *object;
	    const char *name;
	} object;
	struct {
	    uint64_t frequency;
	    void (*callback)(void *);
	    void *data;
	} worker;
    };
} core_thread_args_t;

int core_thread_create(core_thread_type_t type, core_thread_args_t *args);
int core_threads_start(void);
void core_threads_stop(void);
uint64_t core_get_clock_ticks(void);
uint64_t core_get_runtime(void);
void core_threads_pause(void);
void core_threads_resume(void);
void core_threads_destroy(void);

#endif

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


typedef void (*work_callback_t)(void *user_data);

int controller_thread_create(core_object_t *object, const char *name);
int controller_timer_thread_create(uint64_t frequency,
				   uint64_t update_frequency);
int controller_work_thread_create(work_callback_t callback, void *user_data,
				  uint64_t frequency);
int controller_thread_start(void);
void controller_thread_stop(void);
uint64_t controller_thread_get_clock_ticks(void);
uint64_t controller_thread_get_runtime(void);
void controller_thread_pause(void);
void controller_thread_resume(void);
void controller_thread_destroy(void);

#endif

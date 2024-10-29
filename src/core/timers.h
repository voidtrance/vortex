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
#ifndef __TIMERS_H__
#define __TIMERS_H__

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    uint64_t (*callback)(uint64_t ticks, void *data);
    void *data;
} core_timer_t;

typedef uint64_t core_timer_handle_t;

int core_timers_init(void);
core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout);
int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout);
void core_timer_unregister(core_timer_handle_t handle);
void core_timers_disarm(void);
void core_timers_free(void);

#endif

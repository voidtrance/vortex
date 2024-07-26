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
#ifndef __TIMING_H__
#define __TIMING_H__
#include <stdint.h>

typedef void (*update_callback_t)(uint64_t ticks, uint64_t runtime,
				  void *user_data);
typedef void (*work_callback_t)(void *user_data);

int controller_timer_start(update_callback_t update_cb,
			   uint64_t update_frequency,
			   work_callback_t work_cb, uint64_t work_frequency,
			   void *user_data);
int64_t controller_timer_stop(void);

#endif

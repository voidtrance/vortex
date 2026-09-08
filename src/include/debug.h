/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2026 Mitko Haralanov
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
#ifndef __DEBUG_H__
#define __DEBUG_H__

#ifdef VORTEX_DEBUG
#include <stdio.h>
#include <signal.h>
#define dbg_print(f, ...)                  \
    ({                                     \
        fprintf(stderr, f, ##__VA_ARGS__); \
        fflush(stdout);                    \
    })
#define breakpoint() raise(SIGSEGV)
#else
#define breakpoint()
#define dbg_print(f, ...)
#define printf(f, ...)
#define fprintf(s, ...)
#endif

#endif
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
#ifndef __DEBUG_H__
#define __DEBUG_H__
#ifdef VORTEX_MEM_LEAK
#include "mem_debug.h"
#endif

typedef enum {
    LOG_LEVEL_NOTSET = 0,
    LOG_LEVEL_DEBUG = 10,
    LOG_LEVEL_INFO = 20,
    LOG_LEVEL_WARNING = 30,
    LOG_LEVEL_ERROR = 40,
    LOG_LEVEL_CRITICAL = 50,
    LOG_LEVEL_MAX,
} core_log_level_t;

#define CORE_LOG(obj, level, fmt, ...)				\
    (((core_object_t *)(obj))->call_data.log(			\
	(level), ((core_object_t *)(obj))->type,		\
	((core_object_t *)(obj))->name, (fmt), ##__VA_ARGS__))

#define log_fatal(o, fmt, ...) CORE_LOG(o, LOG_LEVEL_FATAL, fmt, ##__VA_ARGS__)
#define log_error(o, fmt, ...) CORE_LOG(o, LOG_LEVEL_ERROR, fmt, ##__VA_ARGS__)
#define log_warning(o, fmt, ...) \
    CORE_LOG(o, LOG_LEVEL_WARNING, fmt, ##__VA_ARGS__)
#define log_info(o, fmt, ...) CORE_LOG(o, LOG_LEVEL_INFO, fmt, ##__VA_ARGS__)
#define log_verbose(o, fmt, ...) \
    CORE_LOG(o, LOG_LEVEL_VERBOSE, fmt, ##__VA_ARGS__)
#define log_debug(o, fmt, ...) CORE_LOG(o, LOG_LEVEL_DEBUG, fmt, ##__VA_ARGS__)

#endif

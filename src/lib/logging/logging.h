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
#ifndef __LOGGING_H__
#define __LOGGING_H__
#include <stddef.h>

typedef enum {
    LOG_LEVEL_NOTSET,
    LOG_LEVEL_DEBUG,
    LOG_LEVEL_VERBOSE,
    LOG_LEVEL_INFO,
    LOG_LEVEL_WARNING,
    LOG_LEVEL_ERROR,
    LOG_LEVEL_CRITICAL,
    LOG_LEVEL_MAX
} log_level_t;

const char *log_level_names[LOG_LEVEL_MAX] = { "NOTSET",  "DEBUG",   "VERBOSE",
                                               "INFO",    "WARNING", "ERROR",
                                               "CRITICAL" };

typedef struct logger vortex_logger_t;

int vortex_logging_init(const char *logfile);
int vortex_logging_set_extended(bool extended);
int vortex_logging_set_level(log_level_t level);
log_level_t vortex_logging_get_level(void);
int vortex_logging_add_filter(const char *filter);
int vortex_logger_create(const char *name, vortex_logger_t **logger);
int vortex_logger_set_prefix(vortex_logger_t *logger, const char *prefix);
int vortex_logger_log(vortex_logger_t *logger, log_level_t level,
                      const char *filename, size_t line, const char *format,
                      ...);
void vortex_logger_destroy(vortex_logger_t *logger);
void vortex_logging_deinit(void);

#endif
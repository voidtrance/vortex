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
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include <stdarg.h>
#include <time.h>
#include <pthread.h>
#include "logging.h"

typedef struct log_token {
    const char *token;
    size_t len;
} log_token_t;

struct logger {
    char *name;
    char *prefix;
    log_token_t **tokens;
    size_t n_tokens;
};

typedef struct {
    log_token_t **tokens;
    size_t n_tokens;
    bool final;
} filter_t;

typedef struct log_setup {
    log_level_t level;
    char *logfile;
    FILE *stream;
    filter_t *filters;
    size_t n_filters;
    bool extended;
    uint64_t inital_logtime;
    pthread_mutex_t lock;
} log_setup_t;

static log_setup_t *log_setup = NULL;

static void free_tokens(log_token_t **tokens, size_t n_tokens) {
    for (size_t i = 0; i < n_tokens; i++) {
        free((void *)tokens[i]->token);
        free(tokens[i]);
    }

    free(tokens);
}

static int parse_tokens(log_token_t ***tokens, size_t *n_tokens,
                        const char *name) {
    char *ptr = (char *)name;
    char *sep_ptr;
    void *new_tokens;

    if (!name || strlen(name) == 0)
        return EINVAL;

    // The name is going to have at least on token.
    do {
        log_token_t *token;
        size_t n_chars;

        token = malloc(sizeof(log_token_t));
        if (!token)
            return ENOMEM;

        sep_ptr = strchr(ptr, '.');
        if (!sep_ptr)
            n_chars = strlen(ptr);
        else
            n_chars = sep_ptr - ptr;

        token->token = strndup(ptr, n_chars);
        token->len = n_chars;

        new_tokens = realloc(*tokens, sizeof(log_token_t *) * (*n_tokens + 1));
        if (!new_tokens) {
            free((void *)token->token);
            free(token);
            return ENOMEM;
        }

        *tokens = new_tokens;
        (*tokens)[*n_tokens] = token;
        *n_tokens += 1;
        ptr += n_chars + 1;
    } while (sep_ptr && *ptr != '\0');

    return 0;
}

static int parse_logger_name(vortex_logger_t *logger, const char *name) {
    if (!logger || !name)
        return -1;

    logger->name = strdup(name);
    if (parse_tokens(&logger->tokens, &logger->n_tokens, name))
        return -1;

    return 0;
}

static int parse_filter(log_setup_t *info, const char *filter) {
    void *filters;

    if (!info || !filter)
        return EINVAL;

    filters = realloc(info->filters, sizeof(filter_t) * (info->n_filters + 1));
    if (!filters)
        return ENOMEM;

    info->filters = filters;

    memset(&info->filters[info->n_filters], 0, sizeof(filter_t));

    /*
     * Check if the filter is final now because strtok() will modify the
     * string by replacing the last '.' with a null terminator.
     */
    if (filter[strlen(filter) - 1] == '.')
        info->filters[info->n_filters].final = true;
    else
        info->filters[info->n_filters].final = false;

    if (parse_tokens(&info->filters[info->n_filters].tokens,
                     &info->filters[info->n_filters].n_tokens, filter))
        return EINVAL;

    /*
    printf("Adding filter: %s\n", filter);
    for (size_t i = 0; i < info->filters[info->n_filters].n_tokens; i++) {
        log_token_t *token = info->filters[info->n_filters].tokens[i];
        printf("  Token %zu: %s\n", i, token->token);
    }
    */

    info->n_filters++;
    return 0;
}

static bool filter_matches(const filter_t *filter,
                           const vortex_logger_t *logger) {
    size_t n_matched_tokens = 0;

    if (logger->n_tokens < filter->n_tokens)
        return false;

    for (size_t i = 0; i < filter->n_tokens; i++) {
        log_token_t *token = filter->tokens[i];

        if (token->len > 1 || token->token[0] != '*') {
            if (strncmp(logger->tokens[i]->token, token->token, token->len) !=
                0)
                return false;
        }

        n_matched_tokens++;
    }

    if (filter->final && n_matched_tokens < logger->n_tokens)
        return false;

    return true;
}

static bool filter_record(const vortex_logger_t *logger) {
    if (!log_setup->n_filters)
        return true;

    for (size_t i = 0; i < log_setup->n_filters; i++) {
        if (filter_matches(&log_setup->filters[i], logger))
            return true;
    }

    return false;
}

static uint64_t get_current_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)(ts.tv_sec * 1000000000 + ts.tv_nsec);
}

static uint64_t get_elapsed_time_ns(log_setup_t *info) {
    return get_current_time_ns() - info->inital_logtime;
}

int vortex_logging_init(const char *logfile) {
    if (log_setup)
        return EEXIST;

    log_setup = malloc(sizeof(log_setup_t));
    if (!log_setup)
        return ENOMEM;

    memset(log_setup, 0, sizeof(log_setup_t));
    log_setup->level = LOG_LEVEL_NOTSET;
    log_setup->logfile = logfile ? strdup(logfile) : NULL;
    log_setup->filters = NULL;
    log_setup->n_filters = 0;
    log_setup->inital_logtime = get_current_time_ns();
    log_setup->extended = false;
    log_setup->stream = NULL;
    pthread_mutex_init(&log_setup->lock, NULL);

    if (logfile) {
        log_setup->stream = fopen(logfile, "a");
        if (!log_setup->stream) {
            free(log_setup->logfile);
            free(log_setup);
            log_setup = NULL;
            return errno;
        }
    } else {
        // Default to stdout if no logfile is provided
        log_setup->stream = stderr;
    }

    return 0;
}

int vortex_logging_set_extended(bool extended) {
    if (!log_setup)
        return EFAULT;

    log_setup->extended = extended;
    return 0;
}

int vortex_logging_set_level(log_level_t level) {
    if (!log_setup)
        return EFAULT;

    if (level < LOG_LEVEL_NOTSET || level >= LOG_LEVEL_MAX)
        return EINVAL;

    log_setup->level = level;
    return 0;
}

log_level_t vortex_logging_get_level(void) {
    if (!log_setup)
        return LOG_LEVEL_NOTSET;

    return log_setup->level;
}

int vortex_logging_add_filter(const char *filter) {
    int status;

    if (!log_setup)
        return EFAULT;

    pthread_mutex_lock(&log_setup->lock);
    status = parse_filter(log_setup, filter);
    pthread_mutex_unlock(&log_setup->lock);
    return status;
}

int vortex_logger_create(const char *name, vortex_logger_t **logger) {
    vortex_logger_t *l;

    l = malloc(sizeof(vortex_logger_t));
    if (!l)
        return ENOMEM;

    memset(l, 0, sizeof(vortex_logger_t));
    if (parse_logger_name(l, name)) {
        free(l);
        return EINVAL;
    }

    /*
    printf("Creating logger: %s\n", l->name);
    for (size_t i = 0; i < l->n_tokens; i++) {
        printf("  Token %zu: %s\n", i, l->tokens[i]->token);
    }
    */

    if (logger)
        *logger = l;

    return 0;
}

int vortex_logger_set_prefix(vortex_logger_t *logger, const char *prefix) {
    if (!logger || !prefix)
        return EFAULT;

    if (logger->prefix)
        free(logger->prefix);

    logger->prefix = strdup(prefix);
    return 0;
}

int vortex_logger_log(vortex_logger_t *logger, log_level_t level,
                      const char *filename, size_t line, const char *format,
                      ...) {
    va_list args;
    uint64_t elapsed_time;

    if (!log_setup || !logger)
        return EFAULT;

    if (level < LOG_LEVEL_NOTSET || level >= LOG_LEVEL_MAX)
        return EINVAL;

    if (level < log_setup->level)
        return 0;

    pthread_mutex_lock(&log_setup->lock);

    /*
     * Filtering is done with the lock held to protect against
     * a filter being added while logging is in progress.
     */
    if (!filter_record(logger)) {
        pthread_mutex_unlock(&log_setup->lock);
        return 0;
    }

    elapsed_time = get_elapsed_time_ns(log_setup);
    fprintf(log_setup->stream, "%.4f ", elapsed_time / 1000.0);

    if (log_setup->extended) {
        fprintf(log_setup->stream, "[%s] %s:%zu: ", log_level_names[level],
                filename, line);
    } else {
        fprintf(log_setup->stream, "[%s] ", log_level_names[level]);
    }

    if (logger->prefix)
        fprintf(log_setup->stream, "%s: ", logger->prefix);

    va_start(args, format);
    vfprintf(log_setup->stream, format, args);
    va_end(args);
    fprintf(log_setup->stream, "\n");
    pthread_mutex_unlock(&log_setup->lock);
    return 0;
}

void vortex_logger_destroy(vortex_logger_t *logger) {
    if (logger) {
        // Free any allocated tokens if necessary
        free_tokens(logger->tokens, logger->n_tokens);
        free(logger);
    }
}

void vortex_logging_deinit(void) {
    if (!log_setup)
        return;

    if (log_setup->stream && log_setup->stream != stderr) {
        fclose(log_setup->stream);
    }

    free(log_setup->logfile);
    for (size_t i = 0; i < log_setup->n_filters; i++) {
        free_tokens(log_setup->filters[i].tokens,
                    log_setup->filters[i].n_tokens);
    }

    free(log_setup->filters);
    pthread_mutex_destroy(&log_setup->lock);
    free(log_setup);
    log_setup = NULL;
}
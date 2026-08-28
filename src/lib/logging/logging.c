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
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <stdarg.h>
#include <time.h>
#include <fcntl.h>
#include <unistd.h>
#include <utils.h>
#include <sys/queue.h>
#include <pthread.h>
#include <debug.h>
#include <cache.h>
#include "logging.h"

#define BLACK "\x1b[38;2;0;0;0m"
#define BLUE "\x1b[38;2;0;0;255m"
#define BRONZE "\x1b[38;2;177;86;15m"
#define CYAN "\x1b[38;2;91;141;222m"
#define EMERALD "\x1b[38;2;80;200;120m"
#define GRAY "\x1b[38;2;128;128;128m"
#define GREEN "\x1b[38;2;0;255;0m"
#define LIGHT_BLUE "\x1b[38;2;0;128;255m"
#define LIGHT_GRAY "\x1b[38;2;224;224;224m"
#define MAGENTA "\x1b[38;2;255;0;255m"
#define ORANGE "\x1b[38;2;255;128;0m"
#define RED "\x1b[38;2;255;0;0m"
#define SKY_BLUE "\x1b[38;2;102;178;255m"
#define WHITE "\x1b[38;2;255;255;255m"
#define YELLOW "\x1b[38;2;255;255;0m"

#define BG_BLACK "\x1b[48;2;0;0;0m"
#define BG_BLUE "\x1b[48;2;0;0;255m"
#define BG_BRONZE "\x1b[48;2;177;86;15m"
#define BG_CYAN "\x1b[48;2;91;141;222m"
#define BG_EMERALD "\x1b[48;2;80;200;120m"
#define BG_GRAY "\x1b[48;2;128;128;128m"
#define BG_GREEN "\x1b[48;2;0;255;0m"
#define BG_LIGHT_BLUE "\x1b[48;2;0;128;255m"
#define BG_LIGHT_GRAY "\x1b[48;2;224;224;224m"
#define BG_MAGENTA "\x1b[48;2;255;0;255m"
#define BG_ORANGE "\x1b[48;2;255;128;0m"
#define BG_RED "\x1b[48;2;255;0;0m"
#define BG_SKY_BLUE "\x1b[48;2;102;178;255m"
#define BG_WHITE "\x1b[48;2;255;255;255m"
#define BG_YELLOW "\x1b[48;2;255;255;0m"

#define END "\x1b[0m"

static char *colors[] = {
    [LOG_LEVEL_NOTSET] = "",       [LOG_LEVEL_DEBUG] = BLUE,     [LOG_LEVEL_VERBOSE] = CYAN,
    [LOG_LEVEL_INFO] = YELLOW,     [LOG_LEVEL_WARNING] = ORANGE, [LOG_LEVEL_ERROR] = RED,
    [LOG_LEVEL_CRITICAL] = BG_RED, [LOG_LEVEL_MAX] = "",
};

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

typedef struct log_stream {
    STAILQ_ENTRY(log_stream) entry;
    FILE *stream;
    log_level_t level;
} log_stream_t;

typedef struct log_setup {
    log_level_t level;
    STAILQ_HEAD(log_stream_list, log_stream) log_streams;
    filter_t *filters;
    size_t n_filters;
    bool extended;
    uint64_t inital_logtime;
    pthread_mutex_t lock;
    object_cache_t *string_cache;
} log_setup_t;

static log_setup_t *log_setup = NULL;

#define LOG_STRING_SIZE 8096

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

int vortex_logging_init(void) {
    if (log_setup)
        return EEXIST;

    log_setup = malloc(sizeof(log_setup_t));
    if (!log_setup)
        return ENOMEM;

    memset(log_setup, 0, sizeof(log_setup_t));
    log_setup->level = LOG_LEVEL_MAX;
    log_setup->filters = NULL;
    log_setup->n_filters = 0;
    log_setup->inital_logtime = get_current_time_ns();
    log_setup->extended = false;
    STAILQ_INIT(&log_setup->log_streams);
    pthread_mutex_init(&log_setup->lock, NULL);
    if (object_cache_create(&log_setup->string_cache, LOG_STRING_SIZE))
        return ENOMEM;

    return 0;
}

int vortex_logging_set_extended(bool extended) {
    if (!log_setup)
        return EFAULT;

    log_setup->extended = extended;
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

int vortex_logging_add_stream(int stream, log_level_t level) {
    FILE *fstream;
    log_stream_t *log_stream;
    char mode[3] = { 0 };
    int flags;

    if (level <= LOG_LEVEL_NOTSET || level >= LOG_LEVEL_MAX)
        return EINVAL;

    if (!log_setup)
        return EFAULT;

    log_stream = malloc(sizeof(*log_stream));
    if (!log_stream)
        return ENOMEM;

    flags = fcntl(stream, F_GETFL);
    if (flags & O_RDONLY)
        return EACCES;

    if (flags & O_APPEND)
        mode[0] = 'a';
    else
        mode[0] = 'w';

    if (flags & O_RDWR)
        mode[1] = '+';

    stream = dup(stream);
    fstream = fdopen(stream, mode);
    if (!fstream) {
        free(log_stream);
        return errno;
    }

    setvbuf(fstream, NULL, _IONBF, 0);
    log_stream->stream = fstream;
    log_stream->level = level;

    pthread_mutex_lock(&log_setup->lock);
    STAILQ_INSERT_TAIL(&log_setup->log_streams, log_stream, entry);
    log_setup->level = min(log_setup->level, level);
    pthread_mutex_unlock(&log_setup->lock);
    return 0;
}

static int remove_stream_locked(int stream) {
    log_stream_t *log_stream_entry;
    log_stream_t *next;

    if (STAILQ_EMPTY(&log_setup->log_streams))
        return ENOENT;

    log_stream_entry = STAILQ_FIRST(&log_setup->log_streams);
    while (log_stream_entry) {
        next = STAILQ_NEXT(log_stream_entry, entry);
        if (fileno(log_stream_entry->stream) == stream) {
            STAILQ_REMOVE(&log_setup->log_streams, log_stream_entry, log_stream,
                          entry);
            break;
        }

        log_stream_entry = next;
    }

    if (!log_stream_entry)
        return ENOENT;

    fclose(log_stream_entry->stream);
    free(log_stream_entry);
    return 0;
}

int vortex_logging_remove_stream(int stream) {
    int ret;

    if (!log_setup)
        return EFAULT;

    pthread_mutex_lock(&log_setup->lock);
    ret = remove_stream_locked(stream);
    pthread_mutex_unlock(&log_setup->lock);
    return ret;
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
    log_stream_t *log_stream;
    log_stream_t *next;
    char *string;
    size_t s = 0;
    bool do_log = true;

    if (!log_setup || !logger)
        return EFAULT;

    if (level < LOG_LEVEL_NOTSET || level >= LOG_LEVEL_MAX)
        return EINVAL;

    if (level < log_setup->level)
        return 0;

    /*
     * Message with levels ERROR and higher (more severe) are
     * not filtered.
     */
    if (level < LOG_LEVEL_ERROR) {
        /*
         * Filtering is done with the lock held to protect against
         * a filter being added while logging is in progress.
         */
        pthread_mutex_lock(&log_setup->lock);
        do_log = filter_record(logger);
        pthread_mutex_unlock(&log_setup->lock);
    }

    if (!do_log)
        return 0;

    string = object_cache_alloc(log_setup->string_cache);

    /*
     * The lock is relase so we dont block other threads while the
     * message is formated. If a filter that would filter out this
     * message is added while the lock is dropped, it OK.
     */
    elapsed_time = get_elapsed_time_ns(log_setup);
    s = snprintf(string, LOG_STRING_SIZE, "%s%.4f%s ", GREEN, elapsed_time / 1000.0, END);
    if (log_setup->extended) {
        s += snprintf(string + s, LOG_STRING_SIZE - s, "[%s%s%s] %s:%zu: ", colors[level],
                      log_level_names[level], END, filename, line);
    } else {
        s += snprintf(string + s, LOG_STRING_SIZE - s, "[%s%s%s] ", colors[level],
                      log_level_names[level], END);
    }

    if (logger->prefix)
        s += snprintf(string + s, LOG_STRING_SIZE - s, "%s%s%s: ", CYAN, logger->prefix, END);

    va_start(args, format);
    s += vsnprintf(string + s, LOG_STRING_SIZE - s, format, args);
    va_end(args);
    if (s < LOG_STRING_SIZE - 1 && format[strlen(format) - 1] != '\n')
        string[s++] = '\n';
    string[s] = '\0';

    pthread_mutex_lock(&log_setup->lock);
    log_stream = STAILQ_FIRST(&log_setup->log_streams);
    while (log_stream) {
        next = STAILQ_NEXT(log_stream, entry);
        if (level < log_stream->level)
            goto next_stream;

        if (fputs(string, log_stream->stream) < 0)
            remove_stream_locked(fileno(log_stream->stream));

next_stream:
        log_stream = next;
    }

    object_cache_free(string);
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
    log_stream_t *log_stream;
    log_stream_t *next;

    if (!log_setup)
        return;

    pthread_mutex_lock(&log_setup->lock);
    for (log_stream = STAILQ_FIRST(&log_setup->log_streams),
        next = STAILQ_NEXT(log_stream, entry);
         log_stream; log_stream = next, next = STAILQ_NEXT(next, entry)) {
        remove_stream_locked(fileno(log_stream->stream));
        if (!next)
            break;
    }

    pthread_mutex_unlock(&log_setup->lock);

    for (size_t i = 0; i < log_setup->n_filters; i++) {
        free_tokens(log_setup->filters[i].tokens,
                    log_setup->filters[i].n_tokens);
    }

    object_cache_destroy(log_setup->string_cache);
    free(log_setup->filters);
    pthread_mutex_destroy(&log_setup->lock);
    free(log_setup);
    log_setup = NULL;
}
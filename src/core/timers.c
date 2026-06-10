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

#ifndef VORTEX_TIMERS_DEBUG
#define VORTEX_TIMERS_DEBUG 0
#define VORTEX_TIMERS_DEBUG_LISTS 0
#endif

#if VORTEX_TIMERS_DEBUG
#include <logging.h>
#else
#define VORTEX_TIMERS_DEBUG_LISTS 0
#endif

#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <core_threads.h>
#include <debug.h>
#include <utils.h>
#include <dlist.h>
#include "timers.h"

#define CHECK_TIMER 0

typedef enum {
    EXECUTE_STATE_NONE = 0,
    EXECUTE_STATE_RUNNABLE,
    EXECUTE_STATE_EXECUTING,
    EXECUTE_STATE_TO_REMOVE,
} execute_state_t;

#if VORTEX_TIMERS_DEBUG_LISTS
static const char *__states[] = {
    [EXECUTE_STATE_NONE] = "NONE",
    [EXECUTE_STATE_RUNNABLE] = "RUNNABLE",
    [EXECUTE_STATE_EXECUTING] = "EXECUTING",
    [EXECUTE_STATE_TO_REMOVE] = "TO_REMOVE",
};
#endif

typedef struct core_timers_entry_struct {
    dlist_t entry;
    core_timer_t timer;
    uint64_t timestamp;
    execute_state_t state;
} core_timers_entry_t;

typedef dlist_t core_timers_list_t;

typedef struct {
#if VORTEX_TIMERS_DEBUG_LISTS
    const char name[16];
#endif
    core_timers_list_t list;
    uint32_t count;
} core_timer_set_t;

typedef struct {
    pthread_mutex_t lock;
    core_timer_set_t armed;
    core_timer_set_t disarmed;
    core_timer_set_t free;
    uint64_t current;
    uint64_t mask;
} core_timers_t;

static core_timers_t timers = {
    .armed = {
#if VORTEX_TIMERS_DEBUG_LISTS
        "ARMED",
#endif
         DLIST_INITIALIZOR(timers.armed.list), 0 },
    .disarmed = {
#if VORTEX_TIMERS_DEBUG_LISTS
        "DISARMED",
#endif
         DLIST_INITIALIZOR(timers.disarmed.list), 0 },
    .free = {
#if VORTEX_TIMERS_DEBUG_LISTS
        "FREE",
#endif
         DLIST_INITIALIZOR(timers.free.list), 0 },
    .lock = PTHREAD_MUTEX_INITIALIZER,
    .current = 0,
    .mask = 0,
};

#if VORTEX_TIMERS_DEBUG
static vortex_logger_t *logger = NULL;
#endif

static void core_timers_update(uint64_t ticks, void *data);

#define get_now() __atomic_load_n(&timers.current, __ATOMIC_SEQ_CST)
#define set_now(ticks) __atomic_store_n(&timers->current, ticks, __ATOMIC_SEQ_CST)

#undef dbg_print
#if VORTEX_TIMERS_DEBUG
#define dbg_print(fmt, ...) \
    vortex_logger_log(logger, LOG_LEVEL_DEBUG, __FILE__, __LINE__, fmt, ##__VA_ARGS__)
#else
#define dbg_print(fmt, ...)
#endif

#if VORTEX_TIMERS_DEBUG_LISTS
#define __dump(op, ticks, timer, set, file, line)                                                  \
    do {                                                                                           \
        core_timers_entry_t *__entry;                                                              \
        char __buffer[1024];                                                                       \
        size_t __i = 0;                                                                            \
        __i += snprintf(__buffer, sizeof(__buffer) - __i, "[%s](%s) [0x%lx,%s,%lu]:", (set)->name, \
                        (op), (unsigned long)(timer), __states[(timer)->state], (ticks));          \
        dlist_for_each_elem_container(__entry, &((set)->list), entry)                              \
            __i += snprintf(__buffer + __i, sizeof(__buffer) - __i,                                \
                            " 0x%lx,%s,%lu:", (unsigned long)__entry, __states[__entry->state],    \
                            __entry->timestamp);                                                   \
        vortex_logger_log(logger, LOG_LEVEL_DEBUG, file, line, "%s", __buffer);                    \
    } while (0)
#define dump(op, ticks, timer, set) __dump(op, ticks, timer, set, __FILE__, __LINE__)
#else
#define dump(op, ticks, timer, set)
#endif

int core_timers_init(uint16_t width) {
    core_thread_args_t args;
#if VORTEX_TIMERS_DEBUG
    int ret;
#endif

    timers.mask = (1UL << width) - 1;
    args.timer.callback = core_timers_update;
    args.timer.data = (void *)&timers;

#if VORTEX_TIMERS_DEBUG
    ret = vortex_logger_create("vortex.core.timers", &logger);
    if (ret)
        return ret;
#endif

    return core_thread_create(CORE_THREAD_TYPE_TIMER, &args);
}

static void timer_arm_locked(core_timers_entry_t *timer) {
    core_timers_entry_t *entry;
    core_timer_set_t *set = &timers.armed;

    if (unlikely(dlist_is_empty(&set->list)))
        goto insert_back;

    dlist_for_each_elem_container(entry, &set->list, entry) {
        if (core_timers_compare(timer->timestamp, entry->timestamp) <= 0) {
            dlist_elem_insert_tail(&timer->entry, &entry->entry);
            goto inserted;
        }
    }

insert_back:
    dlist_elem_insert_tail(&timer->entry, &set->list);

inserted:
    timer->state = EXECUTE_STATE_RUNNABLE;
    set->count++;
    dump("ARM", get_now(), timer, &timers.armed);
}

static void timer_arm(core_timers_entry_t *timer) {
    pthread_mutex_lock(&timers.lock);
    timer_arm_locked(timer);
    pthread_mutex_unlock(&timers.lock);
}

static void timer_disarm_locked(core_timers_entry_t *timer) {
    timer->state = EXECUTE_STATE_NONE;
    dlist_elem_insert_tail(&timer->entry, &timers.disarmed.list);
    dump("DISARM", get_now(), timer, &timers.disarmed);
}

static void timer_disarm(core_timers_entry_t *timer) {
    pthread_mutex_lock(&timers.lock);
    timer_disarm_locked(timer);
    pthread_mutex_unlock(&timers.lock);
}

static void timer_remove_locked(core_timers_entry_t *timer) {
    dlist_elem_remove(&timer->entry);
    dump("REMOVE", get_now(), timer,
         timer->state == EXECUTE_STATE_RUNNABLE ? &timers.armed : &timers.disarmed);
    if (timer->state == EXECUTE_STATE_RUNNABLE)
        timers.armed.count--;
    else
        timers.disarmed.count--;
}

core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout) {
    core_timers_entry_t *new_timer;

    timeout &= timers.mask;

    new_timer = malloc(sizeof(*new_timer));
    if (!new_timer) {
        errno = -ENOMEM;
        return 0;
    }

    new_timer->timer = timer;
    new_timer->timestamp = timeout;
    new_timer->state = EXECUTE_STATE_NONE;

    if (timeout)
        timer_arm(new_timer);
    else
        timer_disarm(new_timer);

    dump("REGISTER", get_now(), new_timer, timeout ? &timers.armed : &timers.disarmed);
    return (core_timer_handle_t)new_timer;
}

int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout) {
    core_timers_entry_t *timer = (core_timers_entry_t *)handle;

    timeout &= timers.mask;

    pthread_mutex_lock(&timers.lock);
    timer_remove_locked(timer);
    timer->timestamp = timeout;
    if (timeout)
        timer_arm_locked(timer);
    else
        timer_disarm_locked(timer);

    dump("RESCHEDULE", get_now(), timer, timeout ? &timers.armed : &timers.disarmed);
    pthread_mutex_unlock(&timers.lock);
    return 0;
}

void core_timer_unregister(core_timer_handle_t handle) {
    core_timers_entry_t *timer = (core_timers_entry_t *)handle;
    execute_state_t state;

    pthread_mutex_lock(&timers.lock);
    state = timer->state;
    state = EXECUTE_STATE_TO_REMOVE;
    if (state != EXECUTE_STATE_EXECUTING) {
        dump("UNREGISTER", get_now(), timer,
             timer->state == EXECUTE_STATE_RUNNABLE ? &timers.armed : &timers.disarmed);
        timer_remove_locked(timer);
        dlist_elem_insert_tail(&timer->entry, &timers.free.list);
    }

    pthread_mutex_unlock(&timers.lock);
}

int core_timers_compare(uint64_t timeout1, uint64_t timeout2) {
    return (int)((timeout1 & timers.mask) - (timeout2 & timers.mask));
}

static void core_timers_update(uint64_t ticks, void *data) {
    core_timers_t *timers = (core_timers_t *)data;
    core_timers_entry_t *timer;
    core_timers_entry_t *next;
    uint64_t reschedule = 0;

    set_now(ticks);
    pthread_mutex_lock(&timers->lock);
    dlist_for_each_elem_container_safe(timer, next, &timers->free.list, entry) {
        dlist_elem_remove(&timer->entry);
        free(timer);
    }

    dlist_for_each_elem_container_safe(timer, next, &timers->armed.list, entry) {
        if (timer->state != EXECUTE_STATE_RUNNABLE)
            break;

        dump("CHECK", ticks, timer, &timers->armed);
        if (core_timers_compare(timer->timestamp, ticks) > 0)
            break;

        if (timer->state == EXECUTE_STATE_RUNNABLE) {
            timer->state = EXECUTE_STATE_EXECUTING;
            pthread_mutex_unlock(&timers->lock);
            reschedule = timer->timer.callback(ticks, timer->timer.data);
            pthread_mutex_lock(&timers->lock);
        }

        switch (timer->state) {
        case EXECUTE_STATE_EXECUTING:
            timer_remove_locked(timer);
            timer->timestamp = reschedule & timers->mask;
            if (timer->timestamp)
                timer_arm_locked(timer);
            else
                timer_disarm_locked(timer);

            dump("UPDATE", ticks, timer, &timers->armed);
            break;
        case EXECUTE_STATE_TO_REMOVE:
            timer_remove_locked(timer);
            free(timer);
        default:

            break;
        }
    }

    pthread_mutex_unlock(&timers->lock);
    return;
}

void core_timers_disarm(void) {
    core_timers_entry_t *timer;
    core_timers_entry_t *next;

    pthread_mutex_lock(&timers.lock);
    dlist_for_each_elem_container_safe(timer, next, &timers.armed.list, entry) {
        timer_remove_locked(timer);
        timer_disarm_locked(timer);
    }

    pthread_mutex_unlock(&timers.lock);
}

void core_timers_free(void) {
    core_timers_entry_t *timer;
    core_timers_entry_t *next;

    pthread_mutex_lock(&timers.lock);
    dlist_for_each_elem_container_safe(timer, next, &timers.armed.list, entry) {
        timer_remove_locked(timer);
        free(timer);
    }

    dlist_for_each_elem_container_safe(timer, next, &timers.disarmed.list, entry) {
        timer_remove_locked(timer);
        free(timer);
    }

    pthread_mutex_unlock(&timers.lock);
    pthread_mutex_destroy(&timers.lock);
#if VORTEX_TIMERS_DEBUG
    vortex_logger_destroy(logger);
#endif
}

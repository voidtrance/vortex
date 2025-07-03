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

#define TIMER_DEBUG 0
#if TIMER_DEBUG
#include <stdio.h>
#endif
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/queue.h>
#include <core_threads.h>
#include <debug.h>
#include <utils.h>
#include <atomics.h>
#include "timers.h"

#define CHECK_TIMER 0

typedef enum {
    EXECUTE_STATE_NONE = 0,
    EXECUTE_STATE_EXECUTING,
    EXECUTE_STATE_TO_REMOVE,
    EXECUTE_STATE_REMOVED,
} execute_state_t;

typedef struct core_timers_entry_struct {
    CIRCLEQ_ENTRY(core_timers_entry_struct) entry;
    core_timer_t timer;
    uint64_t timestamp;
    bool armed;
    execute_state_t state;
} core_timers_entry_t;

/* Some useful CIRCLEQ macros which are aren't provided. */
#define CIRCLEQ_FOREACH_SAFE(elm, next, head, field)                  \
    for ((elm) = ((head)->cqh_first), (next) = (elm)->field.cqe_next; \
         (elm) != (const void *)(head);                               \
         (elm) = (next), (next) = (next)->field.cqe_next)

typedef CIRCLEQ_HEAD(core_timers_list,
                     core_timers_entry_struct) core_timers_list_t;

typedef struct {
    core_timers_list_t list;
    uint32_t count;
} core_timer_set_t;

typedef struct {
    pthread_mutex_t lock;
    core_timer_set_t armed;
    core_timer_set_t disarmed;
    uint64_t current;
    uint64_t mask;
} core_timers_t;

static core_timers_t timers = {
    .armed = { CIRCLEQ_HEAD_INITIALIZER(timers.armed.list), 0 },
    .disarmed = { CIRCLEQ_HEAD_INITIALIZER(timers.disarmed.list), 0 },
    .lock = PTHREAD_MUTEX_INITIALIZER,
    .current = 0,
    .mask = 0,
};

static void core_timers_update(uint64_t ticks, void *data);

#define get_now() __atomic_load_n(&timers.current, __ATOMIC_SEQ_CST);
#define set_now(ticks) \
    __atomic_store_n(&timers->current, ticks, __ATOMIC_SEQ_CST);

#if TIMER_DEBUG
FILE *__timer_fd;
#define dump(ticks, timer, list)                                          \
    do {                                                                  \
        core_timers_entry_t *__entry;                                     \
        fprintf(__timer_fd, "[%lu,0x%lx]:", ticks, (unsigned long)timer); \
        CIRCLEQ_FOREACH(__entry, list, entry)                             \
            fprintf(__timer_fd, "0x%lx,%lu:", (unsigned long)__entry,     \
                    __entry->timestamp);                                  \
        fprintf(__timer_fd, "\n");                                        \
        fflush(__timer_fd);                                               \
    } while (0)
#endif

int core_timers_init(uint16_t width) {
    core_thread_args_t args;

    timers.mask = (1UL << width) - 1;
    args.timer.callback = core_timers_update;
    args.timer.data = (void *)&timers;

#if TIMER_DEBUG
    __timer_fd = fopen("timer.debug", "w");
    if (!__timer_fd) {
        perror("Failed to open timer.debug");
        return -1;
    }
#endif

    return core_thread_create(CORE_THREAD_TYPE_TIMER, &args);
}

static void timer_arm_locked(core_timers_entry_t *timer) {
    core_timers_entry_t *entry;
    core_timer_set_t *set = &timers.armed;

    if (unlikely(CIRCLEQ_EMPTY(&set->list)))
        goto insert_back;

    CIRCLEQ_FOREACH(entry, &set->list, entry) {
        if (core_timers_compare(timer->timestamp, entry->timestamp) <= 0) {
            CIRCLEQ_INSERT_BEFORE(&set->list, entry, timer, entry);
            goto inserted;
        }
    }

insert_back:
    CIRCLEQ_INSERT_TAIL(&set->list, timer, entry);

inserted:
    timer->armed = true;
    set->count++;
}

static void timer_arm(core_timers_entry_t *timer) {
    pthread_mutex_lock(&timers.lock);
    timer_arm_locked(timer);
    pthread_mutex_unlock(&timers.lock);
}

static void timer_disarm_locked(core_timers_entry_t *timer) {
    timer->armed = false;
    CIRCLEQ_INSERT_TAIL(&timers.disarmed.list, timer, entry);
}

static void timer_disarm(core_timers_entry_t *timer) {
    pthread_mutex_lock(&timers.lock);
    timer_disarm_locked(timer);
    pthread_mutex_unlock(&timers.lock);
}

static void timer_remove_locked(core_timers_entry_t *timer) {
    if (timer->armed) {
        CIRCLEQ_REMOVE(&timers.armed.list, timer, entry);
        timers.armed.count--;
    } else {
        CIRCLEQ_REMOVE(&timers.disarmed.list, timer, entry);
        timers.disarmed.count--;
    }
}

#if 0
static void timer_remove(core_timers_entry_t *timer) {
    pthread_mutex_lock(&timers.lock);
    timer_remove_locked(timer);
    pthread_mutex_unlock(&timers.lock);
}
#endif

core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout) {
    core_timers_entry_t *new_timer;

    timeout &= timers.mask;

#if CHECK_TIMER
    if (timeout && timeout <= get_now())
        return CORE_TIMER_ERROR;
#endif

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

    return (core_timer_handle_t)new_timer;
}

int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout) {
    core_timers_entry_t *timer = (core_timers_entry_t *)handle;

    timeout &= timers.mask;

#if CHECK_TIMER
    if (timeout && timeout <= get_now())
        return -1;
#endif

    pthread_mutex_lock(&timers.lock);
    timer_remove_locked(timer);
    timer->timestamp = timeout;
    if (timeout)
        timer_arm_locked(timer);
    else
        timer_disarm_locked(timer);

    pthread_mutex_unlock(&timers.lock);
    return 0;
}

void core_timer_unregister(core_timer_handle_t handle) {
    core_timers_entry_t *timer = (core_timers_entry_t *)handle;
    execute_state_t state;

    pthread_mutex_lock(&timers.lock);
    state = atomic32_exchange(&timer->state, EXECUTE_STATE_TO_REMOVE);
    if (state == EXECUTE_STATE_NONE) {
        atomic32_store(&timer->state, EXECUTE_STATE_REMOVED);
        timer_remove_locked(timer);
        free(timer);
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
    CIRCLEQ_FOREACH_SAFE(timer, next, &timers->armed.list, entry) {
        if (core_timers_compare(timer->timestamp, ticks) > 0)
            break;

        pthread_mutex_unlock(&timers->lock);
        if (atomic32_compare_exchange(&timer->state, EXECUTE_STATE_NONE,
                                      EXECUTE_STATE_EXECUTING))
            reschedule = timer->timer.callback(ticks, timer->timer.data);
        pthread_mutex_lock(&timers->lock);
        if (!atomic32_compare_exchange(&timer->state, EXECUTE_STATE_EXECUTING,
                                       EXECUTE_STATE_NONE)) {
            if (atomic32_load(&timer->state) == EXECUTE_STATE_TO_REMOVE) {
                timer_remove_locked(timer);
                free(timer);
            }

            continue;
        }

        timer_remove_locked(timer);
        timer->timestamp = reschedule & timers->mask;
        if (timer->timestamp) {
            timer_arm_locked(timer);
        } else {
            timer_disarm_locked(timer);
        }
#if TIMER_DEBUG
        dump(ticks, timer, &timers->armed.list);
#endif

        /*
         * There is a race condition with handling of the timers
         * that needs special handling:
         *   1. At iterations N, both timer and next are timers
         *      on the armed list.
         *   2. The timers lock is released above before calling
         *      timer's callback.
         *   3. During the callback's execution, next gets disarmed.
         *      This can happen because during the callback's
         *      execution, the timers locks is unlocked.
         *   4. When the callback completes, the timers lock is
         *      locked and timer is assigned to next. (next is now
         *      on the disarmed list.)
         *   5. The new next is now the head of the disarmed list.
         *   6. On the next iteration, timer is assigned to the
         *      head of the disarmed list.
         */
        if (!next->armed)
            break;
    }

    pthread_mutex_unlock(&timers->lock);
    return;
}

void core_timers_disarm(void) {
    core_timers_entry_t *timer;
    core_timers_entry_t *next;

    pthread_mutex_lock(&timers.lock);
    CIRCLEQ_FOREACH_SAFE(timer, next, &timers.armed.list, entry) {
        timer_remove_locked(timer);
        timer_disarm_locked(timer);
    }

    pthread_mutex_unlock(&timers.lock);
}

void core_timers_free(void) {
    core_timers_entry_t *timer;
    core_timers_entry_t *next;

#if TIMER_DEBUG
    if (__timer_fd)
        fclose(__timer_fd);
#endif

    pthread_mutex_lock(&timers.lock);
    CIRCLEQ_FOREACH_SAFE(timer, next, &timers.armed.list, entry) {
        timer_remove_locked(timer);
        free(timer);
    }
    CIRCLEQ_FOREACH_SAFE(timer, next, &timers.disarmed.list, entry) {
        timer_remove_locked(timer);
        free(timer);
    }
    pthread_mutex_unlock(&timers.lock);
    pthread_mutex_destroy(&timers.lock);
}

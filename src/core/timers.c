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
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <sys/queue.h>
#include <threads.h>
#include <debug.h>
#include "timers.h"

#define CHECK_TIMER 0

typedef struct core_timers_entry_struct {
    CIRCLEQ_ENTRY(core_timers_entry_struct) entry;
    core_timer_t timer;
    uint64_t timestamp;
    bool armed;
} core_timers_entry_t;

/* Some useful CIRCLEQ macros which are aren't provided. */
#define CIRCLEQ_REMOVE_INIT(head, elm, field)                   \
    do {                                                        \
        CIRCLEQ_REMOVE(head, elm, field);                       \
        (elm)->entry.cqe_next = (elm)->entry.cqe_prev = (elm);  \
    } while (0)
#define CIRCLEQ_IN_LIST(elm, field)                                     \
    ((elm)->entry.cqe_next != (elm) && (elm)->entry.cqe_prev != (elm))
#define CIRCLEQ_FOREACH_SAFE(elm, next, head, field)                  \
    for ((elm) = ((head)->cqh_first), (next) = (elm)->field.cqe_next;	\
         (elm) != (const void *)(head);                               \
         (elm) = (next), (next) = (next)->field.cqe_next)

typedef CIRCLEQ_HEAD(core_timers_list,
                     core_timers_entry_struct) core_timers_list_t;

typedef struct {
    core_timers_list_t list;
    pthread_mutex_t lock;
} core_timer_set_t;

typedef struct {
    core_timer_set_t armed;
    core_timer_set_t disarmed;
    uint64_t current;
    uint64_t mask;
} core_timers_t;

static core_timers_t timers = {
    .armed.list = CIRCLEQ_HEAD_INITIALIZER(timers.armed.list),
    .armed.lock = PTHREAD_MUTEX_INITIALIZER,
    .disarmed.list = CIRCLEQ_HEAD_INITIALIZER(timers.disarmed.list),
    .disarmed.lock = PTHREAD_MUTEX_INITIALIZER,
    .current = 0,
    .mask = 0,
};

#ifdef VORTEX_DEBUG
static struct __timer_check_struct {
    core_timer_handle_t handles[64];
    void *lists[5];
    size_t index;
} __timer_check = { 0 };

static void __do_timer_check(core_timer_handle_t handle,
                             core_timers_list_t *list) {
    size_t i;
    for (i = 0; i < __timer_check.index; i++) {
        if (__timer_check.handles[i] == handle)
            return;
    }
    if (!list || (list && (core_timer_handle_t)list == handle))
        return;
    breakpoint();
}
#endif

static void core_timers_update(uint64_t ticks, void *data);

int core_timers_init(uint16_t width) {
    core_thread_args_t args;

#ifdef VORTEX_DEBUG
    __timer_check.lists[0] = &timers.armed.list;
    __timer_check.lists[1] = &timers.disarmed.list;
#endif

    timers.mask = (1UL << width) - 1;
    args.timer.callback = core_timers_update;
    args.timer.data = (void *)&timers;
    return core_thread_create(CORE_THREAD_TYPE_TIMER, &args);
}

static void core_timers_order(core_timers_list_t *list,
                              core_timers_entry_t *timer) {
    core_timers_entry_t *entry;

    CIRCLEQ_FOREACH(entry, list, entry) {
        if (core_timers_compare(timer->timestamp, entry->timestamp) <= 0) {
            CIRCLEQ_INSERT_BEFORE(list, entry, timer, entry);
            goto inserted;
        }
    }

    CIRCLEQ_INSERT_TAIL(list, timer, entry);

inserted:
    timer->armed = true;
}

core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout) {
    core_timers_entry_t *timers_entry;

    timeout &= timers.mask;

#if CHECK_TIMER
    uint64_t now = __atomic_load_n(&timers.current, __ATOMIC_ACQUIRE);

    if (timeout && timeout <= now)
        return CORE_TIMER_ERROR;
#endif
    timers_entry = malloc(sizeof(*timers_entry));
    if (!timers_entry) {
        errno = -ENOMEM;
        return 0;
    }

    timers_entry->timer = timer;
    timers_entry->timestamp = timeout;

#ifdef VORTEX_DEBUG
    __timer_check.handles[__timer_check.index++] =
        (core_timer_handle_t)timers_entry;
#endif

    if (timeout) {
        timers_entry->armed = true;
        pthread_mutex_lock(&timers.armed.lock);
        core_timers_order(&timers.armed.list, timers_entry);
        pthread_mutex_unlock(&timers.armed.lock);
    } else {
        /* register but disarm timer */
        timers_entry->armed = false;
        pthread_mutex_lock(&timers.disarmed.lock);
        CIRCLEQ_INSERT_TAIL(&timers.disarmed.list, timers_entry, entry);
        pthread_mutex_unlock(&timers.disarmed.lock);
    }

    return (core_timer_handle_t)timers_entry;
}

static void timer_disarm(core_timers_entry_t *timer) {
    timer->armed = false;
    pthread_mutex_lock(&timers.disarmed.lock);
    CIRCLEQ_INSERT_TAIL(&timers.disarmed.list, timer, entry);
    pthread_mutex_unlock(&timers.disarmed.lock);
}

int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout) {
    core_timers_entry_t *timer = (core_timers_entry_t *)handle;

    timeout &= timers.mask;
#ifdef VORTEX_DEBUG
    __do_timer_check(handle, NULL);
#endif
#if CHECK_TIMER
    if (timeout &&
        timeout <= __atomic_load_n(&timers.current, __ATOMIC_ACQUIRE))
        return -1;
#endif

    pthread_mutex_lock(&timers.armed.lock);
    if (!timer->armed) {
        if (timeout == 0)
            goto unlock;

        pthread_mutex_lock(&timers.disarmed.lock);
        CIRCLEQ_REMOVE(&timers.disarmed.list, timer, entry);
        pthread_mutex_unlock(&timers.disarmed.lock);
    } else {
        CIRCLEQ_REMOVE(&timers.armed.list, timer, entry);
        if (timeout == 0) {
            timer_disarm(timer);
            goto unlock;
        }
    }

    timer->timestamp = timeout;
    core_timers_order(&timers.armed.list, timer);
unlock:
    pthread_mutex_unlock(&timers.armed.lock);
    return 0;
}

void core_timer_unregister(core_timer_handle_t handle) {
    core_timers_entry_t *timer = (core_timers_entry_t *)handle;

#ifdef VORTEX_DEBUG
    __do_timer_check(handle, NULL);
#endif

    if (timer->armed) {
        pthread_mutex_lock(&timers.armed.lock);
        CIRCLEQ_REMOVE(&timers.armed.list, timer, entry);
        pthread_mutex_unlock(&timers.armed.lock);
    } else {
        pthread_mutex_lock(&timers.disarmed.lock);
        CIRCLEQ_REMOVE(&timers.disarmed.list, timer, entry);
        pthread_mutex_unlock(&timers.disarmed.lock);
    }
    free(timer);
}

int core_timers_compare(uint64_t timeout1, uint64_t timeout2) {
    return (int)((timeout1 & timers.mask) - (timeout2 & timers.mask));
}

static void core_timers_update(uint64_t ticks, void *data) {
    core_timers_t *timers = (core_timers_t *)data;
    core_timers_entry_t *timer;
    core_timers_entry_t *next;
    uint64_t reschedule;

    __atomic_store_n(&timers->current, ticks, __ATOMIC_RELEASE);

    pthread_mutex_lock(&timers->armed.lock);
    CIRCLEQ_FOREACH_SAFE(timer, next, &timers->armed.list, entry) {
#ifdef VORTEX_DEBUG
        __do_timer_check((core_timer_handle_t)timer, &timers->armed.list);
        __do_timer_check((core_timer_handle_t)next, &timers->armed.list);
#endif
        if (core_timers_compare(timer->timestamp, ticks) >= 0)
            break;

        CIRCLEQ_REMOVE(&timers->armed.list, timer, entry);
        pthread_mutex_unlock(&timers->armed.lock);
        reschedule = timer->timer.callback(ticks, timer->timer.data);
        pthread_mutex_lock(&timers->armed.lock);
        if (reschedule) {
            timer->timestamp = reschedule;
            core_timers_order(&timers->armed.list, timer);
        } else {
            timer_disarm(timer);
        }

        if (next->entry.cqe_prev != timer)
            break;
    }

    pthread_mutex_unlock(&timers->armed.lock);
    return;
}

void core_timers_disarm(void) {
    core_timers_entry_t *timer;
    core_timers_entry_t *next;

    pthread_mutex_lock(&timers.armed.lock);
    if (!CIRCLEQ_EMPTY(&timers.armed.list)) {
        pthread_mutex_lock(&timers.disarmed.lock);
        CIRCLEQ_FOREACH_SAFE(timer, next, &timers.armed.list, entry) {
            CIRCLEQ_REMOVE(&timers.armed.list, timer, entry);
            CIRCLEQ_INSERT_TAIL(&timers.disarmed.list, timer, entry);
        }

        pthread_mutex_unlock(&timers.disarmed.lock);
    }

    pthread_mutex_unlock(&timers.armed.lock);
}

static void timers_free(core_timer_set_t *set) {
    core_timers_entry_t *timer;
    core_timers_entry_t *next;

    pthread_mutex_lock(&set->lock);
    if (!CIRCLEQ_EMPTY(&set->list)) {
        CIRCLEQ_FOREACH_SAFE(timer, next, &set->list, entry) {
            CIRCLEQ_REMOVE(&set->list, timer, entry);
            free(timer);
        }
    }
    pthread_mutex_unlock(&set->lock);
    pthread_mutex_destroy(&set->lock);
}

void core_timers_free(void) {
    timers_free(&timers.armed);
    timers_free(&timers.disarmed);
}

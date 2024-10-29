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
#include "timers.h"
#include "threads.h"

typedef struct core_timers_struct {
    CIRCLEQ_ENTRY(core_timers_struct) entry;
    core_timer_t timer;
    uint64_t timestamp;
    bool armed;
} core_timers_t;

/* Some useful CIRCLEQ macros which are aren't provided. */
#define CIRCLEQ_REMOVE_INIT(head, elm, field)				\
    do {								\
	CIRCLEQ_REMOVE(head, elm, field);				\
	(elm)->entry.cqe_next = (elm)->entry.cqe_prev = (elm);		\
    } while (0)
#define CIRCLEQ_IN_LIST(elm, field)					\
    ((elm)->entry.cqe_next != (elm) && (elm)->entry.cqe_prev != (elm))
#define CIRCLEQ_FOREACH_SAFE(elm, next, head, field)			\
    for ((elm) = ((head)->cqh_first), (next) = (elm)->field.cqe_next;	\
	 (elm) != (const void *)(head);					\
	 (elm) = (next), (next) = (elm)->field.cqe_next)

typedef CIRCLEQ_HEAD(core_timers_list, core_timers_struct) core_timers_list_t;
static core_timers_list_t core_timers = CIRCLEQ_HEAD_INITIALIZER(core_timers);
static core_timers_list_t disarmed = CIRCLEQ_HEAD_INITIALIZER(disarmed);
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t disarmed_lock = PTHREAD_MUTEX_INITIALIZER;

static void core_timers_update(uint64_t ticks, void *data);

int core_timers_init(void) {
    core_thread_args_t args;

    args.timer.callback = core_timers_update;
    args.timer.data = (void *)&core_timers;
    return core_thread_create(CORE_THREAD_TYPE_TIMER, &args);
}

static void core_timers_order(core_timers_list_t *list, core_timers_t *timer) {
    core_timers_t *entry;

    CIRCLEQ_FOREACH(entry, list, entry) {
	if (timer->timestamp < entry->timestamp) {
	    CIRCLEQ_INSERT_BEFORE(list, entry, timer, entry);
	    goto inserted;
	}
    }

    CIRCLEQ_INSERT_TAIL(list, timer, entry);

inserted:
    timer->armed = true;
}

core_timer_handle_t core_timer_register(core_timer_t timer, uint64_t timeout) {
    core_timers_t *timers_entry;

    timers_entry = malloc(sizeof(*timers_entry));
    if (!timers_entry) {
	errno = -ENOMEM;
	return 0;
    }

    timers_entry->timer = timer;
    timers_entry->timestamp = timeout;

    if (timeout) {
      pthread_mutex_lock(&lock);
      core_timers_order(&core_timers, timers_entry);
      pthread_mutex_unlock(&lock);
    } else {
      /* register but disarm timer */
      timers_entry->armed = false;
      pthread_mutex_lock(&disarmed_lock);
      CIRCLEQ_INSERT_TAIL(&disarmed, timers_entry, entry);
      pthread_mutex_unlock(&disarmed_lock);
    }

    return (core_timer_handle_t)timers_entry;
}

static void timer_disarm(core_timers_t *timer) {
    timer->armed = false;
    pthread_mutex_lock(&disarmed_lock);
    CIRCLEQ_INSERT_TAIL(&disarmed, timer, entry);
    pthread_mutex_unlock(&disarmed_lock);
}

int core_timer_reschedule(core_timer_handle_t handle, uint64_t timeout) {
    core_timers_t *timer = (core_timers_t *)handle;

    pthread_mutex_lock(&lock);
    if (!timer->armed) {
	if (timeout == 0)
	    goto unlock;

	pthread_mutex_lock(&disarmed_lock);
	if (CIRCLEQ_IN_LIST(timer, entry))
	    CIRCLEQ_REMOVE_INIT(&disarmed, timer, entry);
	pthread_mutex_unlock(&disarmed_lock);
    } else {
	if (CIRCLEQ_IN_LIST(timer, entry))
	    CIRCLEQ_REMOVE_INIT(&core_timers, timer, entry);
	if (timeout == 0) {
	    timer_disarm(timer);
	    goto unlock;
	}

    }

    timer->timestamp = timeout;
    core_timers_order(&core_timers, timer);
unlock:
    pthread_mutex_unlock(&lock);
    return 0;
}

void core_timer_unregister(core_timer_handle_t handle) {
    core_timers_t *timer = (core_timers_t *)handle;

    if (timer->armed) {
	pthread_mutex_lock(&lock);
	CIRCLEQ_REMOVE_INIT(&core_timers, timer, entry);
	pthread_mutex_unlock(&lock);
    } else {
	pthread_mutex_lock(&disarmed_lock);
	CIRCLEQ_REMOVE_INIT(&disarmed, timer, entry);
	pthread_mutex_unlock(&disarmed_lock);
    }
    free(timer);
}

static void core_timers_update(uint64_t ticks, void *data) {
    core_timers_list_t *list = (core_timers_list_t *)data;
    core_timers_t *timer;
    core_timers_t *next;
    uint64_t reschedule;

    pthread_mutex_lock(&lock);
    CIRCLEQ_FOREACH_SAFE(timer, next, list, entry) {
        if (timer->timestamp > ticks)
          goto unlock;

	if (CIRCLEQ_IN_LIST(timer, entry))
	    CIRCLEQ_REMOVE_INIT(list, timer, entry);
	pthread_mutex_unlock(&lock);

	reschedule = timer->timer.callback(ticks, timer->timer.data);
	if (!reschedule) {
	    timer_disarm(timer);
	    pthread_mutex_lock(&lock);
	    continue;
	}


	timer->timestamp = reschedule;
	pthread_mutex_lock(&lock);
	core_timers_order(list, timer);
    }

unlock:
    pthread_mutex_unlock(&lock);
    return;
}

void core_timers_disarm(void) {
    core_timers_t *timer;
    core_timers_t *next;

    pthread_mutex_lock(&lock);
    if (!CIRCLEQ_EMPTY(&core_timers)) {
	pthread_mutex_lock(&disarmed_lock);
	CIRCLEQ_FOREACH_SAFE(timer, next, &core_timers, entry) {
	    CIRCLEQ_REMOVE(&core_timers, timer, entry);
	    CIRCLEQ_INSERT_TAIL(&disarmed, timer, entry);
	}

        pthread_mutex_unlock(&disarmed_lock);
    }

    pthread_mutex_unlock(&lock);
}

static void timers_free(core_timers_list_t *list, pthread_mutex_t *lock) {
    core_timers_t *timer;
    core_timers_t *next;

    pthread_mutex_lock(lock);
    if (!CIRCLEQ_EMPTY(list)) {
	CIRCLEQ_FOREACH_SAFE(timer, next, list, entry) {
	    CIRCLEQ_REMOVE(list, timer, entry);
	    free(timer);
	}
    }
    pthread_mutex_unlock(lock);
    pthread_mutex_destroy(lock);
}

void core_timers_free(void) {
    timers_free(&core_timers, &lock);
    timers_free(&disarmed, &disarmed_lock);
}

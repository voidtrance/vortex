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
#include <sched.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <limits.h>
#include <sys/resource.h>
#include <sys/queue.h>
#include <utils.h>
#include "core.h"
#include "thread_control.h"
#include "debug.h"

struct core_thread_control {
    int do_run;
    bool pause;
    pthread_t thread_id;
};

struct core_thread_args {
    const char *name;
    union {
	struct {
	    void *object;
	} update;
	struct {
	    void *callback;
	    void *data;
	    uint64_t frequency;
        } worker;
	struct {
	    uint64_t frequency;
	    uint64_t update;
	} timer;
    };
    int *control;
    bool *pause;
    int ret;
};

typedef struct core_control_data {
    STAILQ_ENTRY(core_control_data) entry;
    struct core_thread_control control;
    struct core_thread_args args;
    void *(*thread_func)(void *);
} core_control_data_t;

typedef STAILQ_HEAD(core_threads_list, core_control_data) core_thread_list_t;
core_thread_list_t core_threads;
static pthread_once_t initialized = PTHREAD_ONCE_INIT;

typedef struct {
    uint64_t controller_ticks ;
    uint64_t controller_runtime;
    int32_t trigger;
    bool paused;
} core_time_data_t;

enum {
    TIMER_TRIGGER_WAIT,
    TIMER_TRIGGER_WAKE,
};

static core_time_data_t global_time_data = {
    .controller_ticks = 0,
    .controller_runtime = 0,
    .trigger = TIMER_TRIGGER_WAKE,
    .paused = false,
};

#define DEFAULT_SCHED_POLICY SCHED_FIFO

#define timespec_delta(s, e)                                                   \
    ((SEC_TO_NSEC((e).tv_sec - (s).tv_sec)) + ((e).tv_nsec - (s).tv_nsec))

static long timer_update_wait(int32_t *flag) {
    long ret = 0;
    int32_t wake_value = TIMER_TRIGGER_WAKE;

    while (1) {
	if (__atomic_compare_exchange_n(flag, &wake_value, TIMER_TRIGGER_WAIT,
					false, __ATOMIC_SEQ_CST,
					__ATOMIC_SEQ_CST))
	    break;

	ret = syscall(SYS_futex, flag, FUTEX_WAIT | FUTEX_PRIVATE_FLAG,
		      TIMER_TRIGGER_WAIT, NULL, NULL, NULL);
	if (ret)
	    break;
    }

    return ret;
}

static long timer_update_wake(int32_t *flag) {

    __atomic_store_n(flag, TIMER_TRIGGER_WAKE, __ATOMIC_SEQ_CST);
    return syscall(SYS_futex, flag, FUTEX_WAKE | FUTEX_PRIVATE_FLAG, INT_MAX,
		   TIMER_TRIGGER_WAKE, NULL, NULL, NULL);
}

static void *core_time_control_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    float tick = (1000.0 / ((float)args->timer.frequency / 1000000));
    float update = (1000.0 / ((float)args->timer.update / 1000000));
    struct timespec sleep = { .tv_sec = update / SEC_TO_NSEC(1),
	.tv_nsec = (uint64_t)update % SEC_TO_NSEC(1) };
    struct timespec pause = { .tv_sec = 0, .tv_nsec = 50000 };
    struct timespec start;
    struct timespec now;

    args->ret = 0;

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, args->name,
	     "step duration: %f, tick: %f", update, tick);

    clock_gettime(CLOCK_MONOTONIC_RAW, &start);
    while (*(volatile int *)args->control == 1) {
	uint64_t delta;

	/* Pause after threads have been signaled. */
	if (*(volatile bool *)args->pause) {
	    global_time_data.paused = true;
	    clock_nanosleep(CLOCK_MONOTONIC_RAW, 0, &pause, NULL);
	    continue;
	} else if (global_time_data.paused) {
	    global_time_data.paused = false;
	}

	nanosleep(&sleep, NULL);
	clock_gettime(CLOCK_MONOTONIC_RAW, &now);
	delta = timespec_delta(start, now);
	clock_gettime(CLOCK_MONOTONIC_RAW, &start);
	global_time_data.controller_runtime += delta;
	global_time_data.controller_ticks += (uint64_t)((float)delta / tick);
	timer_update_wake(&global_time_data.trigger);
    }
}

static void *core_update_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    core_object_t *object = args->update.object;

    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	timer_update_wait(&global_time_data.trigger);
	object->update(object, global_time_data.controller_ticks,
		       global_time_data.controller_runtime);
    }

    pthread_exit(&args->ret);
}

static void *core_generic_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    work_callback_t callback = (work_callback_t)args->worker.callback;
    float step_duration = 0.0;
    struct timespec sleep_time;

    args->ret = 0;
    if (args->worker.frequency)
	step_duration = ((float)1000 / ((float)args->worker.frequency / 1000000));

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core", "worker frequency: %f",
             step_duration);
    sleep_time.tv_sec = 0;
    sleep_time.tv_nsec = step_duration;

    while (*(volatile int *)args->control == 1) {
	callback(args->worker.data);
        nanosleep(&sleep_time, NULL);
    }

    pthread_exit(&args->ret);
}

int start_thread(struct core_control_data *thread_data) {
    // struct sched_param sched_params;
    pthread_attr_t attrs;
    int ret;

    // sched_params.sched_priority =
    // sched_get_priority_min(DEFAULT_SCHED_POLICY);

    ret = pthread_attr_init(&attrs);
    if (ret)
        return ret;

    // ret = pthread_attr_setschedpolicy(&attrs, DEFAULT_SCHED_POLICY);
    // if (ret)
    //	return ret;

    ret = pthread_attr_setinheritsched(&attrs, PTHREAD_EXPLICIT_SCHED);
    if (ret)
        return ret;

    thread_data->control.do_run = 1;
    thread_data->control.pause = false;
    thread_data->args.control = &thread_data->control.do_run;
    thread_data->args.pause = &thread_data->control.pause;
    ret = pthread_create(&thread_data->control.thread_id, &attrs,
			 thread_data->thread_func, &thread_data->args);
    if (ret)
        return ret;

    // ret = pthread_setschedparam(core_global_data.thread_id,
    // DEFAULT_SCHED_POLICY,
    //                             &sched_params);
    // if (ret)
    //	return ret;

    pthread_attr_destroy(&attrs);
    return 0;
}

void controller_thread_list_init(void) {
    STAILQ_INIT(&core_threads);
}

int controller_thread_create(core_object_t *object, const char *name) {
    core_control_data_t *data;

    pthread_once(&initialized, controller_thread_list_init);

    data = calloc(1, sizeof(*data));
    if (!data)
      return -ENOMEM;

    data->args.name = strdup(name);
    data->args.update.object = object;
    data->thread_func = core_update_thread;
    STAILQ_INSERT_TAIL(&core_threads, data, entry);
    return 0;
}

int controller_timer_thread_create(uint64_t frequency,
				   uint64_t update_frequency) {
    core_control_data_t *data;

    pthread_once(&initialized, controller_thread_list_init);
    data = calloc(1, sizeof(*data));
    if (!data)
      return -ENOMEM;

    data->args.name = strdup("time_control");
    data->args.timer.frequency = frequency;
    data->args.timer.update = update_frequency;
    data->thread_func = core_time_control_thread;
    STAILQ_INSERT_TAIL(&core_threads, data, entry);
    return 0;
}

int controller_work_thread_create(work_callback_t callback, void *user_data,
				  uint64_t frequency) {
    core_control_data_t *data;

    pthread_once(&initialized, controller_thread_list_init);

    data = calloc(1, sizeof(*data));
    if (!data)
	return -ENOMEM;

    data->args.name = strdup("worker");
    data->args.worker.frequency = frequency;
    data->args.worker.callback = callback;
    data->args.worker.data = user_data;
    data->thread_func = core_generic_thread;
    STAILQ_INSERT_TAIL(&core_threads, data, entry);
    return 0;
}

int controller_thread_start(void) {
    core_control_data_t *data;
    int ret;

    STAILQ_FOREACH(data, &core_threads, entry) {
	ret = start_thread(data);
	if (ret) {
	    controller_thread_stop();
	    break;
	}
    }

    return ret;
}

void controller_thread_stop(void) {
    core_control_data_t *data;

    STAILQ_FOREACH(data, &core_threads, entry) {
	if (data->control.do_run)
	    data->control.do_run = 0;
    }

    /* Trigger waiters in case the control thread has
     * already exited. */
    timer_update_wake(&global_time_data.trigger);

    STAILQ_FOREACH(data, &core_threads, entry)
	pthread_join(data->control.thread_id, NULL);
}

uint64_t controller_thread_get_clock_ticks(void) {
    return global_time_data.controller_ticks;
}

uint64_t controller_thread_get_runtime(void) {
    return global_time_data.controller_runtime;
}

void controller_thread_pause(void) {
    core_control_data_t *data;
    struct timespec ts = {.tv_sec = 0, .tv_nsec = 50000};

    STAILQ_FOREACH(data, &core_threads, entry)
	data->control.pause = true;

    while (!global_time_data.paused)
	nanosleep(&ts, NULL);
}

void controller_thread_resume(void) {
    core_control_data_t *data;
    struct timespec ts = {.tv_sec = 0, .tv_nsec = 50000};

    STAILQ_FOREACH(data, &core_threads, entry)
	data->control.pause = false;

    while (global_time_data.paused)
	nanosleep(&ts, NULL);
}

void controller_thread_destroy(void) {
    core_control_data_t *data, *next;

    if (STAILQ_EMPTY(&core_threads))
	return;

    data = STAILQ_FIRST(&core_threads);
    while (data) {
	next = STAILQ_NEXT(data, entry);
	free((char *)data->args.name);
	free(data);
	data = next;
    }
}

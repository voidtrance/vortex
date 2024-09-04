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
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <math.h>
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
    void *callback;
    void *data;
    uint64_t frequency;
    int64_t frequency_match;
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
static bool __initialized = false;

#define DEFAULT_SCHED_POLICY SCHED_FIFO

#define timespec_delta(s, e)                                                   \
    ((SEC_TO_NSEC((e).tv_sec - (s).tv_sec)) + ((e).tv_nsec - (s).tv_nsec))

static void *core_update_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    core_object_t *object = args->data;
    struct timespec ts, te;
    float tick = (1000.0 / (args->frequency / 1000000));
    uint64_t ticks = 0;
    uint64_t runtime = 0;
    int64_t sleep_counter = 0;

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, args->name, "step duration: %f",
	     tick);
    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	int64_t delay;
	uint64_t time;

	if (*(volatile bool *)args->pause) {
	    ts.tv_nsec = 50000;
	    clock_nanosleep(CLOCK_MONOTONIC_RAW, 0, &ts, NULL);
	    continue;
	}

	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	object->update(object, ticks, runtime);
	clock_gettime(CLOCK_MONOTONIC_RAW, &te);
	time = timespec_delta(ts, te);
	delay = (int64_t)tick - time;
        if (delay <= 0 || delay > tick)
	    goto count;
        te.tv_nsec += (uint64_t)delay;
        clock_nanosleep(CLOCK_MONOTONIC_RAW, TIMER_ABSTIME, &te, NULL);
        time = timespec_delta(ts, te);
    count:
        runtime += time;
	ticks += (uint64_t)(roundf(((float)time / tick) * 100) / 100);
    }

    args->frequency_match = sleep_counter;
    pthread_exit(&args->ret);
}

static void *core_generic_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    work_callback_t callback = (work_callback_t)args->callback;
    float step_duration = 0.0;
    struct timespec sleep_time = {0};
    struct timespec ts, te;

    args->ret = 0;
    if (args->frequency)
	step_duration = ((float)1000 / (args->frequency / 1000000));

    while (*(volatile int *)args->control == 1) {
	long delay;

	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	callback(args->data);
	clock_gettime(CLOCK_MONOTONIC_RAW, &te);
        delay = max((long)step_duration - timespec_delta(ts, te), 0);
        if (delay <= 0 || delay > step_duration)
	    continue;
        sleep_time.tv_nsec = delay;
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

int controller_thread_create(core_object_t *object, const char *name,
			     uint64_t frequency) {
    core_control_data_t *data;

    if (!__initialized) {
      STAILQ_INIT(&core_threads);
      __initialized = true;
    }

    data = calloc(1, sizeof(*data));
    if (!data)
      return -ENOMEM;

    data->args.name = strdup(name);
    data->args.frequency = frequency;
    data->args.callback = NULL;;
    data->args.data = object;
    data->thread_func = core_update_thread;
    STAILQ_INSERT_TAIL(&core_threads, data, entry);
    return 0;
}

int controller_work_thread_create(work_callback_t callback, void *user_data,
				  uint64_t frequency) {
    core_control_data_t *data;

    if (!__initialized) {
      STAILQ_INIT(&core_threads);
      __initialized = true;
    }


    data = calloc(1, sizeof(*data));
    if (!data)
	return -ENOMEM;

    data->args.frequency = frequency;
    data->args.callback = callback;
    data->args.data = user_data;
    data->thread_func = core_generic_thread;
    STAILQ_INSERT_TAIL(&core_threads, data, entry);
    return 0;
}
int controller_thread_start(void) {
    core_control_data_t *data;
    int ret;

    STAILQ_FOREACH(data, &core_threads, entry) {
	ret = start_thread(data);
	if (ret)
	    break;
    }

    if (ret)
	controller_thread_stop();

    return ret;
}

void controller_thread_stop(void) {
    core_control_data_t *data;

    STAILQ_FOREACH(data, &core_threads, entry) {
	if (data->control.do_run) {
	    data->control.do_run = 0;
	    pthread_join(data->control.thread_id, NULL);
	    if (data->args.name)
		core_log(LOG_LEVEL_INFO, OBJECT_TYPE_NONE, data->args.name,
			 "update frequency match: %ld",
			 data->args.frequency_match);
	}
    }
}

void controller_thread_pause(void) {
    core_control_data_t *data;

    STAILQ_FOREACH(data, &core_threads, entry)
	data->control.pause = true;
}

void controller_thread_resume(void) {
    core_control_data_t *data;

    STAILQ_FOREACH(data, &core_threads, entry)
	data->control.pause = false;
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

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
#include "utils.h"
#include "core.h"
#include "thread_control.h"
#include "debug.h"

struct core_thread_control {
    int do_run;
    bool pause;
    pthread_t thread_id;
};

struct core_thread_args {
    void *callback;
    void *user_data;
    uint64_t frequency;
    int64_t frequency_match;
    int *control;
    bool *pause;
    int ret;
};

struct core_control_data {
    struct core_thread_control control;
    struct core_thread_args args;
    void *(*thread_func)(void *);
};

static struct core_control_data core_global_update;
static struct core_control_data core_global_work;

#define DEFAULT_SCHED_POLICY SCHED_FIFO

#define timespec_delta(s, e)                                                   \
    ((SEC_TO_NSEC((e).tv_sec - (s).tv_sec)) + ((e).tv_nsec - (s).tv_nsec))

static void *core_update_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    update_callback_t callback = (update_callback_t)args->callback;
    struct timespec sleep_time = {0};
    struct timespec ts, te;
    float tick = (1000.0 / (args->frequency / 1000000));
    uint64_t ticks = 0;
    uint64_t runtime = 0;
    int64_t sleep_counter = 0;

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "threads", "step duration: %f",
	     tick);
    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	int64_t delay;
	uint64_t time;

	if (*(volatile bool *)args->pause) {
	    sleep_time.tv_nsec = 50000;
	    nanosleep(&sleep_time, NULL);
	    continue;
	}

	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	callback(ticks, runtime, args->user_data);
	clock_gettime(CLOCK_MONOTONIC_RAW, &te);
	time = timespec_delta(ts, te);
	delay = (int64_t)tick - time;
        sleep_counter += delay;
        if (delay <= 0 || delay > tick)
	    goto count;
        sleep_time.tv_nsec = (uint64_t)delay;
        nanosleep(&sleep_time, NULL);
        clock_gettime(CLOCK_MONOTONIC_RAW, &te);
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
	callback(args->user_data);
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

int controller_timer_start(update_callback_t update_cb,
			   uint64_t update_frequency,
			   work_callback_t work_cb, uint64_t work_frequency,
                           void *user_data) {
    int ret;

    core_global_update.args.frequency = update_frequency;
    core_global_update.args.callback = update_cb;
    core_global_update.args.user_data = user_data;
    core_global_update.thread_func = core_update_thread;
    ret = start_thread(&core_global_update);
    if (ret)
	return ret;

    core_global_work.args.frequency = work_frequency;
    core_global_work.args.callback = work_cb;
    core_global_work.args.user_data = user_data;
    core_global_work.thread_func = core_generic_thread;
    ret = start_thread(&core_global_work);
    if (ret) {
	core_global_update.control.do_run = 0;
	pthread_join(core_global_update.control.thread_id, NULL);
	return ret;
    }

    return ret;
}

int64_t controller_timer_stop(void) {
    core_global_update.control.do_run = 0;
    core_global_work.control.do_run = 0;
    if (core_global_update.control.thread_id)
        pthread_join(core_global_update.control.thread_id, NULL);
    if (core_global_work.control.thread_id)
	pthread_join(core_global_work.control.thread_id, NULL);

    return core_global_update.args.frequency_match;
}

void controller_timer_pause(void) {
    core_global_update.control.pause = true;
    core_global_update.control.pause = true;
}

void controller_timer_resume(void) {
    core_global_update.control.pause = false;
    core_global_work.control.pause = false;
}

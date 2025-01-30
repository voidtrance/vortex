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
#define _GNU_SOURCE
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
#include "threads.h"

struct core_thread_control {
    int do_run;
    bool pause;
    pthread_t thread_id;
};

struct core_thread_args {
    const char *name;
    core_thread_args_t args;
    int *control;
    bool *pause;
    int ret;
};

typedef struct core_control_data {
    STAILQ_ENTRY(core_control_data) entry;
    core_thread_type_t type;
    struct core_thread_control control;
    struct core_thread_args args;
    void *(*thread_func)(void *);
} core_control_data_t;

typedef STAILQ_HEAD(core_threads_list, core_control_data) core_thread_list_t;
core_thread_list_t core_threads;
static pthread_once_t initialized = PTHREAD_ONCE_INIT;

typedef struct {
    uint64_t controller_ticks;
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

#define get_value(x) (*(volatile typeof((x)) *)&(x))
#define set_value(x, y) (*(volatile typeof((x)) *)&(x) = (y))

static void *core_time_control_thread(void *arg) {
    struct core_thread_args *data = (struct core_thread_args *)arg;
    core_thread_args_t *args = &data->args;
    float tick = (1000.0 / ((float)args->update.tick_frequency / 1000000));
    float update = (1000.0 / ((float)args->update.update_frequency / 1000000));
    struct timespec sleep = { .tv_sec = (uint64_t)update / SEC_TO_NSEC(1),
            .tv_nsec = (uint64_t)update % SEC_TO_NSEC(1) };
    uint64_t controller_clock_mask = (1UL << args->update.width) - 1;
    struct timespec pause = { .tv_sec = 0, .tv_nsec = 50000 };
    struct timespec start;
    struct timespec now;

    data->ret = 0;

    clock_gettime(CLOCK_MONOTONIC_RAW, &start);
    while (get_value(*data->control) == 1) {
        uint64_t runtime;

        /* Pause after threads have been signaled. */
        if (get_value(*data->pause)) {
            set_value(global_time_data.paused, true);
            clock_nanosleep(CLOCK_MONOTONIC_RAW, 0, &pause, NULL);
            continue;
        } else if (global_time_data.paused) {
            set_value(global_time_data.paused, false);
        }

        clock_nanosleep(CLOCK_MONOTONIC_RAW, 0, &sleep, NULL);
        clock_gettime(CLOCK_MONOTONIC_RAW, &now);
        runtime = timespec_delta(start, now);
        set_value(global_time_data.controller_runtime, runtime);
        set_value(global_time_data.controller_ticks,
                  (uint64_t)((float)runtime / tick) & controller_clock_mask);
        timer_update_wake(&global_time_data.trigger);
    }

    pthread_exit(&data->ret);
}

static void *core_timer_thread(void *arg) {
    struct core_thread_args *data = (struct core_thread_args *)arg;
    core_thread_args_t *args = &data->args;

    data->ret = 0;
    while (get_value(*data->control) == 1) {
        timer_update_wait(&global_time_data.trigger);
        args->timer.callback(get_value(global_time_data.controller_ticks),
                             args->timer.data);
    }

    pthread_exit(&data->ret);
}

static void *core_update_thread(void *arg) {
    struct core_thread_args *data = (struct core_thread_args *)arg;
    core_thread_args_t *args = &data->args;

    data->ret = 0;
    while (get_value(*data->control) == 1) {
        timer_update_wait(&global_time_data.trigger);
        args->object.callback(args->object.data,
                              get_value(global_time_data.controller_ticks),
                              get_value(global_time_data.controller_runtime));
    }

    pthread_exit(&data->ret);
}

static void *core_generic_thread(void *arg) {
    struct core_thread_args *data = (struct core_thread_args *)arg;
    core_thread_args_t *args = &data->args;
    float step_duration = 0.0;
    struct timespec sleep_time;

    data->ret = 0;
    if (args->worker.frequency)
        step_duration = ((float)1000 / ((float)args->worker.frequency / 1000000));

    sleep_time.tv_sec = 0;
    sleep_time.tv_nsec = step_duration;

    while (get_value(*data->control) == 1) {
        args->worker.callback(args->worker.data);
        nanosleep(&sleep_time, NULL);
    }

    pthread_exit(&data->ret);
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

static void core_thread_list_init(void) {
    STAILQ_INIT(&core_threads);
}

int core_thread_create(core_thread_type_t type, core_thread_args_t *args) {
    core_control_data_t *data;

    pthread_once(&initialized, core_thread_list_init);

    data = calloc(1, sizeof(*data));
    if (!data)
        return -ENOMEM;

    memcpy(&data->args.args, args, sizeof(data->args));
    data->type = type;

    switch (type) {
    case CORE_THREAD_TYPE_UPDATE:
        data->thread_func = core_time_control_thread;
        data->args.name = strdup("time_control");
        break;
    case CORE_THREAD_TYPE_TIMER:
        data->thread_func = core_timer_thread;
        data->args.name = strdup("timer");
        break;
    case CORE_THREAD_TYPE_OBJECT:
        data->thread_func = core_update_thread;
        data->args.name = strdup(args->object.name);
        break;
    case CORE_THREAD_TYPE_WORKER:
        data->thread_func = core_generic_thread;
        data->args.name = strdup("worker");
    }

    STAILQ_INSERT_TAIL(&core_threads, data, entry);
    return 0;
}

int core_threads_start(void) {
    core_control_data_t *data;
    int ret;

    STAILQ_FOREACH(data, &core_threads, entry) {
        ret = start_thread(data);
        if (ret) {
            core_threads_stop();
            break;
        }
    }

    return ret;
}

void core_threads_stop(void) {
    core_control_data_t *data;

    /*
     * Stop all threads except the time control one.
     * This should ensure that any other threads waiting
     * on the futex will be woken up and will be able to
     * exit cleanly.
     */
    STAILQ_FOREACH(data, &core_threads, entry) {
        if (data->type != CORE_THREAD_TYPE_UPDATE)
            set_value(data->control.do_run, 0);
    }

    STAILQ_FOREACH(data, &core_threads, entry) {
        if (data->type != CORE_THREAD_TYPE_UPDATE)
            pthread_join(data->control.thread_id, NULL);
    }

    /*
     * Now that all other threads have exited, stop the
     * time control thread.
     */
    STAILQ_FOREACH(data, &core_threads, entry) {
        if (data->type == CORE_THREAD_TYPE_UPDATE) {
            set_value(data->control.do_run, 0);
            pthread_join(data->control.thread_id, NULL);
        }
    }
}

uint64_t core_get_clock_ticks(void) {
    return get_value(global_time_data.controller_ticks);
}

uint64_t core_get_runtime(void) {
    return get_value(global_time_data.controller_runtime);
}

void core_threads_pause(void) {
    core_control_data_t *data;
    struct timespec ts = {.tv_sec = 0, .tv_nsec = 50000};

    STAILQ_FOREACH(data, &core_threads, entry)
        set_value(data->control.pause, true);

    while (get_value(global_time_data.paused))
        nanosleep(&ts, NULL);
}

void core_threads_resume(void) {
    core_control_data_t *data;
    struct timespec ts = {.tv_sec = 0, .tv_nsec = 50000};

    STAILQ_FOREACH(data, &core_threads, entry)
        set_value(data->control.pause, false);

    while (get_value(global_time_data.paused))
        nanosleep(&ts, NULL);
}

void core_threads_destroy(void) {
    core_control_data_t *data, *next;

    if (STAILQ_EMPTY(&core_threads))
        return;

    data = STAILQ_FIRST(&core_threads);
    while (data) {
        next = STAILQ_NEXT(data, entry);
        free((char *)data->args.name);
        if (data->type == CORE_THREAD_TYPE_OBJECT)
            free((char *)data->args.args.object.name);
        free(data);
        data = next;
    }
}

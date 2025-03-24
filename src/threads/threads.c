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
#include <stdio.h>
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <sys/sysinfo.h>
#include <limits.h>
#include <sys/resource.h>
#include <sys/queue.h>
#include <sys/timerfd.h>
#include <utils.h>
#include "threads.h"

enum {
    THREAD_CONTROL_STOP = 0,
    THREAD_CONTROL_RUN,
    THREAD_CONTROL_RUNNING,
    THREAD_CONTROL_PAUSED,
};

struct core_thread_args {
    const char *name;
    core_thread_args_t args;
    int control;
    int ret;
};

typedef struct core_control_data {
    STAILQ_ENTRY(core_control_data) entry;
    core_thread_type_t type;
    pthread_t thread_id;
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
} core_time_data_t;

enum {
    TIMER_TRIGGER_WAIT,
    TIMER_TRIGGER_WAKE,
};

static core_time_data_t global_time_data = {
    .controller_ticks = 0,
    .controller_runtime = 0,
    .trigger = TIMER_TRIGGER_WAKE,
};

#define DEFAULT_SCHED_POLICY SCHED_FIFO

#define timespec_delta(s, e)                                                   \
    ((SEC_TO_NSEC((e).tv_sec - (s).tv_sec)) + ((e).tv_nsec - (s).tv_nsec))

static long timer_update_wait(int32_t *flag) {
    int32_t wake_value = TIMER_TRIGGER_WAKE;

    while (1) {
        if (__atomic_compare_exchange_n(flag, &wake_value, TIMER_TRIGGER_WAIT,
                                        false, __ATOMIC_SEQ_CST,
                                        __ATOMIC_SEQ_CST))
            break;

        if (syscall(SYS_futex, flag, FUTEX_WAIT_PRIVATE, TIMER_TRIGGER_WAIT,
                    NULL, NULL, NULL) == -1 &&
            errno != EAGAIN)
            return -errno;
    }

    return 0;
}

static long timer_update_wake(int32_t *flag) {
    uint32_t wait_value = TIMER_TRIGGER_WAIT;

    if (__atomic_compare_exchange_n(flag, &wait_value, TIMER_TRIGGER_WAKE,
                                    false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST))
        return syscall(SYS_futex, flag, FUTEX_WAKE_PRIVATE, INT_MAX, NULL, NULL,
                       0);

    return 0;
}

#define get_value(x) (*(volatile typeof((x)) *)&(x))
#define set_value(x, y) (*(volatile typeof((x)) *)&(x) = (y))

static void *core_time_control_thread(void *arg) {
    struct core_thread_args *data = (struct core_thread_args *)arg;
    core_thread_args_t *args = &data->args;
    float tick = (1000.0 / ((float)args->update.tick_frequency / 1000000));
    float update = (1000.0 / ((float)args->update.update_frequency / 1000000));
    struct timespec sleep = { .tv_sec = (time_t)update / SEC_TO_NSEC(1),
                              .tv_nsec = (long int)update % SEC_TO_NSEC(1) };
    uint64_t controller_clock_mask = (1UL << args->update.width) - 1;
    struct timespec pause = { .tv_sec = 0, .tv_nsec = 50000 };
    struct timespec start;
    struct timespec now;
    uint64_t runtime = 0;

    data->ret = 0;
    clock_gettime(CLOCK_MONOTONIC_RAW, &start);
    set_value(data->control, THREAD_CONTROL_RUNNING);
    while (likely(get_value(data->control))) {
        if (unlikely(get_value(data->control) == THREAD_CONTROL_PAUSED)) {
            clock_nanosleep(CLOCK_MONOTONIC_RAW, 0, &pause, NULL);
            continue;
        }

        nanosleep(&sleep, NULL);
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
    set_value(data->control, THREAD_CONTROL_RUNNING);
    while (get_value(data->control)) {
        timer_update_wait(&global_time_data.trigger);
        args->timer.callback(get_value(global_time_data.controller_ticks),
                             args->timer.data);
    }

    pthread_exit(&data->ret);
}

static void *core_update_thread(void *arg) {
    struct core_thread_args *data = (struct core_thread_args *)arg;
    core_thread_args_t *args = &data->args;
    float update = (1000.0 / ((float)args->update.update_frequency / 1000000));
    struct timespec sleep;

    sleep.tv_sec = (uint64_t)update / SEC_TO_NSEC(1);
    sleep.tv_nsec = (uint64_t)update % SEC_TO_NSEC(1);

    data->ret = 0;
    set_value(data->control, THREAD_CONTROL_RUNNING);
    while (get_value(data->control)) {
        //timer_update_wait(&global_time_data.trigger);
        args->object.callback(args->object.data,
                              get_value(global_time_data.controller_ticks),
                              get_value(global_time_data.controller_runtime));
        nanosleep(&sleep, NULL);
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

    set_value(data->control, THREAD_CONTROL_RUNNING);
    while (get_value(data->control)) {
        args->worker.callback(args->worker.data);
        nanosleep(&sleep_time, NULL);
    }

    pthread_exit(&data->ret);
}

#define __stringify(x) #x
#define stringify(x) __stringify(x)

#define PTHREAD_CALL(func, ...)                                 \
    do {                                                        \
        int __ret = func(__VA_ARGS__);                          \
        if (__ret) {                                            \
            fprintf(stderr, "ERROR: " stringify(func) ": %s\n", \
                    strerror(__ret));                           \
            return __ret;                                       \
        }                                                       \
    } while (0)

static int start_thread(struct core_control_data *thread_data) {
    struct sched_param sched_params;
    struct rlimit rlimit;
    pthread_attr_t attrs, *attrp;
    int min_prio, max_prio, prio_step;
    bool attempt_prio = true;
    cpu_set_t cpu_mask;
    int num_procs = get_nprocs();
    int ret;

    min_prio = sched_get_priority_min(SCHED_RR);
    max_prio = sched_get_priority_max(SCHED_RR);
    if (getrlimit(RLIMIT_RTPRIO, &rlimit) == -1 || rlimit.rlim_max == 0 ||
        max_prio - min_prio < 3) {
        attempt_prio = false;
    }

    prio_step = (max_prio - min_prio) / 3;

    CPU_ZERO(&cpu_mask);

    switch (thread_data->type) {
    case CORE_THREAD_TYPE_UPDATE:
    case CORE_THREAD_TYPE_TIMER:
        CPU_SET(0, &cpu_mask);
        sched_params.sched_priority = min_prio;
        break;
    case CORE_THREAD_TYPE_OBJECT:
        if (num_procs > 1)
            CPU_SET(1, &cpu_mask);
        sched_params.sched_priority = min_prio + prio_step;
        break;
    default:
        if (num_procs > 2)
            CPU_SET(2, &cpu_mask);
        sched_params.sched_priority = min_prio + prio_step * 2;
    }

    PTHREAD_CALL(pthread_attr_init, &attrs);

    if (CPU_COUNT(&cpu_mask))
        PTHREAD_CALL(pthread_attr_setaffinity_np, &attrs, sizeof(cpu_mask),
                     &cpu_mask);

    if (attempt_prio) {
        PTHREAD_CALL(pthread_attr_setinheritsched, &attrs,
                     PTHREAD_EXPLICIT_SCHED);
        PTHREAD_CALL(pthread_attr_setschedpolicy, &attrs, SCHED_RR);
        PTHREAD_CALL(pthread_attr_setschedparam, &attrs, &sched_params);
    }

    thread_data->args.control = THREAD_CONTROL_RUN;
    attrp = &attrs;
recreate:
    ret = pthread_create(&thread_data->thread_id, attrp,
                         thread_data->thread_func, &thread_data->args);
    if (ret) {
        if (ret == EPERM && attrp) {
            fprintf(stderr, "ERROR: Failed to set thread scheduling policy.\n");
            fprintf(stderr, "ERROR: Using default policy.\n");
            attrp = NULL;
            goto recreate;
        }

        return ret;
    }

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
            set_value(data->args.control, THREAD_CONTROL_STOP);
    }

    STAILQ_FOREACH(data, &core_threads, entry) {
        if (data->type != CORE_THREAD_TYPE_UPDATE)
            pthread_join(data->thread_id, NULL);
    }

    /*
     * Now that all other threads have exited, stop the
     * time control thread.
     */
    STAILQ_FOREACH(data, &core_threads, entry) {
        if (data->type == CORE_THREAD_TYPE_UPDATE) {
            set_value(data->args.control, THREAD_CONTROL_STOP);
            pthread_join(data->thread_id, NULL);
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

    STAILQ_FOREACH(data, &core_threads, entry)
        set_value(data->args.control, THREAD_CONTROL_PAUSED);
}

void core_threads_resume(void) {
    core_control_data_t *data;

    STAILQ_FOREACH(data, &core_threads, entry)
        set_value(data->args.control, THREAD_CONTROL_RUNNING);
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

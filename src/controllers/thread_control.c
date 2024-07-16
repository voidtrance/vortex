#include "thread_control.h"
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <sys/resource.h>
#include "utils.h"

struct core_thread_control {
    int do_run;
    pthread_t thread_id;
};

struct core_thread_args {
    void *callback;
    void *user_data;
    uint64_t frequency;
    int *control;
    int ret;
};

struct core_control_data {
    struct core_thread_control control;
    struct core_thread_args args;
    void *(*thread_func)(void *);
};

static struct core_control_data core_global_update;
static struct core_control_data core_global_complete;
static struct core_control_data core_global_events;

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

    printf("step duration: %f\n", tick);
    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	int64_t delay;
	uint64_t time;

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

    printf("update time counter: %ld\n", sleep_counter);
    pthread_exit(&args->ret);
}

static void *core_generic_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    completion_callback_t callback = (completion_callback_t)args->callback;
    float step_duration = ((float)1000 / (args->frequency / 1000000));
    struct timespec sleep_time = {0};
    struct timespec ts, te;

    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	long delay;

	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	callback(args->user_data);
	clock_gettime(CLOCK_MONOTONIC_RAW, &te);
        delay = max((long)step_duration - timespec_delta(ts, te), 0);
        if (delay < 0 || delay > step_duration)
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
    thread_data->args.control = &thread_data->control.do_run;
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
			   completion_callback_t completion_cb,
			   uint64_t completion_frequency,
			   event_callback_t event_cb,
			   uint64_t event_frequency,
                           void *user_data) {
    int ret;

    core_global_update.args.frequency = update_frequency;
    core_global_update.args.callback = update_cb;
    core_global_update.args.user_data = user_data;
    core_global_update.thread_func = core_update_thread;
    ret = start_thread(&core_global_update);
    if (ret)
	return ret;

    core_global_complete.args.frequency = completion_frequency;
    core_global_complete.args.callback = completion_cb;
    core_global_complete.args.user_data = user_data;
    core_global_complete.thread_func = core_generic_thread;
    ret = start_thread(&core_global_complete);
    if (ret)
	return ret;

    core_global_events.args.frequency = event_frequency;
    core_global_events.args.callback = event_cb;
    core_global_events.args.user_data = user_data;
    core_global_events.thread_func = core_generic_thread;
    ret = start_thread(&core_global_events);

    return ret;
}

void controller_timer_stop(void) {
    core_global_update.control.do_run = 0;
    core_global_complete.control.do_run = 0;
    core_global_events.control.do_run = 0;
    pthread_join(core_global_update.control.thread_id, NULL);
    pthread_join(core_global_complete.control.thread_id, NULL);
    pthread_join(core_global_events.control.thread_id, NULL);
}

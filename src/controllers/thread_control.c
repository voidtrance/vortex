#include "thread_control.h"
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

typedef struct {
    int core_thread_do_run;
    pthread_t thread_id;
} core_thread_control_t;

struct core_update_thread_args {
    update_callback_t callback;
    void *user_data;
    uint64_t frequency;
    int *control;
    uint64_t total;
    uint64_t count;
    int ret;
};

struct core_completion_thread_args {
    completion_callback_t callback;
    void *user_data;
    uint64_t frequency;
    int *control;
    int ret;
};

static core_thread_control_t core_update_global_data;
static core_thread_control_t core_complete_global_data;
static struct core_update_thread_args update_args;
static struct core_completion_thread_args completion_args;

#define DEFAULT_SCHED_POLICY SCHED_FIFO

#define max(a, b) ((a <= (typeof(a))b) ? b : a)
#define timespec_delta(s, e)                                                   \
    ((((e).tv_sec - (s).tv_sec) * 1000000000) + ((e).tv_nsec - (s).tv_nsec))

static void *core_update_thread(void *arg) {
    struct core_update_thread_args *args =
	(struct core_update_thread_args *)arg;
    float step_duration = ((float)1000 / (args->frequency / 1000000));
    uint64_t step_time = 0;
    struct timespec sleep_time = {0};
    struct timespec ts, te;

    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	long delay;

	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	args->callback(step_time, args->user_data);
	clock_gettime(CLOCK_MONOTONIC_RAW, &te);
	args->total += timespec_delta(ts, te);
	args->count++;
        delay = max((long)step_duration - timespec_delta(ts, te), 0);
        if (delay < 0 || delay > step_duration)
	    continue;
        sleep_time.tv_nsec = delay;
        nanosleep(&sleep_time, NULL);
        step_time += (int)step_duration;
    }

    pthread_exit(&args->ret);
}

static void *core_complete_thread(void *arg) {
    struct core_completion_thread_args *args =
	(struct core_completion_thread_args *)arg;
    float step_duration = ((float)1000 / (args->frequency / 1000000));
    struct timespec sleep_time = {0};
    struct timespec ts, te;

    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
	long delay;

	clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
	args->callback(args->user_data);
	clock_gettime(CLOCK_MONOTONIC_RAW, &te);
        delay = max((long)step_duration - timespec_delta(ts, te), 0);
        if (delay < 0 || delay > step_duration)
	    continue;
        sleep_time.tv_nsec = delay;
        nanosleep(&sleep_time, NULL);
    }

    pthread_exit(&args->ret);
}

int start_thread(core_thread_control_t *control,
		 void *(*thread_func)(void *), void *args) {
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

    ret = pthread_create(&control->thread_id, &attrs, thread_func, args);
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

int controller_timer_start(uint64_t frequency, update_callback_t update_cb,
			   completion_callback_t completion_cb,
                           void *user_data) {
    int ret;

    core_update_global_data.core_thread_do_run = 1;
    update_args.frequency = frequency;
    update_args.callback = update_cb;
    update_args.user_data = user_data;
    update_args.control = &core_update_global_data.core_thread_do_run;

    ret = start_thread(&core_update_global_data, core_update_thread,
		       &update_args);
    if (ret)
	return ret;

    core_complete_global_data.core_thread_do_run = 1;
    completion_args.frequency = frequency;
    completion_args.callback = completion_cb;
    completion_args.user_data = user_data;
    completion_args.control = &core_update_global_data.core_thread_do_run;

    ret = start_thread(&core_complete_global_data, core_complete_thread,
		       &completion_args);
    return ret;
}

void controller_timer_stop(void) {
    core_update_global_data.core_thread_do_run = 0;
    core_complete_global_data.core_thread_do_run = 0;
    pthread_join(core_update_global_data.thread_id, NULL);
    pthread_join(core_complete_global_data.thread_id, NULL);
    printf("Average update cycle: %f nsec\n",
	   (float)update_args.total / update_args.count);
}

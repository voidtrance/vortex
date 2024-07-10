#include <pthread.h>
#include <sched.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
#include "timing.h"

typedef struct core_timing {
    int core_thread_do_run;
    pthread_t thread_id;
} core_timing_t;

struct core_thread_args {
	timer_callback_t callback;
	void *user_data;
    uint64_t frequency;
    int *control;
    uint64_t total;
    uint64_t count;
    int ret;
};

static core_timing_t core_global_data;
static struct core_thread_args thread_args;

#define DEFAULT_SCHED_POLICY SCHED_FIFO

#define max(a, b) ((a <= (typeof(a))b) ? b : a)
#define timespec_delta(s, e) \
	((((e).tv_sec - (s).tv_sec) * 1000000000) + ((e).tv_nsec - (s).tv_nsec))

static void *core_timing_thread(void *arg) {
    struct core_thread_args *args = (struct core_thread_args *)arg;
    float step_duration =  ((float)1000 / (args->frequency / 1000000));
    uint64_t step_time = 0;
    struct timespec sleep_time = { 0 };
    struct timespec ts, te;

    args->ret = 0;
    while (*(volatile int *)args->control == 1) {
        long delay;
		int ret;

		clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
		ret = args->callback(step_time, args->user_data);
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

    return &args->ret;
}

int controller_timer_start(uint64_t frequency, timer_callback_t callback,
						   void *user_data) {
    //struct sched_param sched_params;
    pthread_attr_t attrs;
    int ret;

    //sched_params.sched_priority = sched_get_priority_min(DEFAULT_SCHED_POLICY);

    ret = pthread_attr_init(&attrs);
	if (ret)
		return ret;

    //ret = pthread_attr_setschedpolicy(&attrs, DEFAULT_SCHED_POLICY);
	//if (ret)
	//	return ret;

    ret = pthread_attr_setinheritsched(&attrs, PTHREAD_EXPLICIT_SCHED);
	if (ret)
		return ret;

    core_global_data.core_thread_do_run = 1;
    thread_args.frequency = frequency;
    thread_args.callback = callback;
	thread_args.user_data = user_data;
    thread_args.control = &core_global_data.core_thread_do_run;

    ret = pthread_create(&core_global_data.thread_id, &attrs,
						 &core_timing_thread, &thread_args);
	if (ret)
		return ret;

    //ret = pthread_setschedparam(core_global_data.thread_id, DEFAULT_SCHED_POLICY,
    //                            &sched_params);
	//if (ret)
	//	return ret;

	pthread_attr_destroy(&attrs);
	return 0;
}

void controller_timer_stop(void) {
    core_global_data.core_thread_do_run = 0;
    pthread_join(core_global_data.thread_id, NULL);
    printf("Average update cycle: %f nsec\n",
		   (float)thread_args.total / thread_args.count);
}

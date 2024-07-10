#define _GNU_SOURCE
#include <stdio.h>
#include <pthread.h>
#include <time.h>
#include <sched.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <errno.h>

static bool do_run = true;

#define SEC2NSEC 1000 * 1000 * 1000

int SCHED_POLICY = SCHED_RR;

struct thread_args {
    uint32_t sleep_time;
    uint64_t total;
    uint64_t count;
};

static void *thread_func(void *arg) {
    struct thread_args *args = (struct thread_args *)arg;
    struct timespec ts, te, sleep, rem;
    uint64_t duration;

    sleep.tv_sec = 0;
    sleep.tv_nsec = args->sleep_time;
    args->total = 0;
    args->count = 0;
    while (do_run) {
        clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
        nanosleep(&sleep, &rem);
        clock_gettime(CLOCK_MONOTONIC_RAW, &te);
        duration = ((te.tv_sec - ts.tv_sec) * SEC2NSEC) + 
            (te.tv_nsec - ts.tv_nsec);
        args->total += duration;
        args->count++;
    }
}

int main(int argc, char **argv) {
    pthread_attr_t attrs;
    pthread_t thread;
    struct thread_args args;
    uint32_t runtime;
    uint32_t sleeptime;
    void *res;
    int opt;
    int min_priority, max_priority, priority;
    unsigned int relative = 0;
    struct sched_param sparam;
    cpu_set_t mask;

    while ((opt = getopt(argc, argv, "s:r:p:")) != -1) {
        switch (opt) {
        case 's':
            sleeptime = strtoul(optarg, NULL, 0);
            break;
        case 'r':
            runtime = strtoul(optarg, NULL, 0);
            break;
        case 'p':
            relative = strtoul(optarg, NULL, 0);
            break;
        }
    }

    //CPU_SET(1, &mask);
    //sched_setaffinity(0, sizeof(mask), &mask);

    min_priority = sched_get_priority_min(SCHED_POLICY);
    max_priority = sched_get_priority_max(SCHED_POLICY);
    printf("min/max priority: %d/%d\n", min_priority, max_priority);
    priority = min_priority + relative;
    if (priority > max_priority)
        priority = max_priority;

    printf("run priority: %d\n", priority);
    sparam.sched_priority = priority;

    if (pthread_attr_init(&attrs))
        perror("pthread_attr_init");

    if (pthread_attr_setschedpolicy(&attrs, SCHED_POLICY))
        perror("pthread_attr_setschedpolicy");

    if (pthread_attr_setinheritsched(&attrs, PTHREAD_EXPLICIT_SCHED))
        perror("pthread_attr_setinheritsched");

    args.sleep_time = sleeptime;
    if (pthread_create(&thread, &attrs, &thread_func, &args))
        perror("pthread_create");

    if (pthread_setschedparam(thread, SCHED_POLICY, &sparam))
        perror("pthread_setschedparam");

    sleep(runtime);
    do_run = false;
    pthread_join(thread, &res);

    printf("sleep time: %llu / %llu = %f\n", args.total, args.count,
            (float)args.total / args.count);
    pthread_attr_destroy(&attrs);
    return 0;
}
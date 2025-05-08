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
#include <string.h>
#include <sys/resource.h>
#include <linux/prctl.h>
#include <sys/prctl.h>

static bool do_run = true;

#define SEC2NSEC 1000 * 1000 * 1000
#define __stringify(x) #x
#define stringify(x) __stringify(x)

#define PTHREAD_CALL(func, ...)                                          \
    do {                                                                 \
        int __ret = func(__VA_ARGS__);                                   \
        if (__ret) {                                                     \
            printf("ERROR: " stringify(func) ": %s\n", strerror(__ret)); \
            return __ret;                                                \
        }                                                                \
    } while (0)

int SCHED_POLICY = SCHED_RR;

struct thread_args {
    uint32_t sleep_time;
    uint64_t total;
    uint64_t count;
};

static void *thread_func(void *arg) {
    struct thread_args *args = (struct thread_args *)arg;
    struct timespec ts, te, sleep, rem;

    sleep.tv_sec = 0;
    sleep.tv_nsec = args->sleep_time;
    args->total = 0;
    args->count = 0;
    while (do_run) {
        clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
        nanosleep(&sleep, &rem);
        clock_gettime(CLOCK_MONOTONIC_RAW, &te);
        args->count++;
        args->total +=
            ((te.tv_sec - ts.tv_sec) * SEC2NSEC) + (te.tv_nsec - ts.tv_nsec);
    }
    return NULL;
}

static void show_thread_policy(int policy, struct sched_param params) {
    printf("Thread policy: %s, priority: %d\n",
           (policy == SCHED_FIFO)  ? "SCHED_FIFO" :
           (policy == SCHED_RR)    ? "SCHED_RR" :
           (policy == SCHED_OTHER) ? "SCHED_OTHER" :
                                     "unknown",
           params.sched_priority);
}

int main(int argc, char **argv) {
    pthread_attr_t attrs;
    pthread_t thread;
    struct thread_args args;
    uint32_t runtime;
    uint32_t sleeptime;
    void *res;
    int opt;
    int ret;
    int policy;
    int min_priority, max_priority, priority;
    unsigned int relative = 0;
    struct sched_param sparam;
    struct rlimit rlimit;
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

    CPU_ZERO(&mask);
    CPU_SET(1, &mask);
    sched_setaffinity(getpid(), sizeof(mask), &mask);

    min_priority = sched_get_priority_min(SCHED_POLICY);
    max_priority = sched_get_priority_max(SCHED_POLICY);
    printf("min/max priority: %d/%d\n", min_priority, max_priority);
    rlimit.rlim_cur = max_priority;
    rlimit.rlim_max = max_priority;
    if (setrlimit(RLIMIT_RTPRIO, &rlimit) == -1) {
        perror("setrlimit");
        return errno;
    }

    priority = min_priority + relative;
    if (priority > max_priority)
        priority = max_priority;

    printf("run priority: %d\n", priority);
    sparam.sched_priority = priority;

    PTHREAD_CALL(pthread_attr_init, &attrs);
    PTHREAD_CALL(pthread_attr_setinheritsched, &attrs, PTHREAD_EXPLICIT_SCHED);
    PTHREAD_CALL(pthread_attr_setschedpolicy, &attrs, SCHED_POLICY);
    PTHREAD_CALL(pthread_attr_setschedparam, &attrs, &sparam);
    PTHREAD_CALL(pthread_attr_getschedparam, &attrs, &sparam);
    PTHREAD_CALL(pthread_attr_getschedpolicy, &attrs, &policy);

    PTHREAD_CALL(prctl, PR_SET_TIMERSLACK, 1);
    show_thread_policy(policy, sparam);

    args.sleep_time = sleeptime;
    ret = pthread_create(&thread, &attrs, &thread_func, &args);
    if (ret) {
        printf("pthread_create: %s\n", strerror(ret));
        return ret;
    }

    sleep(runtime);
    do_run = false;
    pthread_join(thread, &res);

    printf("sleep time: %lu / %lu = %f ns\n", args.total, args.count,
           (float)args.total / args.count);
    pthread_attr_destroy(&attrs);
    return 0;
}

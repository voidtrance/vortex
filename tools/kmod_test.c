#include <stdio.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <stdint.h>
#include <unistd.h>
#include <time.h>

#define PAGE_SIZE 4096

static struct data {
    uint64_t runtime;
    uint64_t ticks;
} vdata = { 0 };

static struct config {
    uint16_t sleep;
    uint16_t tick;
} config = { 0 };

int main(int argc, char **argv) {
    struct timespec ts, te, sleep;
    uint32_t count;
    int configfd;
    uint64_t diff_runtime, diff_ticks;
    float avg_runtime, avg_ticks;
    size_t iters = 10000000;

    configfd = open("/dev/vortex", O_RDWR);
    if (configfd < 0) {
        perror("open");
        return -1;
    }

    /*
    char *address = NULL;
    address = mmap(NULL, PAGE_SIZE, PROT_READ, MAP_SHARED, configfd, 0);
    if (address == MAP_FAILED) {
        perror("mmap");
        return -1;
    }
    
    memcpy(&vdata, address, sizeof(vdata));
    printf("%lx %lx\n", vdata.runtime, vdata.ticks);
        */

    config.sleep = 1000;
    config.tick = 83;
    if (write(configfd, &config, sizeof(config)) == -1) {
        perror("write");
        return -1;
    }

    for (count = 0; count < iters; count++) {
        uint64_t old_r = vdata.runtime;
        uint64_t old_t = vdata.ticks;
        if (read(configfd, &vdata, sizeof(vdata)) == -1)
            perror("read");
        diff_runtime += vdata.runtime - old_r;
        diff_ticks += vdata.ticks - old_t;
    }

    printf("runtime = %f, ticks=%f\n", (float)diff_runtime / iters,
           (float)diff_ticks / iters);
    close(configfd);
    return 0;
}
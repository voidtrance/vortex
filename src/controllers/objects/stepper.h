#ifndef __STEPPER_H__
#define __STEPPER_H__
#include <stdint.h>
#include <stdbool.h>

typedef struct {
    bool enabled;
    uint64_t steps;
    uint16_t spr;
    uint8_t microsteps;
} stepper_status_t;

#endif

#ifndef __AXIS_H__
#define __AXIS_H__
#include <stdint.h>
#include <stdbool.h>

typedef struct {
    bool homed;
    float length;
    float position;
} axis_status_t;

#endif

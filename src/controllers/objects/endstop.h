#ifndef __ENDSTOP_H__
#define __ENDSTOP_H__
#include <stdbool.h>

typedef struct {
    bool triggered;
    const char type[4];
} endstop_status_t;

#endif

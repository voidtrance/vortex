#ifndef __TIMING_H__
#define __TIMING_H__
#include <stdint.h>

typedef int (*timer_callback_t)(uint64_t clock_step, void *user_data);

int controller_timer_start(uint64_t frequency, timer_callback_t callback,
						   void *user_data);
void controller_timer_stop(void);

#endif

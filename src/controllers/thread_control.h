#ifndef __TIMING_H__
#define __TIMING_H__
#include <stdint.h>

typedef void (*update_callback_t)(uint64_t clock_step, void *user_data);
typedef void (*completion_callback_t)(void *user_data);

int controller_timer_start(uint64_t frequency, update_callback_t update_cb,
			   completion_callback_t completion_cb,
			   void *user_data);
void controller_timer_stop(void);

#endif

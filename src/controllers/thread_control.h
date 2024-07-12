#ifndef __TIMING_H__
#define __TIMING_H__
#include <stdint.h>

typedef void (*update_callback_t)(uint64_t clock_step, void *user_data);
typedef void (*completion_callback_t)(void *user_data);
typedef void (*event_callback_t)(void *user_data);

int controller_timer_start(update_callback_t update_cb,
			   uint64_t update_frequency,
			   completion_callback_t completion_cb,
			   uint64_t completion_frequency,
			   event_callback_t event_cb,
			   uint64_t event_frequency,
			   void *user_data);
void controller_timer_stop(void);

#endif

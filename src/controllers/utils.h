#ifndef __UTILS_H__
#define __UTILS_H__
#include <stdint.h>

#define SEC_TO_MSEC(x) ((x)*1000)
#define MSEC_TO_USEC(x) SEC_TO_MSEC(x)
#define SEC_TO_USEC(x) (SEC_TO_MSEC(x) * 1000)
#define MSEC_TO_NSEC(x) SEC_TO_USEC(x)
#define SEC_TO_NSEC(x) (SEC_TO_USEC(x) * 1000)
#define KHZ_TO_HZ(x) ((x)*1000)
#define MHZ_TO_HZ(x) (KHZ_TO_HZ(x)*1000)
#define GHZ_TO_HZ(x) (MHZ_TO_HZ(x)*1000)
#define MHZ_TO_NSEC(x) (1000 / (x))
#define GHZ_TO_NSEC(x) (1/(x))
#define HZ_TO_NSEC(x) MHZ_TO_NSEC((x) / MHZ_TO_HZ(1))

#define max(a, b) ((a <= (typeof(a))b) ? b : a)
#define min(a, b) ((a <= (typeof(a))b) ? a : b)

uint32_t str_to_hertz(const char *str);

#endif

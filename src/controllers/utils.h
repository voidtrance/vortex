#ifndef __UTILS_H__
#define __UTILS_H__
#include <stdint.h>

#define KHZ_TO_HZ(x) ((x)*1000)
#define MHZ_TO_HZ(x) (KHZ_TO_HZ(x)*1000)
#define GHZ_TO_HZ(x) (MHZ_TO_HZ(x)*1000)
#define MHZ_TO_NSEC(x) (1000 / (x))
#define GHZ_TO_NSEC(x) (1/(x))
#define HZ_TO_NSEC(x) MHZ_TO_NSEC((x) / MHZ_TO_HZ(1))

uint32_t str_to_hertz(const char *str);

#endif

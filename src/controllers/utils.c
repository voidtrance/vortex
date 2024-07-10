#include <ctype.h>
#include <stdlib.h>
#include "utils.h"

uint32_t str_to_hertz(const char *str)
{
	char *ptr = (char *)str;
	unsigned long n;

	n = strtoul(str, &ptr, 0);
	switch (tolower(*ptr)) {
	case 'k':
		n = KHZ_TO_HZ(n);
		break;
	case 'm':
		n = MHZ_TO_HZ(n);
		break;
	case 'g':
		n = GHZ_TO_HZ(n);
		break;
	default:
		n = 0;
	}

	return n;
}

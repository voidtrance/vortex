/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024  Mitko Haralanov
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include "utils.h"
#include <stdio.h>

uint32_t str_to_hertz(const char *str)
{
	char *ptr = (char *)str;
	unsigned long n;

	n = strtoul(str, &ptr, 0);
	if (strlen(ptr) == 3 && tolower(*(ptr+1)) == 'h' &&
	    tolower(*(ptr+2)) == 'z') {
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
	}

	return n;
}

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
#ifndef __CACHE_H__
#define __CACHE_H__
#include <stddef.h>

typedef struct object_cache object_cache_t;

int object_cache_create(object_cache_t **cache, size_t object_size);
void *object_cache_alloc(object_cache_t *cache);
void object_cache_free(void *object);
void object_cache_destroy(object_cache_t *cache);

#endif

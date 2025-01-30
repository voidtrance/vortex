/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2025 Mitko Haralanov
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
#ifndef __MEM_DEBUG__
#define __MEM_DEBUG__
#include <stdlib.h>
#include <stdint.h>

void *__malloc(size_t, const char *, unsigned int);
#define malloc(size) __malloc(size, __func__, __LINE__)

void *__calloc(size_t, size_t, const char *, unsigned int);
#define calloc(num, size) __calloc(num, size, __func__, __LINE__)

void *__realloc(void *, size_t, const char *, unsigned int);
#define realloc(ptr, size) __realloc(ptr, size, __func__, __LINE__);

void __free(void *, const char *, unsigned int);
#define free(ptr) __free(ptr, __func__, __LINE__)

void *__reallocarray(void *, size_t, size_t, const char *, unsigned int);
#define reallocarray(ptr, num, size) \
    __reallocarray(ptr, num, size, __func__, __LINE__)
#endif

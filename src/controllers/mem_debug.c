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
#define _GNU_SOURCE
#include <stdio.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <unistd.h>
#include <sys/mman.h>
#include "mem_debug.h"

void *__malloc(size_t size, const char *f, unsigned int l) {
    void *(*__malloc_sym)(size_t) = dlsym(RTLD_NEXT, "malloc");
    void *ptr = NULL;


    ptr = __malloc_sym(size);
    if (ptr)
        fprintf(stderr, "malloc:%d:%p:%zu:%s:%u\n", getpid(), ptr, size,
		f, l);

    return ptr;
}

void *__calloc(size_t nmemb, size_t size, const char *f, unsigned int l) {
    void *(*__calloc_sym)(size_t, size_t) = dlsym(RTLD_NEXT, "calloc");
    void *ptr = NULL;

    ptr = __calloc_sym(nmemb, size);
    if (ptr)
	fprintf(stderr, "calloc:%d:%p:%zu:%s:%u\n", getpid(), ptr, nmemb * size,
		f, l);
    return ptr;
}

void *__realloc(void *ptr, size_t size, const char *f, unsigned int l) {
    void *(*__realloc_sym)(void *, size_t) = dlsym(RTLD_NEXT, "realloc");

    ptr = __realloc_sym(ptr, size);
    if (ptr)
	fprintf(stderr, "realloc:%d:%p:%zu:%s:%u\n", getpid(), ptr, size,
		f, l);
    return ptr;
}

void __free(void *ptr, const char *f, unsigned int l) {
    void (*__free_sym)(void *) = dlsym(RTLD_NEXT, "free");

    if (ptr)
	fprintf(stderr, "free:%d:%p:%s:%u\n", getpid(), ptr,
		f, l);
    __free_sym(ptr);
}

void *__reallocarray(void *ptr, size_t nmemb, size_t size, const char *f,
		     unsigned int l) {
    void *(*__reallocarray_sym)(void *, size_t, size_t) = dlsym(RTLD_NEXT,
								"reallocarray");

    ptr = __reallocarray_sym(ptr, nmemb, size);
    if (ptr)
	fprintf(stderr, "reallocarray:%d:%p:%zu:%s:%u\n", getpid(), ptr,
		(nmemb * size), f, l);
    return ptr;
}

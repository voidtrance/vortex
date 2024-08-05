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
#include <stdlib.h>
#include <unistd.h>
#include <stdbool.h>
#include <pthread.h>
#include <errno.h>
#include <sys/queue.h>
#include <stdint.h>
#include "cache.h"
#ifdef VORTEX_DEBUG
#include <stdio.h>
#endif

#define container_of(ptr, member, type) \
    ({ void *__ptr = (void *)ptr; ((type *)(__ptr - offsetof(type, member))); })

struct cache_object {
    STAILQ_ENTRY(cache_object) entry;
    object_cache_t *cache;
    void *ptr;
};

STAILQ_HEAD(cache_object_list, cache_object);

struct object_cache {
    void **memory;
    size_t segment;
    size_t num_segments;
    struct cache_object_list objects;
    struct cache_object_list alloced;
    size_t num_objects;
    size_t object_size;
    pthread_mutex_t lock;
    uint64_t refcount;
};

static bool object_cache_fill(object_cache_t *cache) {
    void *new_memory;
    void *ptr;
    size_t page_size;
    size_t limit;

    /* Allocate a page at a time. */
    page_size = sysconf(_SC_PAGESIZE);
    new_memory = calloc(1, page_size);
    if (!new_memory)
	return false;

    if (cache->segment == cache->num_segments) {
	size_t alloc_size;
	void **new;

	if (!cache->num_segments) {
	    cache->num_segments = 1;
	    alloc_size = 1;
	} else {
	    alloc_size = cache->num_segments * 2;
	}

	new = reallocarray(cache->memory, alloc_size, sizeof(*new));
	if (new) {
	    cache->memory = new;
            cache->num_segments = alloc_size;
        } else {
	    free(new_memory);
	    return false;
	}
    }

    limit = page_size - sizeof(struct cache_object) - cache->object_size;
    for (ptr = new_memory; ptr < new_memory + limit; cache->num_objects++) {
	struct cache_object *object_entry = (struct cache_object *)ptr;

	ptr += sizeof(struct cache_object);
	object_entry->ptr = ptr;
        object_entry->cache = cache;
        ptr += cache->object_size;
	STAILQ_INSERT_TAIL(&cache->objects, object_entry, entry);
    }

    cache->memory[cache->segment++] = new_memory;

    return true;
}

int object_cache_create(object_cache_t **cache_ptr, size_t object_size) {
    object_cache_t *cache;

    if (*cache_ptr == NULL) {
	cache = malloc(sizeof(*cache));
	if (!cache)
	    return -ENOMEM;

	cache->segment = 0;
	cache->num_segments = 0;
	cache->object_size = object_size;
	cache->num_objects = 0;
	cache->refcount = 1;
	cache->memory = NULL;
	STAILQ_INIT(&cache->objects);
	STAILQ_INIT(&cache->alloced);
	pthread_mutex_init(&cache->lock, NULL);

	if (!object_cache_fill(cache)) {
	    free(cache);
	    return -ENOMEM;
	}

	*cache_ptr = cache;
    } else {
	cache = *cache_ptr;
	pthread_mutex_lock(&cache->lock);
	cache->refcount++;
	pthread_mutex_unlock(&cache->lock);
    }

    return 0;
}

void *object_cache_alloc(object_cache_t *cache) {
    struct cache_object *object;

    pthread_mutex_lock(&cache->lock);
    if (STAILQ_EMPTY(&cache->objects)) {
	if (!object_cache_fill(cache)) {
	    pthread_mutex_unlock(&cache->lock);
	    return NULL;
	}
    }

    object = STAILQ_FIRST(&cache->objects);
    STAILQ_REMOVE(&cache->objects, object, cache_object, entry);
    STAILQ_INSERT_TAIL(&cache->alloced, object, entry);
    cache->refcount++;
    pthread_mutex_unlock(&cache->lock);
    return object->ptr;
}

void object_cache_free(void *object) {
    struct cache_object *obj = object - sizeof(struct cache_object);
    object_cache_t *cache = obj->cache;
#ifdef VORTEX_DEBUG
    bool found = false;
#endif

    pthread_mutex_lock(&cache->lock);
#ifdef VORTEX_DEBUG
    STAILQ_FOREACH(obj, &cache->alloced, entry) {
	if (obj->ptr == object) {
	    found = true;
	    break;
	}
    }
    if (!found)
	fprintf(stderr, "Cache object not found in alloced list.\n");
#endif
    STAILQ_REMOVE(&cache->alloced, obj, cache_object, entry);
    STAILQ_INSERT_TAIL(&cache->objects, obj, entry);
    cache->refcount--;
    pthread_mutex_unlock(&cache->lock);
}

void object_cache_destroy(object_cache_t *cache) {
    size_t i;

    pthread_mutex_lock(&cache->lock);
    if (cache->refcount == 0) {
	for (i = 0; i < cache->segment; i++)
	    free(cache->memory[i]);
	free(cache);
	return;
    }
    pthread_mutex_unlock(&cache->lock);
}

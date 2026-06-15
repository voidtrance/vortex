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
#include <stdlib.h>
#include <unistd.h>
#include <stdbool.h>
#include <pthread.h>
#include <errno.h>
#include <debug.h>
#include <stdint.h>
#include <dlist.h>
#include <utils.h>
#include "cache.h"

#define OBJECT_CACHE_TAG 0xdeadbeefc0dedead

struct cache_object {
    dlist_t entry;
    uint64_t tag;
    object_cache_t *cache;
    void *ptr;
#ifdef VORTEX_DEBUG
    uint64_t refcount;
#endif
};

struct object_cache {
    void **memory;
    size_t page_size;
    size_t segment;
    size_t num_segments;
    dlist_t objects;
    dlist_t alloced;
    size_t num_objects;
    size_t object_size;
    pthread_mutex_t lock;
    uint64_t refcount;
};

static bool object_cache_fill(object_cache_t *cache) {
    void *new_memory;
    void *ptr;
    size_t limit;
    size_t memory_size;
    size_t batch = 64;
    size_t per_object_size = cache->object_size + sizeof(struct object_cache);

    /* Allocate enough space for at least 64 objects. */
    memory_size = max(cache->page_size, batch * per_object_size);
    new_memory = calloc(1, memory_size);
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

    limit = memory_size - per_object_size;
    for (ptr = new_memory; ptr < new_memory + limit; cache->num_objects++) {
        struct cache_object *object_entry = (struct cache_object *)ptr;

        ptr += sizeof(struct cache_object);
        object_entry->tag = OBJECT_CACHE_TAG;
        object_entry->ptr = ptr;
        object_entry->cache = cache;
#ifdef VORTEX_DEBUG
        object_entry->refcount = 0;
#endif
        ptr += cache->object_size;
        dlist_elem_insert_tail(&object_entry->entry, &cache->objects);
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

        cache->page_size = sysconf(_SC_PAGESIZE);
        cache->segment = 0;
        cache->num_segments = 0;
        cache->object_size = object_size;
        cache->num_objects = 0;
        cache->refcount = 1;
        cache->memory = NULL;
        DLIST_INITIALIZE(&cache->objects);
        DLIST_INITIALIZE(&cache->alloced);
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
    if (dlist_is_empty(&cache->objects)) {
        if (!object_cache_fill(cache)) {
            pthread_mutex_unlock(&cache->lock);
            return NULL;
        }
    }

    object = dlist_first_elem_container_or_null(&cache->objects, struct cache_object, entry);
    dlist_elem_remove(&object->entry);

#ifdef VORTEX_DEBUG
    if (object->refcount) {
        fprintf(stderr, "Cache object has more than one reference!");
        breakpoint();
    }

    object->refcount++;
#endif

    dlist_elem_insert_tail(&object->entry, &cache->alloced);
    cache->refcount++;
    pthread_mutex_unlock(&cache->lock);
    return object->ptr;
}

void object_cache_free(void *object) {
    struct cache_object *obj;
    object_cache_t *cache;
#ifdef VORTEX_DEBUG
    struct cache_object *__obj;
    bool found = false;
#endif

    if (!object)
        return;

    obj = object - sizeof(struct cache_object);
    if (obj->tag != OBJECT_CACHE_TAG || obj->ptr != object) {
        free(object);
        return;
    }

    cache = obj->cache;

    pthread_mutex_lock(&cache->lock);
#ifdef VORTEX_DEBUG
    dlist_for_each_elem_container(__obj, &cache->alloced, entry)
        found |= __obj->ptr == object;

    if (!found) {
        fprintf(stderr, "Cache object not found in alloced list.\n");
        breakpoint();
    }

    obj->refcount--;
#endif
    dlist_elem_remove(&obj->entry);
    dlist_elem_insert_tail(&obj->entry, &cache->objects);
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

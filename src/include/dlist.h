/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024-2026 Mitko Haralanov
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
#ifndef __DLIST_H__
#define __DLIST_H__

#ifndef container_of
#define container_of(ptr, type, member) ((type *)((unsigned long)(ptr) - offsetof(type, member)))
#endif

typedef struct dlist {
    struct dlist *prev;
    struct dlist *next;
} dlist_t;

#define DLIST_INITIALIZOR(name) { &(name), &(name) }
#define DLIST_DECLARE(name) dlist_t name = DLIST_INITIALIZOR(name)

static inline void DLIST_INITIALIZE(dlist_t *dlist) {
    dlist->next = dlist;
    dlist->prev = dlist;
}

static inline void dlist_elem_insert(dlist_t *new, dlist_t *head) {
    head->next->prev = new;
    new->next = head->next;
    new->prev = head;
    head->next = new;
}

static inline void dlist_elem_insert_tail(dlist_t *new, dlist_t *head) {
    head->prev->next = new;
    new->prev = head->prev;
    head->prev = new;
    new->next = head;
}

static inline void dlist_elem_remove(dlist_t *elem) {
    elem->next->prev = elem->prev;
    elem->prev->next = elem->next;
}

static inline int dlist_elem_is_first(const dlist_t *elem, const dlist_t *head) {
    return elem->prev == head;
}

static inline int dlist_elem_is_last(const dlist_t *elem, const dlist_t *head) {
    return elem->next == head;
}

static inline int dlist_elem_is_head(const dlist_t *elem, const dlist_t *head) {
    return elem == head;
}

static inline int dlist_is_empty(const dlist_t *head) {
    return head->next == head;
}

#define dlist_elem_container(elem, type, member) container_of(elem, type, member)

#define dlist_first_elem_container(elem, type, member) \
    dlist_elem_container((elem)->next, type, member)

#define dlist_last_elem_container(elem, type, member) \
    dlist_elem_container((elem)->prev, type, member)

#define dlist_first_elem_container_or_null(elem, type, member)                \
    ({                                                                        \
        dlist_t *head__ = (elem);                                             \
        dlist_t *elem__ = head__->next;                                       \
        elem__ != head__ ? dlist_elem_container(elem__, type, member) : NULL; \
    })

#define dlist_next_elem_container(elem, member) \
    dlist_elem_container((elem)->member.next, typeof(*(elem)), member)

#define dlist_prev_elem_container(elem, member) \
    dlist_elem_container((elem)->member.prev, typeof(*(elem)), member)

#define dlist_elem_container_is_head(elem, head, member) dlist_elem_is_head(&elem->member, (head))

#define dlist_for_each_elem(elem, head) \
    for (elem = (head)->next; !dlist_elem_is_head(elem, (head)); elem = elem->next)

#define dlist_for_each_elem_container(elem, head, member)                \
    for (elem = dlist_first_elem_container(head, typeof(*elem), member); \
         !dlist_elem_container_is_head(elem, head, member);              \
         elem = dlist_next_elem_container(elem, member))

#define dlist_for_each_elem_container_start_from(elem, head, member) \
    for (; !dlist_elem_container_is_head(elem, head, member);        \
         elem = dlist_next_elem_container(elem, member))

#define dlist_for_each_elem_container_start_reverse(elem, head, member) \
    for (; !dlist_elem_container_is_head(elem, head, member);           \
         elem = dlist_prev_elem_container(elem, member))

#define dlist_for_each_elem_container_continue_from(elem, head, member) \
    for (elem = dlist_next_elem_container(elem, member);                \
         !dlist_elem_container_is_head(elem, head, member);             \
         elem = dlist_next_elem_container(elem, member))

#define dlist_for_each_elem_container_safe(elem, next, head, member)     \
    for (elem = dlist_first_elem_container(head, typeof(*elem), member), \
        next = dlist_next_elem_container(elem, member);                  \
         !dlist_elem_container_is_head(elem, head, member);              \
         elem = next, next = dlist_next_elem_container(elem, member))

#endif
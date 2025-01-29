/*
 * vortex - GCode machine emulator
 * Copyright (C) 2024,2025  Mitko Haralanov
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
#include <stdbool.h>
#include "atomics.h"

#undef DEFINE_FUNCS
#define DEFINE_FUNCS(size, type)                                              \
    type atomic##size##_load(type *ptr) {                                     \
        return __atomic_load_n(ptr, __ATOMIC_SEQ_CST);                        \
    }                                                                         \
    void atomic##size##_store(type *ptr, type value) {                        \
        __atomic_store_n(ptr, value, __ATOMIC_SEQ_CST);                       \
    }                                                                         \
    type atomic##size##_exchange(type *ptr, type value) {                     \
        return __atomic_exchange_n(ptr, value, __ATOMIC_SEQ_CST);             \
    }                                                                         \
    type atomic##size##_compare_exchange(type *ptr, type oldval,              \
                                         type newval) {                       \
        return __atomic_compare_exchange_n(                                   \
            ptr, &oldval, newval, false, __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST); \
    }                                                                         \
    type atomic##size##_add(type *ptr, type value) {                          \
        return __atomic_add_fetch(ptr, value, __ATOMIC_SEQ_CST);              \
    }                                                                         \
    type atomic##size##_sub(type *ptr, type value) {                          \
        return __atomic_sub_fetch(ptr, value, __ATOMIC_SEQ_CST);              \
    }                                                                         \
    type atomic##size##_inc(type *ptr) {                                      \
        return atomic##size##_add(ptr, 1);                                    \
    }                                                                         \
    type atomic##size##_dec(type *ptr) {                                      \
        return atomic##size##_sub(ptr, 1);                                    \
    }                                                                         \
    type atomic##size##_and(type *ptr, type value) {                          \
        return __atomic_and_fetch(ptr, value, __ATOMIC_SEQ_CST);              \
    }                                                                         \
    type atomic##size##_or(type *ptr, type value) {                           \
        return __atomic_or_fetch(ptr, value, __ATOMIC_SEQ_CST);               \
    }                                                                         \
    type atomic##size##_xor(type *ptr, type value) {                          \
        return __atomic_xor_fetch(ptr, value, __ATOMIC_SEQ_CST);              \
    }                                                                         \
    type atomic##size##_not(type *ptr) {                                      \
        return __atomic_nand_fetch(ptr, (type)(-1UL), __ATOMIC_SEQ_CST);      \
    }

#undef __ATOMICS_H__
#define MULTI_INCLUDE
#include "atomics.h"
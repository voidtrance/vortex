/*
 * vortex - GCode machine emulator
 * Copyright (C) 2026 Mitko Haralanov
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
#ifndef __CLANG_LIB_H__
#define __CLANG_LIB_H__
#include <stdbool.h>
#include <stddef.h>
#include <clang-c/Index.h>

typedef enum { VERBOSE_NONE = 0, VERBOSE_INFO, VERBOSE_VERBOSE, VERBOSE_DEBUG } log_level_t;
typedef enum { Q_NONE, Q_CONST, Q_VOLATILE, Q_RESTRICT } qualifier_t;

typedef struct {
    enum CXTypeKind type;
    const char *name;
    qualifier_t qualifier;
    size_t size;
    union {
        struct {
            enum CXTypeKind type;
            const char *name;
            size_t deref_count;
        } pointer;
        struct {
            enum CXTypeKind type;
            const char *name;
            size_t sizes[8];
            size_t n_dims;
        } array;
        struct {
            int value;
        } enum_constant;
    };
} clang_type_t;

typedef struct {
    enum CXTypeKind type;
    const char *name;
    qualifier_t qualifier;
} clang_canonical_type_t;

typedef struct {
    enum CXCursorKind kind;
    clang_type_t base;
    clang_type_t canonical;
    const char *name;
    const char *kind_name;
    const char *filename;
    unsigned int lineno;
    unsigned int column;
    unsigned int offset;
} clang_node_t;

typedef struct {
    clang_node_t *root;
} clang_unit_t;

void clang_set_verbose_level(log_level_t level);

clang_unit_t *clang_unit_init(const char *filename);

bool clang_unit_parse(clang_unit_t *unit);

clang_node_t *clang_node_get_parent(clang_node_t *node);

void clang_node_reset(clang_node_t *node);

clang_node_t *clang_node_first(clang_node_t *node, const enum CXCursorKind kind);

clang_node_t *clang_node_next(clang_node_t *node, const enum CXCursorKind kind);

clang_node_t *clang_node_prev(clang_node_t *node, const enum CXCursorKind kind);

clang_node_t *clang_node_find(clang_node_t *node, const enum CXCursorKind kind);

clang_node_t *clang_node_find_next(clang_node_t *node, const enum CXCursorKind kind);

clang_node_t *clang_node_find_prev(clang_node_t *node, const enum CXCursorKind kind);

clang_node_t *
clang_node_find_by_name(clang_node_t *node, const char *name, const enum CXCursorKind kind);

void clang_unit_destroy(clang_unit_t *unit);

#endif
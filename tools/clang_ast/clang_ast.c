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
#include <stdio.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdbool.h>
#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include "clang_ast.h"

#define __stringify(x) #x
#define stringify(x) __stringify(x)
#define container_of(ptr, type, member)              \
    ({                                               \
        void *__mptr = (void *)(ptr);                \
        ((type *)(__mptr - offsetof(type, member))); \
    })
#define ARRAY_SIZE(arr) ((sizeof((arr)) / (sizeof((arr)[0]))))

#define CONFIG_STRUCT_SUFFIX "_config_params_t"
#define STATUS_STRUCT_SUFFIX "_status_t"
#define COMMAND_STRUCT_SUFFIX "_command_t"

#ifndef __GNUC__
#define UNUSED
#else
#define UNUSED __attribute__((unused))
#endif

#define CXCursor_Any (CXCursor_OverloadCandidate + 1)

/*             Lists   */
#define LIST_POISON1 0xdeadc0de
#define LIST_POISON2 0xc0dedead

struct list_head {
    struct list_head *prev;
    struct list_head *next;
};

#define LIST_HEAD_INIT(name) { &(name), &(name) }
#define LIST_HEAD(name) struct list_head name = LIST_HEAD_INIT(name)

static inline void INIT_LIST_HEAD(struct list_head *list) {
    list->next = list;
    list->prev = list;
}

static inline void
__list_add(struct list_head *new, struct list_head *prev, struct list_head *next) {
    next->prev = new;
    new->next = next;
    new->prev = prev;
    prev->next = new;
}

static UNUSED inline void list_add(struct list_head *new, struct list_head *head) {
    __list_add(new, head, head->next);
}

static inline void list_add_tail(struct list_head *new, struct list_head *head) {
    __list_add(new, head->prev, head);
}

static inline void __list_del(struct list_head *prev, struct list_head *next) {
    next->prev = prev;
    prev->next = next;
}

static inline void __list_del_entry(struct list_head *entry) {
    __list_del(entry->prev, entry->next);
}

static inline void list_del(struct list_head *entry) {
    __list_del_entry(entry);
    entry->next = (void *)LIST_POISON1;
    entry->prev = (void *)LIST_POISON2;
}

static inline int list_is_first(const struct list_head *list, const struct list_head *head) {
    return list->prev == head;
}

static inline int list_is_last(const struct list_head *list, const struct list_head *head) {
    return list->next == head;
}

static inline int list_is_head(const struct list_head *list, const struct list_head *head) {
    return list == head;
}

static inline int list_empty(const struct list_head *head) {
    return head->next == head;
}

#define list_entry(ptr, type, member) container_of(ptr, type, member)
#define list_first_entry(ptr, type, member) list_entry((ptr)->next, type, member)
#define list_last_entry(ptr, type, member) list_entry((ptr)->prev, type, member)
#define list_first_entry_or_null(ptr, type, member)               \
    ({                                                            \
        struct list_head *head__ = (ptr);                         \
        struct list_head *pos__ = head__->next;                   \
        pos__ != head__ ? list_entry(pos__, type, member) : NULL; \
    })
#define list_next_entry(pos, member) list_entry((pos)->member.next, typeof(*(pos)), member)
#define list_prev_entry(pos, member) list_entry((pos)->member.prev, typeof(*(pos)), member)
#define list_entry_is_head(pos, head, member) list_is_head(&pos->member, (head))
#define list_for_each(pos, head) \
    for (pos = (head)->next; !list_is_head(pos, (head)); pos = pos->next)
#define list_for_each_entry(pos, head, member)               \
    for (pos = list_first_entry(head, typeof(*pos), member); \
         !list_entry_is_head(pos, head, member); pos = list_next_entry(pos, member))
#define list_for_each_entry_from(pos, head, member) \
    for (; !list_entry_is_head(pos, head, member); pos = list_next_entry(pos, member))
#define list_for_each_entry_from_reverse(pos, head, member) \
    for (; !list_entry_is_head(pos, head, member); pos = list_prev_entry(pos, member))
#define list_for_each_entry_continue(pos, head, member)                              \
    for (pos = list_next_entry(pos, member); !list_entry_is_head(pos, head, member); \
         pos = list_next_entry(pos, member))
#define list_for_each_entry_safe(pos, n, head, member)                                         \
    for (pos = list_first_entry(head, typeof(*pos), member), n = list_next_entry(pos, member); \
         !list_entry_is_head(pos, head, member); pos = n, n = list_next_entry(n, member))

struct clang_node_struct {
    clang_node_t node;
    CXCursor cursor;
    struct list_head entry;
    struct clang_node_struct *parent;
    struct clang_node_struct *iter;
    struct list_head children;
    uint16_t n_children;
};

struct clang_unit_struct {
    clang_unit_t unit;
    struct clang_node_struct *node;
    CXIndex index;
    CXTranslationUnit tu;
    CXCursor cursor;
};

log_level_t verbose_level = VERBOSE_NONE;

static void logp(log_level_t level, const char *format, ...) {
    va_list args;

    if (level > verbose_level)
        return;

    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
}

static qualifier_t get_qualifier_for_type(CXType type) {
    if (clang_isConstQualifiedType(type))
        return Q_CONST;
    else if (clang_isVolatileQualifiedType(type))
        return Q_VOLATILE;
    else if (clang_isRestrictQualifiedType(type))
        return Q_RESTRICT;

    return Q_NONE;
}

static void strip(char *str, const char *sub) {
    char *p;
    char *end;

    if (!str || !sub || !*sub)
        return;

    p = strstr(str, sub);
    if (!p)
        return;

    end = p + strlen(sub);

    if (p - 1 > str && isspace(*(p - 1)))
        p--;

    if (*end && isspace(*end))
        end++;

    memmove(p, end, strlen(end) + 1);
}

static char *get_type_name(CXType type, qualifier_t qualifier) {
    CXString str;
    char *c_str;

    str = clang_getTypeSpelling(type);
    c_str = strdup(clang_getCString(str));

    /*
    switch (qualifier) {
    case Q_CONST:
        strip(c_str, "const");
        break;
    case Q_VOLATILE:
        strip(c_str, "volatile");
        break;
    case Q_RESTRICT:
        strip(c_str, "restrict");
        break;
    default:
        break;
    }
    */

    /* Clang AST parsing does not provide a way to get if
     * a pointer is qualified. Therefore, we have to do a
     * substring stripping of all qualifiers. */
    strip(c_str, "const");
    strip(c_str, "volatile");
    strip(c_str, "restrict");

    return c_str;
}

static void get_node_info(clang_type_t *type, CXType clang_type) {
    CXType _type;
    qualifier_t qualifier;

    type->size = clang_Type_getSizeOf(clang_type);

    switch (type->type) {
    case CXType_ConstantArray:
        type->array.sizes[type->array.n_dims] = clang_getArraySize(clang_type);
        type->array.n_dims++;
        _type = clang_getElementType(clang_type);

        while (_type.kind == CXType_ConstantArray) {
            type->array.sizes[type->array.n_dims] = clang_getArraySize(_type);
            type->array.n_dims++;
            _type = clang_getArrayElementType(_type);
        }

        type->array.type = _type.kind;
        qualifier = get_qualifier_for_type(_type);
        if (qualifier)
            _type = clang_getUnqualifiedType(_type);

        type->array.name = get_type_name(_type, qualifier);
        break;
    case CXType_Pointer:
        _type = clang_getPointeeType(clang_type);
        type->pointer.type = _type.kind;
        while (type->pointer.type == CXType_Pointer) {
            type->pointer.deref_count++;
            type->pointer.type = clang_getPointeeType(_type).kind;
        }

        type->size = clang_Type_getSizeOf(_type);
        qualifier = get_qualifier_for_type(_type);
        if (qualifier)
            _type = clang_getUnqualifiedType(_type);

        type->pointer.name = get_type_name(_type, qualifier);
        break;
    default:
        break;
    }
}

static void set_cursor_type(clang_node_t *node, const CXCursor cursor) {
    CXType clang_type;
    CXType _type;

    clang_type = clang_getCursorType(cursor);
    node->base.type = clang_type.kind;
    node->base.qualifier = get_qualifier_for_type(clang_type);
    node->base.name = get_type_name(clang_type, node->base.qualifier);

    _type = clang_getCanonicalType(clang_type);
    node->canonical.type = _type.kind;
    node->canonical.qualifier = get_qualifier_for_type(_type);
    node->canonical.name = get_type_name(_type, node->canonical.qualifier);

    get_node_info(&node->base, clang_type);
    get_node_info(&node->canonical, _type);

    switch (clang_getCursorKind(cursor)) {
    case CXCursor_EnumConstantDecl:
        node->base.enum_constant.value = clang_getEnumConstantDeclValue(cursor);
    default:
        break;
    }
}

static struct clang_node_struct *get_cursor_node(const CXCursor cursor) {
    struct clang_node_struct *node;
    CXString str;
    CXSourceLocation location;
    CXFile location_file;

    node = calloc(1, sizeof(*node));
    if (!node)
        return NULL;

    INIT_LIST_HEAD(&node->children);
    node->cursor = cursor;
    node->node.kind = clang_getCursorKind(cursor);
    str = clang_getCursorKindSpelling(node->node.kind);
    node->node.kind_name = strdup(clang_getCString(str));
    clang_disposeString(str);
    str = clang_getCursorSpelling(cursor);
    node->node.name = strdup(clang_getCString(str));
    clang_disposeString(str);
    location = clang_getCursorLocation(cursor);
    clang_getSpellingLocation(location, &location_file, &node->node.lineno, &node->node.column,
                              &node->node.offset);
    if (location_file) {
        str = clang_getFileName(location_file);
        node->node.filename = strdup(clang_getCString(str));
        clang_disposeString(str);
    }

    set_cursor_type(&node->node, node->cursor);

    return node;
}

static void destroy_type(clang_type_t *type) {
    switch (type->type) {
    case CXType_ConstantArray:
        free((char *)type->array.name);
        break;
    case CXType_Pointer:
        free((char *)type->pointer.name);
        break;
    default:
        break;
    };
}
static void destroy_nodes(struct clang_node_struct *head) {
    struct clang_node_struct *node;
    struct clang_node_struct *next;

    list_for_each_entry_safe(node, next, &head->children, entry) {
        list_del(&node->entry);
        destroy_nodes(node);
    }

    destroy_type(&head->node.base);
    free((char *)head->node.canonical.name);
    free((char *)head->node.name);
    free((char *)head->node.kind_name);
    free((char *)head->node.filename);
    free(head);
}

static void print_node(clang_node_t *node, uint8_t level) {
    clang_node_t *parent = clang_node_get_parent(node);

    logp(VERBOSE_VERBOSE, "%*cNode({%s -> %u:%u}[%s,%u], parent={%s}[%s])\n", level, ' ',
         node->name, node->lineno, node->column, node->kind_name, node->base.type,
         parent ? parent->name : "None", parent ? parent->kind_name : "None");
}

static void dump_tree(struct clang_node_struct *root, uint8_t level) {
    struct clang_node_struct *child;

    print_node(&root->node, level);
    list_for_each_entry(child, &root->children, entry) dump_tree(child, level + 1);
}

static struct clang_node_struct *find_cursor_node(struct clang_node_struct *root, CXCursor cursor) {
    struct clang_node_struct *child;
    struct clang_node_struct *parent = NULL;

    if (clang_equalCursors(root->cursor, cursor))
        return root;

    list_for_each_entry(child, &root->children, entry) {
        parent = find_cursor_node(child, cursor);
        if (parent)
            break;
    }

    return parent;
}

static UNUSED void deduplicate_tree(struct clang_node_struct *root) {
    struct clang_node_struct *sibling;
    struct clang_node_struct *next;
    struct clang_node_struct *parent = root->parent;

    if (!parent && !list_empty(&root->children)) {
        deduplicate_tree(list_first_entry(&root->children, struct clang_node_struct, entry));
        return;
    }

    print_node(&root->node, 0);
    list_for_each_entry_safe(sibling, next, &parent->children, entry) {
        struct clang_node_struct *sibling_child =
            list_first_entry_or_null(&sibling->children, struct clang_node_struct, entry);

        if (clang_equalCursors(root->cursor, sibling->cursor))
            continue;

        if (sibling_child) {
            if (clang_equalCursors(sibling_child->cursor, root->cursor)) {
                list_del(&root->entry);
                destroy_nodes(root);
            }

            deduplicate_tree(sibling_child);
        }

        deduplicate_tree(sibling);
    }
}

static enum CXChildVisitResult
visitor(CXCursor cursor, CXCursor cursor_parent, CXClientData clientData) {
    CXSourceLocation location = clang_getCursorLocation(cursor);
    struct clang_node_struct *root = (struct clang_node_struct *)clientData;
    struct clang_node_struct *node;
    struct clang_node_struct *parent;
    struct clang_node_struct *duplicate;

    if (clang_Location_isFromMainFile(location) == 0)
        return CXChildVisit_Continue;

    node = get_cursor_node(cursor);
    if (!node)
        return CXChildVisit_Break;

    logp(VERBOSE_DEBUG, "Visiting %s, ", node->node.name);
    parent = find_cursor_node(root, cursor_parent);
    if (!parent)
        return CXChildVisit_Break;

    duplicate = find_cursor_node(root, cursor);
    if (duplicate) {
        list_del(&duplicate->entry);
        destroy_nodes(node);
        duplicate->parent->n_children--;
        node = duplicate;
    }

    node->parent = parent;
    list_add_tail(&node->entry, &parent->children);
    parent->n_children++;
    return CXChildVisit_Recurse;
}

void clang_set_verbose_level(log_level_t level) {
    verbose_level = level;
}

clang_unit_t *clang_unit_init(const char *pathname) {
    struct clang_unit_struct *unit;
    const char *args[] = { "-isystem",
                           "/usr/include",
                           "-resource-dir",
                           "/usr/lib/clang/" stringify(__clang_major__),
                           "-I.",
                           "-I../../src/core/kinematics",
                           "-I../../src/include",
                           "-I../../src/lib/atomics" };

    unit = calloc(1, sizeof(*unit));
    if (!unit) {
        return NULL;
    }

    logp(VERBOSE_DEBUG, "Clang resource path: %s\n", args[3]);
    logp(VERBOSE_INFO, "Processing: %s\n", pathname);
    unit->index = clang_createIndex(0, 1);
    logp(VERBOSE_DEBUG, "Index: 0x%p\n", unit->index);
    unit->tu = clang_parseTranslationUnit(unit->index, pathname, args, ARRAY_SIZE(args), NULL, 0,
                                          CXTranslationUnit_None);
    logp(VERBOSE_DEBUG, "Translation unit 0x%p\n", unit->tu);
    if (!unit->tu) {
        clang_disposeIndex(unit->index);
        free(unit);
        return NULL;
    }

    unit->cursor = clang_getTranslationUnitCursor(unit->tu);
    unit->node = get_cursor_node(unit->cursor);
    unit->unit.root = &unit->node->node;
    return &unit->unit;
}

bool clang_unit_parse(clang_unit_t *unit) {
    struct clang_unit_struct *unit_ptr = container_of(unit, struct clang_unit_struct, unit);
    unsigned int ret;

    ret = clang_visitChildren(unit_ptr->cursor, visitor, unit_ptr->node);
    dump_tree(unit_ptr->node, 0);
    return (bool)(!ret);
}

clang_node_t *clang_node_get_parent(clang_node_t *node) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);
    if (node_ptr->parent)
        return &node_ptr->parent->node;
    return NULL;
}

void clang_node_reset(clang_node_t *node) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);
    node_ptr->iter = NULL;
}

clang_node_t *clang_node_first(clang_node_t *node, const enum CXCursorKind kind) {
    clang_node_t *first;

    clang_node_reset(node);
    first = clang_node_next(node, kind);
    if (!first)
        clang_node_reset(node);

    return first;
}

clang_node_t *clang_node_next(clang_node_t *node, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);

    if (list_empty(&node_ptr->children) ||
        (node_ptr->iter && list_is_last(&node_ptr->iter->entry, &node_ptr->children)))
        return NULL;

    if (!node_ptr->iter) {
        node_ptr->iter = list_first_entry(&node_ptr->children, typeof(*node_ptr->iter), entry);

        if (kind == CXCursor_Any)
            return &node_ptr->iter->node;
        else if (node_ptr->iter->node.kind == kind)
            return &node_ptr->iter->node;
    }

    list_for_each_entry_continue(node_ptr->iter, &node_ptr->children, entry) {
        if (kind != CXCursor_Any && kind != node_ptr->iter->node.kind)
            continue;

        return &node_ptr->iter->node;
    }

    return NULL;
}

clang_node_t *clang_node_prev(clang_node_t *node, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);

    if (list_empty(&node_ptr->children) ||
        (node_ptr->iter && list_is_first(&node_ptr->iter->entry, &node_ptr->children)))
        return NULL;

    if (!node_ptr->iter) {
        node_ptr->iter = list_last_entry(&node_ptr->children, typeof(*node_ptr->iter), entry);

        if (kind == CXCursor_Any)
            return &node_ptr->iter->node;
        else if (node_ptr->iter->node.kind == kind)
            return &node_ptr->iter->node;
    }

    list_for_each_entry_from_reverse(node_ptr->iter, &node_ptr->children, entry) {
        if (kind != CXCursor_Any && kind != node_ptr->iter->node.kind)
            continue;

        return &node_ptr->iter->node;
    }

    return NULL;
}

static clang_node_t *node_find(struct clang_node_struct *node, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr;
    clang_node_t *match;

    list_for_each_entry(node_ptr, &node->children, entry) {
        if (node_ptr->node.kind == kind)
            return &node_ptr->node;
        match = node_find(node_ptr, kind);
        if (match)
            return match;
    }

    return NULL;
}

clang_node_t *clang_node_find(clang_node_t *node, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);
    return node_find(node_ptr, kind);
}

unsigned level = 0;

clang_node_t *clang_node_find_next(clang_node_t *node, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);
    struct clang_node_struct *parent = node_ptr->parent;

    while (parent) {
        node_ptr = list_next_entry(node_ptr, entry);
        if (!list_is_head(&node_ptr->entry, &parent->children)) {
            if (node_ptr->node.kind == kind)
                return &node_ptr->node;
        }

        list_for_each_entry_from(node_ptr, &parent->children, entry) {
            node = node_find(node_ptr, kind);
            if (node)
                return node;
        }

        node_ptr = parent;
        parent = parent->parent;
    }

    return NULL;
}

clang_node_t *clang_node_find_prev(clang_node_t *node, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);
    struct clang_node_struct *parent = node_ptr->parent;

    while (parent) {
        node_ptr = list_prev_entry(node_ptr, entry);
        if (!list_is_head(&node_ptr->entry, &parent->children)) {
            if (node_ptr->node.kind == kind)
                return &node_ptr->node;
        }

        list_for_each_entry_from_reverse(node_ptr, &parent->children, entry) {
            node = node_find(node_ptr, kind);
            if (node)
                return node;
        }

        node_ptr = parent;
        parent = parent->parent;
    }

    return NULL;
}

static clang_node_t *
node_find_by_name(struct clang_node_struct *node, const char *name, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr;
    clang_node_t *match;

    list_for_each_entry(node_ptr, &node->children, entry) {
        if (!strncmp(node_ptr->node.name, name, strlen(name)) &&
            (kind == CXCursor_Any || node_ptr->node.kind == kind))
            return &node_ptr->node;
        match = node_find_by_name(node_ptr, name, kind);
        if (match)
            return match;
    }

    return NULL;
}

clang_node_t *
clang_node_find_by_name(clang_node_t *node, const char *name, const enum CXCursorKind kind) {
    struct clang_node_struct *node_ptr = container_of(node, struct clang_node_struct, node);
    return node_find_by_name(node_ptr, name, kind);
}

void clang_unit_destroy(clang_unit_t *unit) {
    struct clang_unit_struct *unit_ptr;

    if (!unit)
        return;

    unit_ptr = container_of(unit, struct clang_unit_struct, unit);

    if (unit_ptr->tu) {
        clang_disposeTranslationUnit(unit_ptr->tu);
        destroy_nodes(unit_ptr->node);
    }

    if (unit_ptr->index)
        clang_disposeIndex(unit_ptr->index);

    free(unit_ptr);
}

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
#ifndef __OBJECT_DEFS_H__
#define __OBJECT_DEFS_H__
#include <stdint.h>
#include <sys/queue.h>
#include <stdlib.h>
#include "auto-klass.h"

typedef unsigned long core_object_id_t;
#define CORE_OBJECT_ID_INVALID (-1UL)

/*
 * Common command structure. This structure will be
 * filled out by the controller core when a object
 * command is submitted and will be passed to the
 * object.
 */
typedef struct core_object_command {
    uint64_t command_id;
    uint16_t object_cmd_id;
    void *args;
} core_object_command_t;

typedef struct core_object core_object_t;

#endif

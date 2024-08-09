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
#ifndef __OBJECTS_COMMON_DEFS_H__
#define __OBJECTS_COMMON_DEFS_H__
#include "objects/object_defs.h"
#include "events.h"
#include "debug.h"

#define CMD_ERROR_PREFIX (0xdeadbeef)
#define CMD_ID_IS_ERROR(x) ((x) >> 32 == CMD_ERROR_PREFIX)
#define CMD_ID_ERROR(x) ((int32_t)((x) & ~(CMD_ERROR_PREFIX << 32)))

typedef core_object_t *(*object_lookup_cb_t)(const core_object_type_t,
                                             const char *, void *);
typedef void (*complete_cb_t)(uint64_t, int, void *);
typedef uint64_t (*cmd_submit_cb_t)(core_object_t *, core_object_id_t, uint16_t,
				    void *, complete_cb_t, void *);
typedef void (*log_cb_t)(core_log_level_t, core_object_type_t, const char *,
			 const char *, ...);
/*
 * Data structure given to all the objects.
 */
typedef struct {
    object_lookup_cb_t object_lookup;
    complete_cb_t completion_callback;
    event_register_t event_register;
    event_register_t event_unregister;
    event_submit_t event_submit;
    cmd_submit_cb_t cmd_submit;
    log_cb_t log;
    void *cb_data;
} core_call_data_t;

/*
 * Common object structure. Objects should wrap
 * this structure in their own object-specific
 * structure.
 * If wrapped, this structure should be the
 * first member of the object-specific
 * structure.
 */
struct core_object {
    core_object_type_t type;
    const char *name;
    LIST_ENTRY(core_object) entry;

    int (*init)(core_object_t *object);
    void (*reset)(core_object_t *object);
    int (*exec_command)(core_object_t *object, core_object_command_t *cmd);
    void (*get_state)(core_object_t *object, void *);
    /*
     * Object update callback. This callback will be called
     * by the timing loop to update the object's state.
     *    - ticks are the number of controller clock ticks that have
     *      elapsed since the last update. The rate of change of
     *      this value depends on the controller's running frequency.
     *    - runtime is the absolute wall clock runtime (in ns) of
     *      the emulator.
     */
    void (*update)(core_object_t *object, uint64_t ticks, uint64_t runtime);
    void (*destroy)(core_object_t *object);

    core_call_data_t call_data;
};

static inline core_object_id_t core_object_to_id(core_object_t *object) {
    return (core_object_id_t)object;
}

static inline core_object_t *core_id_to_object(core_object_id_t id) {
    if (id != CORE_OBJECT_ID_INVALID)
      return (core_object_t *)id;
    return NULL;
}

#define CORE_LOOKUP_OBJECT(obj, type, name)				\
    (((core_object_t *)(obj))->call_data.object_lookup(			\
	(type), (name),							\
	((core_object_t *)(obj))->call_data.cb_data))
#define CORE_CMD_COMPLETE(obj, id, status)				\
    (((core_object_t *)(obj))->call_data.completion_callback(		\
	(id), (status),	((core_object_t *)(obj))->call_data.cb_data))
#define CORE_EVENT_REGISTER(obj, type, event, name, handler)		\
    (((core_object_t *)(obj))->call_data.event_register(		\
	(type), (event), (name), ((core_object_t *)(obj)), (handler),	\
	((core_object_t *)(obj))->call_data.cb_data))
#define CORE_EVENT_UNREGISTER(obj, type, event, name)			\
    (((core_object_t *)(obj))->call_data.event_unregister(		\
	(type), (event), (name), ((core_object_t *)(obj)), (handler),	\
	((core_object_t *)(obj))->call_data.cb_data))
#define CORE_EVENT_SUBMIT(obj, type, id, data)				\
    (((core_object_t *)(obj))->call_data.event_submit(			\
	(type), (id), (data),						\
	((core_object_t *)(obj))->call_data.cb_data))
#define CORE_CMD_SUBMIT(obj, target, cmd_id, handler, args)		\
    (((core_object_t *)(obj))->call_data.cmd_submit(			\
	((core_object_t *)(obj)), core_object_to_id(target), (cmd_id),	\
	((void *)(args)), (handler),					\
	((core_object_t *)(obj))->call_data.cb_data))

static inline void core_object_destroy(core_object_t *object) {
    free((char *)object->name);
}

#endif

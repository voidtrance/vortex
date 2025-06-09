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
#ifndef __OBJECTS_COMMON_DEFS_H__
#define __OBJECTS_COMMON_DEFS_H__
#include <logging.h>
#include "objects/object_defs.h"
#include "events.h"

#define __maybe_unused __attribute__((__unused__))

#define CMD_ERROR_PREFIX (0xdeadbeef)
#define CMD_ID_IS_ERROR(x) ((x) >> 32 == CMD_ERROR_PREFIX)
#define CMD_ID_ERROR(x) ((int32_t)((x) & ~(CMD_ERROR_PREFIX << 32)))

typedef core_object_t *(*object_lookup_cb_t)(const core_object_type_t,
                                             const char *, void *);
typedef core_object_t **(*object_list_cb_t)(const core_object_type_t, void *);
typedef void (*complete_cb_t)(uint64_t, int64_t, void *, void *);
typedef uint64_t (*cmd_submit_cb_t)(core_object_t *, core_object_id_t, uint16_t,
				    void *, complete_cb_t, void *);

/*
 * Data structure given to all the objects.
 */
typedef struct {
    object_lookup_cb_t object_lookup;
    object_list_cb_t object_list;
    complete_cb_t completion_callback;
    event_register_t event_register;
    event_register_t event_unregister;
    event_submit_t event_submit;
    cmd_submit_cb_t cmd_submit;
    void *v_cmd_exec;
    void *v_get_state;
    vortex_logger_t *logger;
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
    /*
     * The type of the object. This is set by the
     * object creation function.
     */
    core_object_type_t type;

    /*
     * The object name. Set during object creation.
     */
    const char *name;

    /*
     * Object update frequency in HZ. This is how
     * frequently the `update` callback will be called.
     */
    uint64_t update_frequency;

    /*
     * This member is for internal use.
     */
    LIST_ENTRY(core_object) entry;

    /*
     * Initialize the object.
     * All objects are initialized before the update
     * loop begins.
     */
    int (*init)(core_object_t *object);

    /*
     * Reset the object state.
     * This function is called when the emulator is
     * reset.
     */
    void (*reset)(core_object_t *object);

    /*
     * Object command execution function.
     * This function is called when a command is
     * submitted to the object.
     *    - cmd is the command to execute.
     *    - return value is the command ID of the
     *      command that was executed. If the command
     *      failed, the return value should be
     *      CMD_ERROR_PREFIX | error_code.
    */
    int (*exec_command)(core_object_t *object, core_object_command_t *cmd);

    /*
     * Object state retrieval function.
     * This function is called when the object
     * state is requested.
     *    - state is a pointer to the state structure
     *      that will be filled by the object.
     */
    void (*get_state)(core_object_t *object, void *state);

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

    /*
     * Destory the object.
     * This function should free all object resources.
     */
    void (*destroy)(core_object_t *object);

    /*
     * This is structure is for internal use only.
     */
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

#define CORE_LOOKUP_OBJECT(obj, type, name)                             \
    (((core_object_t *)(obj))->call_data.object_lookup(                 \
        (type), (name), ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_LIST_OBJECTS(obj, type)                                  \
    (((core_object_t *)(obj))->call_data.object_list(	                \
        (type), ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_CMD_COMPLETE(obj, id, status, data)                        \
    (((core_object_t *)(obj))->call_data.completion_callback(           \
        __atomic_exchange_n(&(id), 0, __ATOMIC_SEQ_CST), (status),      \
        (data), ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_EVENT_REGISTER(obj, type, event, name, handler)               \
    (((core_object_t *)(obj))                                              \
         ->call_data.event_register(                                       \
             (type), (event), (name), ((core_object_t *)(obj)), (handler), \
             ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_EVENT_UNREGISTER(obj, type, event, name)                      \
    (((core_object_t *)(obj))                                              \
         ->call_data.event_unregister(                                     \
             (type), (event), (name), ((core_object_t *)(obj)), (handler), \
             ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_EVENT_SUBMIT(obj, event, data)                            \
    (((core_object_t *)(obj))                                          \
         ->call_data.event_submit(                                     \
             (event), core_object_to_id((core_object_t *)obj), (data), \
             ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_CMD_SUBMIT(obj, target, cmd_id, handler, args)          \
    (((core_object_t *)(obj))                                        \
         ->call_data.cmd_submit(((core_object_t *)(obj)),            \
                                core_object_to_id(target), (cmd_id), \
                                ((void *)(args)), (handler),         \
                                ((core_object_t *)(obj))->call_data.cb_data))
#define CORE_LOG(obj, level, fmt, ...)                                      \
    (vortex_logger_log(((core_object_t *)(obj))->call_data.logger, (level), \
                       __FILE__, __LINE__, (fmt), ##__VA_ARGS__))

#define log_debug(obj, fmt, ...) \
    CORE_LOG(obj, LOG_LEVEL_DEBUG, fmt, ##__VA_ARGS__)
#define log_verbose(obj, fmt, ...) \
    CORE_LOG(obj, LOG_LEVEL_VERBOSE, fmt, ##__VA_ARGS__)
#define log_info(obj, fmt, ...) \
    CORE_LOG(obj, LOG_LEVEL_INFO, fmt, ##__VA_ARGS__)
#define log_warning(obj, fmt, ...) \
    CORE_LOG(obj, LOG_LEVEL_WARNING, fmt, ##__VA_ARGS__)
#define log_error(obj, fmt, ...) \
    CORE_LOG(obj, LOG_LEVEL_ERROR, fmt, ##__VA_ARGS__)
#define log_critical(obj, fmt, ...) \
    CORE_LOG(obj, LOG_LEVEL_CRITICAL, fmt, ##__VA_ARGS__)

static inline void core_object_destroy(core_object_t *object) {
    free((char *)object->name);
}

#endif

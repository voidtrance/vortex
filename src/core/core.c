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
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <cache.h>
#include <dlfcn.h>
#include <libgen.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <structmember.h>
#include <sys/queue.h>
#include <utils.h>

#include "core.h"
#include "events.h"
#include "common_defs.h"
#include "thread_control.h"
#include "objects/object_defs.h"
#include "objects/axis.h"
#include "objects/endstop.h"
#include "objects/heater.h"
#include "objects/probe.h"
#include "objects/stepper.h"
#include "objects/thermistor.h"

static const char *module_path = NULL;
static PyObject *VortexCoreError;
typedef core_object_t *(*object_create_func_t)(const char *, void *);

#define MAX_COMPLETIONS 256

typedef struct {
    struct __comp_entry {
	uint64_t id;
	int result;
    } *entries;
    size_t size;
    size_t head;
    size_t tail;
} core_object_completion_data_t;

typedef struct event_subscription {
    STAILQ_ENTRY(event_subscription) entry;
    core_object_type_t object_type;
    core_object_id_t object_id;
    bool is_python;
    union {
	struct {
	    core_object_t *object;
	    event_handler_t handler;
	} core;
	struct {
	    PyObject *handler;
	} python;
    };
} event_subscription_t;

typedef struct event {
    STAILQ_ENTRY(event) entry;
    core_object_event_type_t type;
    core_object_type_t object_type;
    core_object_id_t object_id;
    void *data;
    bool should_free;
} core_event_t;

typedef struct core_command {
    STAILQ_ENTRY(core_command) entry;
    core_object_t *source;
    core_object_id_t target_id;
    core_object_command_t command;
    complete_cb_t handler;
    void *caller_data;
} core_command_t;

typedef struct {
    PyObject *module;
    uint8_t level;
} core_logging_data_t;

#define CMD_ID_MAKE_ERROR(x) ((int64_t)(((uint64_t)CMD_ERROR_PREFIX << 32) | x))

typedef LIST_HEAD(core_object_list, core_object) core_object_list_t;

#define STAILQ_DEFINE(name, type)		\
    typedef struct {				\
	pthread_mutex_t lock;			\
	struct {				\
	    struct type *stqh_first;		\
	    struct type **stqh_last;		\
	} list;					\
    } name;

STAILQ_DEFINE(core_command_list_t, core_command);
STAILQ_DEFINE(core_events_t, event);
STAILQ_DEFINE(core_event_handlers_t, event_subscription);

typedef struct {
    PyObject_HEAD
    void *object_libs[OBJECT_TYPE_MAX];
    object_create_func_t object_create[OBJECT_TYPE_MAX];
    core_object_list_t objects[OBJECT_TYPE_MAX];
    core_command_list_t cmds;
    core_command_list_t submitted;
    uint64_t ticks;
    uint64_t runtime;

    /* Command completion */
    core_object_completion_data_t *completions;
    PyObject *python_complete_cb;

    /* Event handling */
    core_event_handlers_t event_handlers[OBJECT_EVENT_MAX];
    object_cache_t *event_cache;
    core_events_t events;
} core_t;

static core_object_t *core_object_find(const core_object_type_t type,
				       const char *name, void *data);
static void core_object_update(uint64_t ticks, uint64_t runtime,
			       void *user_data);
static void core_process_work(void *user_data);

/* Object callbacks */
static void core_object_command_complete(uint64_t command_id, int result,
					 void *data);
static int core_object_event_register(const core_object_type_t object_type,
				      const core_object_event_type_t event,
				      const char *name, core_object_t *object,
				      event_handler_t handler, void *user_data);
static int core_object_event_unregister(const core_object_type_t object_type,
					const core_object_event_type_t event,
					const char *name, core_object_t *object,
					event_handler_t handler,
					void *user_data);
static int core_object_event_submit(const core_object_event_type_t event,
                                    const core_object_id_t id, void *event_data,
                                    void *user_data);
static uint64_t core_object_command_submit(core_object_t *source,
                                           core_object_id_t target_id,
                                           uint16_t obj_cmd_id, void *args,
                                           complete_cb_t handler,
                                           void *user_data);

static core_call_data_t core_call_data = {0};
static core_logging_data_t logging;

static PyObject *vortex_core_new(PyTypeObject *type, PyObject *args,
				 PyObject *kwargs) {
    core_t *core;

    core = (core_t *)type->tp_alloc(type, 0);
    core->completions = calloc(1, sizeof(*core->completions));
    if (!core->completions) {
	type->tp_free((PyObject *)core);
	return NULL;
    }

    core->completions->size = MAX_COMPLETIONS;
    core->completions->entries = calloc(core->completions->size,
					sizeof(*core->completions->entries));
    if (!core->completions->entries) {
	free(core->completions);
	type->tp_free((PyObject *)core);
	return NULL;
    }

    if (object_cache_create(&core->event_cache, sizeof(core_event_t))) {
	free(core->completions->entries);
	free(core->completions);
	type->tp_free((PyObject *)core);
	return NULL;
    }

    core_call_data.object_lookup = core_object_find;
    core_call_data.completion_callback = core_object_command_complete;
    core_call_data.event_register = core_object_event_register;
    core_call_data.event_unregister = core_object_event_unregister;
    core_call_data.event_submit = core_object_event_submit;
    core_call_data.cmd_submit = core_object_command_submit;
    core_call_data.log = core_log;
    core_call_data.cb_data = core;

    return (PyObject *)core;
}

static int vortex_core_init(core_t *self, PyObject *args, PyObject *kwargs) {
    char *kws[] = {"debug",  NULL};
    core_object_type_t type;
    core_object_event_type_t event;
    uint8_t debug_level = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "i", kws, &debug_level))
	return -1;

    logging.level = debug_level;

    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++)
        LIST_INIT(&self->objects[type]);

    for (event = 0; event < OBJECT_EVENT_MAX; event++) {
	pthread_mutex_init(&self->event_handlers[event].lock, NULL);
	STAILQ_INIT(&self->event_handlers[event].list);
    }

    pthread_mutex_init(&self->events.lock, NULL);
    STAILQ_INIT(&self->events.list);

    pthread_mutex_init(&self->cmds.lock, NULL);
    STAILQ_INIT(&self->cmds.list);

    pthread_mutex_init(&self->submitted.lock, NULL);
    STAILQ_INIT(&self->submitted.list);

    self->ticks = 0;
    self->runtime = 0;
    self->completions->head = 0;
    self->completions->tail = 0;

    return 0;
}

static void vortex_core_dealloc(core_t *self) {
    core_object_type_t type;

    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
	core_object_t *object;
	core_object_t *object_next;

	if (LIST_EMPTY(&self->objects[type]))
	    continue;

	object = LIST_FIRST(&self->objects[type]);
	while (object) {
	    object_next = LIST_NEXT(object, entry);
	    if (object->destroy)
		object->destroy(object);
	    else
		core_object_destroy(object);
	    object = object_next;
	}

	if (self->object_libs[type])
	    dlclose(self->object_libs[type]);
    }

    free(self->completions->entries);
    free(self->completions);
    object_cache_destroy(self->event_cache);

    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *core_start(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    uint64_t frequency;
    int ret;

    if (PyArg_ParseTuple(args, "KO", &frequency,
			 &core->python_complete_cb) == -1)
        return NULL;

    if (!PyCallable_Check(core->python_complete_cb)) {
        PyErr_Format(VortexCoreError, "Completion callback is not callable");
        return NULL;
    }

    Py_INCREF(core->python_complete_cb);

    ret = controller_timer_start(core_object_update, frequency,
				 core_process_work, 0, self);
    if (ret) {
	PyErr_Format(VortexCoreError, "Failed to start core threads: %s",
		     strerror(ret));
	return NULL;
    }

    Py_INCREF(self);
    Py_XINCREF(Py_None);
    return Py_None;
}

static PyObject *core_stop(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    int64_t thread_match;
    core_object_event_type_t type;

    /* Allow external threads to avoid deadlocks. */
    Py_BEGIN_ALLOW_THREADS;
    thread_match = controller_timer_stop();
    Py_END_ALLOW_THREADS;

    pthread_mutex_lock(&core->cmds.lock);
    if (!STAILQ_EMPTY(&core->cmds.list)) {
        core_command_t *cmd, *cmd_next;

        cmd = STAILQ_FIRST(&core->cmds.list);
        while (cmd) {
	    cmd_next = STAILQ_NEXT(cmd, entry);
	    STAILQ_REMOVE(&core->cmds.list, cmd, core_command, entry);
	    object_cache_free(cmd->command.args);
	    free(cmd);
	    cmd = cmd_next;
	}
    }
    pthread_mutex_unlock(&core->cmds.lock);

    pthread_mutex_lock(&core->submitted.lock);
    if (!STAILQ_EMPTY(&core->submitted.list)) {
        core_command_t *cmd, *cmd_next;

        cmd = STAILQ_FIRST(&core->submitted.list);
        while (cmd) {
	    cmd_next = STAILQ_NEXT(cmd, entry);
	    STAILQ_REMOVE(&core->submitted.list, cmd, core_command, entry);
	    object_cache_free(cmd->command.args);
	    free(cmd);
	    cmd = cmd_next;
	}
    }
    pthread_mutex_unlock(&core->submitted.lock);

    pthread_mutex_lock(&core->events.lock);
    if (!STAILQ_EMPTY(&core->events.list)) {
        core_event_t *event, *event_next;

        event = STAILQ_FIRST(&core->events.list);
	while (event) {
	    event_next = STAILQ_NEXT(event, entry);
	    STAILQ_REMOVE(&core->events.list, event, event, entry);
	    object_cache_free(event->data);
	    object_cache_free(event);
	    event = event_next;
	}
    }
    pthread_mutex_unlock(&core->events.lock);

    for (type = 0; type < OBJECT_EVENT_MAX; type++) {
	pthread_mutex_lock(&core->event_handlers[type].lock);
	if (!STAILQ_EMPTY(&core->event_handlers[type].list)) {
	    event_subscription_t *subscription, *next;

	    subscription = STAILQ_FIRST(&core->event_handlers[type].list);
	    while (subscription) {
		next = STAILQ_NEXT(subscription, entry);
		STAILQ_REMOVE(&core->event_handlers[type].list, subscription,
			      event_subscription, entry);
		free(subscription);
                subscription = next;
            }
        }
	pthread_mutex_unlock(&core->event_handlers[type].lock);
    }

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
	     "update thread frequency match: %ld", thread_match);
    Py_DECREF(core->python_complete_cb);
    Py_DECREF(self);
    Py_XINCREF(Py_None);
    return Py_None;
}

static core_object_id_t load_object(core_t *core, core_object_type_t klass,
				    const char *name, void *config) {
    core_object_t *obj;
    char object_path[PATH_MAX];

    if (klass == OBJECT_TYPE_NONE || klass >= OBJECT_TYPE_MAX) {
	core_log(LOG_LEVEL_ERROR, OBJECT_TYPE_NONE, "core",
		 "Invalid object klass %u", klass);
	return CORE_OBJECT_ID_INVALID;
    }

    if (!core->object_libs[klass]) {
	char *path, *dir;

	path = strdup(module_path);
	dir = dirname(path);
	snprintf(object_path, sizeof(object_path), "%s/objects/%s.so", dir,
		 ObjectTypeNames[klass]);
	free(path);
        core->object_libs[klass] = dlopen(object_path, RTLD_LAZY);
        if (!core->object_libs[klass]) {
            char *err = dlerror();
            core_log(LOG_LEVEL_ERROR, OBJECT_TYPE_NONE, "core", "dlopen: %s",
		     err);
            return CORE_OBJECT_ID_INVALID;
        }
    }

    if (!core->object_create[klass]) {
        core->object_create[klass] = dlsym(core->object_libs[klass],
                                           "object_create");
        if (!core->object_create[klass])
            return CORE_OBJECT_ID_INVALID;
    }

    /*
     * Check if an object with the same name exists in the
     * same klass.
     */
    LIST_FOREACH(obj, &core->objects[klass], entry) {
	if (!strncmp(obj->name, name, strlen(obj->name))) {
	    core_log(LOG_LEVEL_ERROR, OBJECT_TYPE_NONE, "core",
		     "object of klass %s and name %s already exists", klass, name);
	    return CORE_OBJECT_ID_INVALID;
	}
    }

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
             "creating object klass %s, name %s", ObjectTypeNames[klass], name);
    obj = core->object_create[klass](name, config);
    if (!obj)
	return CORE_OBJECT_ID_INVALID;

    obj->call_data = core_call_data;
    LIST_INSERT_HEAD(&core->objects[klass], obj, entry);
    return (core_object_id_t)obj;
}

static PyObject *core_create_object(PyObject *self, PyObject *args,
				    PyObject *kwargs) {
    char *kw[] = {"klass", "name", "options", NULL};
    int klass;
    const char *name;
    void *options = NULL;
    core_object_id_t object_id;
    PyObject *id;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "isk", kw, &klass, &name,
                                     &options))
        return NULL;

    object_id = load_object((core_t *)self, klass, name, options);
    if (object_id == CORE_OBJECT_ID_INVALID) {
        PyErr_Format(VortexCoreError, "Failed to create object %s of klass %s",
		     name, ObjectTypeNames[klass]);
        return NULL;
    }

    id = Py_BuildValue("k", object_id);
    return id;
}

static PyObject *vortex_core_register_virtual_object(PyObject *self,
                                                     PyObject *args) {
    core_t *core = (core_t *)self;
    core_object_type_t klass;
    core_object_t *obj;
    char *name = NULL;

    if (!PyArg_ParseTuple(args, "Is", &klass, &name))
	return NULL;

    /*
     * Check if an object with the same name exists in the
     * same klass.
     */
    LIST_FOREACH(obj, &core->objects[klass], entry) {
      if (!strncmp(obj->name, name, strlen(obj->name))) {
        core_log(LOG_LEVEL_ERROR, OBJECT_TYPE_NONE, "core",
                 "object of klass %s and name %s already exists", klass, name);
        return Py_BuildValue("k", CORE_OBJECT_ID_INVALID);
      }
    }

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
             "creating object klass %s, name %s", ObjectTypeNames[klass], name);
    obj = calloc(1, sizeof(core_object_t));
    if (!obj)
	return Py_BuildValue("k", CORE_OBJECT_ID_INVALID);

    obj->type = klass;
    obj->name = strdup(name);
    LIST_INSERT_HEAD(&core->objects[klass], obj, entry);
    return Py_BuildValue("k", (core_object_id_t)obj);
}

static PyObject *core_initialize_object(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    core_object_type_t type;

    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
	core_object_t *object;

	LIST_FOREACH(object, &core->objects[type], entry) {
	    if (!object->init)
		continue;

	    if (object->init(object))
		Py_RETURN_FALSE;
	}
    }

    Py_RETURN_TRUE;
}

static PyObject *core_exec_command(PyObject *self, PyObject *args,
				   PyObject *kwargs) {
    char *kw[] = {"command_id", "object_id", "subcommand_id", "args", NULL};
    uint64_t cmd_id = -1UL;
    uint16_t obj_cmd_id = 0;
    void *cmd_args = NULL;
    core_object_t *object;
    core_object_command_t *cmd;
    PyObject *rc;
    int ret = -1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "kkHk:exec_command", kw,
                                     &cmd_id, &object, &obj_cmd_id, &cmd_args))
        return NULL;

    cmd = calloc(1, sizeof(*cmd));
    if (!cmd) {
        PyErr_Format(VortexCoreError, "Could not allocate command structure");
        return NULL;
    }

    if (object->exec_command) {
	cmd->command_id = cmd_id;
	cmd->object_cmd_id = obj_cmd_id;
	cmd->args = cmd_args;

	/*
	 * Object commands are supposed to be non-blocking -
	 * they should accept/reject the command and handle
	 * it in the object's update() handlers.
	 * However, to avoid deadlocks with logging, release
	 * the Python GIL around the command execution.
	 */
	Py_BEGIN_ALLOW_THREADS;
	ret = object->exec_command(object, cmd);
	Py_END_ALLOW_THREADS;
    }

    rc = Py_BuildValue("i", ret);
    return rc;
}

static void core_object_update(uint64_t ticks, uint64_t runtime,
			       void *user_data) {
    core_t *self = (core_t *)user_data;
    core_object_type_t type;

    self->ticks = ticks;
    self->runtime = runtime;
    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
        core_object_t *object;

        if (LIST_EMPTY(&self->objects[type]))
            continue;

        LIST_FOREACH(object, &self->objects[type], entry) {
	    if (object->update)
		object->update(object, ticks, runtime);
	}
    }
}

static void core_process_work(void *arg) {
    core_t *core = (core_t *)arg;
    core_object_completion_data_t *comps;
    core_command_t *cmd, *cmd_next;
    core_event_t *event, *event_next;
    bool empty;

    /* First, process any submitted commands. */
    pthread_mutex_lock(&core->cmds.lock);
    empty = STAILQ_EMPTY(&core->cmds.list);
    pthread_mutex_unlock(&core->cmds.lock);
    if (empty)
	goto do_events;

    pthread_mutex_lock(&core->cmds.lock);
    cmd = STAILQ_FIRST(&core->cmds.list);
    pthread_mutex_unlock(&core->cmds.lock);
    while (cmd) {
	core_object_t *object;

	cmd_next = STAILQ_NEXT(cmd, entry);
        pthread_mutex_lock(&core->cmds.lock);
        STAILQ_REMOVE(&core->cmds.list, cmd, core_command, entry);
        pthread_mutex_unlock(&core->cmds.lock);

	object = core_id_to_object(cmd->target_id);
	core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
		 "issuing command for %s, id: %lu, cmd: %u",
		 object->name, cmd->command.command_id,
		 cmd->command.object_cmd_id);
	(void)object->exec_command(object, &cmd->command);
	pthread_mutex_lock(&core->submitted.lock);
	STAILQ_INSERT_TAIL(&core->submitted.list, cmd, entry);
	pthread_mutex_unlock(&core->submitted.lock);
	cmd = cmd_next;
    }

  do_events:
    pthread_mutex_lock(&core->events.lock);
    empty = STAILQ_EMPTY(&core->events.list);
    pthread_mutex_unlock(&core->events.lock);
    if (empty)
	goto do_completions;

    pthread_mutex_lock(&core->events.lock);
    event = STAILQ_FIRST(&core->events.list);
    pthread_mutex_unlock(&core->events.lock);
    while (event) {
	event_subscription_t *subscription;

	core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
		 "processing event = %s %s %lu",
		 ObjectTypeNames[event->object_type],
		 OBJECT_EVENT_NAMES[event->type], event->object_id);
	event_next = STAILQ_NEXT(event, entry);
        pthread_mutex_lock(&core->events.lock);
        STAILQ_REMOVE(&core->events.list, event, event, entry);
        pthread_mutex_unlock(&core->events.lock);

	pthread_mutex_lock(&core->event_handlers[event->type].lock);
	STAILQ_FOREACH(subscription, &core->event_handlers[event->type].list,
		       entry) {
	    core_object_t *object;

	    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
		     "sub type: %s, sub id: %lu, sub python: %u",
		     ObjectTypeNames[subscription->object_type],
		     subscription->object_id, subscription->is_python);
	    if (subscription->object_type != event->object_type)
		continue;

            if (subscription->object_id != CORE_OBJECT_ID_INVALID &&
                subscription->object_id != event->object_id)
		continue;

            object = core_id_to_object(event->object_id);
            if (!subscription->is_python)
		subscription->core.handler(subscription->core.object,
					   object->name, event->type,
					   event->data);
            else {
		PyGILState_STATE state = PyGILState_Ensure();
		PyObject *args =
		    Py_BuildValue("(isik)", object->type, object->name,
				  event->type, event->data);
		if (!args) {
		    PyErr_Print();
		    continue;
		}

		(void)PyObject_Call(subscription->python.handler, args, NULL);
		Py_DECREF(args);
		if (PyErr_Occurred())
		    PyErr_Print();
		PyGILState_Release(state);
	    }
	}
        pthread_mutex_unlock(&core->event_handlers[event->type].lock);

	if (event->should_free)
	    object_cache_free(event->data);
	else
	    Py_DECREF(event->data);
	object_cache_free(event);
	event = event_next;
    }

  do_completions:
    comps = core->completions;
    while (comps->tail != comps->head) {
	PyGILState_STATE state;
	PyObject *args;
	bool handled = false;

	core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
		 "completing cmd %lu", comps->entries[comps->tail].id);

	pthread_mutex_lock(&core->submitted.lock);
	empty = STAILQ_EMPTY(&core->submitted.list);
	pthread_mutex_unlock(&core->submitted.lock);
	if (empty)
	    goto python;

	pthread_mutex_lock(&core->submitted.lock);
	cmd = STAILQ_FIRST(&core->submitted.list);
	pthread_mutex_unlock(&core->submitted.lock);
	while (cmd) {
	    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
		     "submitted command %lu", cmd->command.command_id);
	    cmd_next = STAILQ_NEXT(cmd, entry);
	    if (cmd->command.command_id == comps->entries[comps->tail].id) {
		if (cmd->handler)
		    cmd->handler(comps->entries[comps->tail].id,
				 comps->entries[comps->tail].result,
				 cmd->source);
		pthread_mutex_lock(&core->submitted.lock);
		STAILQ_REMOVE(&core->submitted.list, cmd, core_command, entry);
		pthread_mutex_unlock(&core->submitted.lock);
		object_cache_free(cmd->command.args);
		free(cmd);
		handled = true;
		break;
	    }
	    cmd = cmd_next;
	}

	if (handled)
	    goto next;

      python:
        state = PyGILState_Ensure();
        args = Py_BuildValue("(ki)", comps->entries[comps->tail].id,
			     comps->entries[comps->tail].result);
	if (!args) {
	    PyErr_Print();
	    goto next;
	}

        (void)PyObject_Call(core->python_complete_cb, args, NULL);
	Py_DECREF(args);
	if (PyErr_Occurred())
	    PyErr_Print();
        PyGILState_Release(state);

      next:
	comps->tail = (comps->tail + 1) % comps->size;
    }
}

static void core_object_command_complete(uint64_t cmd_id, int result,
					 void *data) {
    core_t *core = (core_t *)data;
    core_object_completion_data_t *comps = core->completions;

    if (comps->head != comps->tail - 1 ||
	(comps->head == comps->size && comps->tail != 0)) {
	comps->entries[comps->head].id = cmd_id;
	comps->entries[comps->head].result = result;
	comps->head = (comps->head + 1) % comps->size;;
    } else {
	void *ptr  = realloc(comps->entries,
			     (comps->size * 2) * sizeof(*comps->entries));
	if (ptr) {
	    comps->entries = (struct __comp_entry *)ptr;
	    comps->size *= 2;
	} else {
	    core_log(LOG_LEVEL_ERROR, OBJECT_TYPE_NONE, "core",
		     "Resizing of completion entries failed! "
		     "Completions can be missed");
	}

    }
}

static core_object_t *core_object_find(const core_object_type_t type,
				       const char *name, void *data) {
    core_t *core = (core_t *)data;
    core_object_t *object;

    LIST_FOREACH(object, &core->objects[type], entry) {
	if (!strncmp(object->name, name, strlen(object->name)))
	    return object;
    }

    return NULL;
}


static int core_object_event_register(const core_object_type_t object_type,
				      const core_object_event_type_t event,
				      const char *name, core_object_t *object,
				      event_handler_t handler, void *data) {
    core_t *core = (core_t *)data;
    event_subscription_t *subscription;

    subscription = calloc(1, sizeof(*subscription));
    if(!subscription)
	return -1;

    subscription->object_type = object_type;
    if (name) {
	core_object_t *object = core_object_find(object_type, name, core);

	if (!object) {
	    free(subscription);
	    return -1;
	}

	subscription->object_id = core_object_to_id(object);
    } else {
	subscription->object_id = CORE_OBJECT_ID_INVALID;
    }

    subscription->is_python = false;
    subscription->core.handler = handler;
    subscription->core.object = object;
    pthread_mutex_lock(&core->event_handlers[event].lock);
    STAILQ_INSERT_TAIL(&core->event_handlers[event].list, subscription, entry);
    pthread_mutex_unlock(&core->event_handlers[event].lock);
    return 0;
}

static int core_object_event_unregister(const core_object_type_t object_type,
					const core_object_event_type_t event,
					const char *name, core_object_t *object,
					event_handler_t handler, void *data) {
    core_t *core = (core_t *)data;
    event_subscription_t *subscription;
    event_subscription_t *next;
    core_object_t *obj = core_object_find(object_type, name, core);

    pthread_mutex_lock(&core->event_handlers[event].lock);
    subscription = STAILQ_FIRST(&core->event_handlers[event].list);
    pthread_mutex_unlock(&core->event_handlers[event].lock);
    while (subscription != NULL) {
	next = STAILQ_NEXT(subscription, entry);
	if (subscription->object_type == object_type &&
	    (subscription->object_id == CORE_OBJECT_ID_INVALID ||
	     (object && subscription->object_id ==
	      core_object_to_id(obj)))) {
            pthread_mutex_lock(&core->event_handlers[event].lock);
            STAILQ_REMOVE(&core->event_handlers[event].list, subscription,
                          event_subscription, entry);
	    pthread_mutex_unlock(&core->event_handlers[event].lock);
            free(subscription);
	    return 0;
	}

	subscription = next;
    }

    return -1;
}

static int __core_object_event_submit(const core_object_event_type_t event_type,
				      const core_object_id_t id,
				      void *event_data, bool should_free,
				      void *user_data) {
    core_t *core = (core_t *)user_data;
    core_event_t *event;
    core_object_t *object = (core_object_t *)id;

    event = object_cache_alloc(core->event_cache);
    if (!event)
	return -1;

    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
	     "submitting event = %s, %s, %lu", OBJECT_EVENT_NAMES[event_type],
	     ObjectTypeNames[object->type], id);
    event->type = event_type;
    event->object_type = object->type;
    event->object_id = id;
    event->data = event_data;
    event->should_free = should_free;
    pthread_mutex_lock(&core->events.lock);
    STAILQ_INSERT_TAIL(&core->events.list, event, entry);
    pthread_mutex_unlock(&core->events.lock);
    return 0;
}
static int core_object_event_submit(const core_object_event_type_t event_type,
				    const core_object_id_t id,
				    void *event_data, void *user_data) {
    return __core_object_event_submit(event_type, id, event_data, true,
				      user_data);
}

static uint64_t core_object_command_submit(core_object_t *source,
					   core_object_id_t target_id,
					   uint16_t obj_cmd_id, void *args,
					   complete_cb_t cb,
					   void *user_data) {
    core_t *core = (core_t *)user_data;
    core_command_t *cmd;

    cmd = malloc(sizeof(*cmd));
    if (!cmd)
	return CMD_ID_MAKE_ERROR(-1);

    cmd->source = source;
    cmd->target_id = target_id;
    cmd->command.command_id = (uint64_t)cmd;
    cmd->command.object_cmd_id = obj_cmd_id;
    cmd->command.args = args;
    cmd->handler = cb;
    core_log(LOG_LEVEL_DEBUG, OBJECT_TYPE_NONE, "core",
	     "submitting command for %u, id: %lu, cmd: %u", target_id,
	     cmd->command.command_id, obj_cmd_id);
    pthread_mutex_lock(&core->cmds.lock);
    STAILQ_INSERT_TAIL(&core->cmds.list, cmd, entry);
    pthread_mutex_unlock(&core->cmds.lock);
    return (uint64_t)cmd;
}

static PyObject *core_python_event_register(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    event_subscription_t *subscription;
    core_object_type_t object_type;
    core_object_event_type_t type;
    PyObject *callback;
    char *name = NULL;

    if (!PyArg_ParseTuple(args, "iisO", &object_type, &type, &name, &callback))
	return NULL;

    Py_INCREF(callback);

    subscription = calloc(1, sizeof(*subscription));
    if (!subscription)
	Py_RETURN_FALSE;

    if (name) {
        core_object_t *object = core_object_find(object_type, name, core);

	if (!object) {
	    free(subscription);
	    Py_RETURN_FALSE;
	}

	subscription->object_id = core_object_to_id(object);
    } else {
	subscription->object_id = CORE_OBJECT_ID_INVALID;
    }

    subscription->object_type = object_type;
    subscription->is_python = true;
    subscription->python.handler = callback;
    pthread_mutex_lock(&core->event_handlers[type].lock);
    STAILQ_INSERT_TAIL(&core->event_handlers[type].list, subscription, entry);
    pthread_mutex_unlock(&core->event_handlers[type].lock);
    Py_RETURN_TRUE;
}

static PyObject *core_python_event_unregister(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    event_subscription_t *subscription;
    event_subscription_t *next;
    core_object_type_t object_type;
    core_object_event_type_t type;
    core_object_id_t object_id = CORE_OBJECT_ID_INVALID;
    char *name;

    if (PyArg_ParseTuple(args, "iis", &object_type, &type, &name))
	return NULL;

    if (name) {
	core_object_t *object = core_object_find(object_type, name, core);

	if (object)
	    object_id = core_object_to_id(object);
    }

    pthread_mutex_lock(&core->event_handlers[type].lock);
    subscription = STAILQ_FIRST(&core->event_handlers[type].list);
    pthread_mutex_unlock(&core->event_handlers[type].lock);

    while (subscription != NULL) {
	next = STAILQ_NEXT(subscription, entry);
	if (subscription->object_type == object_type &&
	    (subscription->object_id == CORE_OBJECT_ID_INVALID ||
	     subscription->object_id == object_id)) {
	    pthread_mutex_lock(&core->event_handlers[type].lock);
	    STAILQ_REMOVE(&core->event_handlers[type].list, subscription,
			  event_subscription, entry);
	    pthread_mutex_unlock(&core->event_handlers[type].lock);
	    if (subscription->is_python)
		Py_DECREF(subscription->python.handler);
	    free(subscription);
	    Py_RETURN_TRUE;
	}

	subscription = next;
    }

    Py_RETURN_FALSE;
}

static PyObject *core_python_event_submit(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    core_object_type_t object_type;
    core_object_id_t object_id;
    PyObject *data;

    if (!PyArg_ParseTuple(args, "ikO", &object_type, &object_id, &data))
	return NULL;

    Py_INCREF(data);
    if (__core_object_event_submit(object_type, object_id, (void *)data, false,
				   core))
	Py_RETURN_FALSE;

    Py_RETURN_TRUE;
}

static PyObject *core_get_ticks(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    PyObject *ticks = PyLong_FromUnsignedLongLong(core->ticks);
    return ticks;
}

static PyObject *core_get_runtime(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    PyObject *runtime = PyLong_FromUnsignedLongLong(core->runtime);
    return runtime;
}

static PyObject *core_get_status(PyObject *self, PyObject *args) {
    PyObject *object_list;
    PyObject *result_list = NULL;
    Py_ssize_t size;
    Py_ssize_t i;
    Py_ssize_t result_idx = 0;

    if (!PyArg_ParseTuple(args, "O", &object_list))
	return NULL;

    if (!PyList_Check(object_list)) {
	PyErr_SetString(VortexCoreError, "Argument should be a list of IDs");
	return NULL;
    }

    size = PyList_Size(object_list);
    result_list = PyList_New(size);
    if (!result_list)
	return NULL;

    for (i = 0; i < size; i++) {
	PyObject *item;
	PyObject *status = NULL;
	core_object_id_t id;
	core_object_t *object;
	void *state;

	item = PyList_GetItem(object_list, i);
	if (!PyLong_Check(item)) {
	    PyErr_SetString(VortexCoreError, "Expected object id");
	    goto fail;
	}

	state = NULL;
	id = PyLong_AsUnsignedLong(item);
	object = core_id_to_object(id);
	if (!object->get_state)
	    continue;

	switch (object->type) {
	case OBJECT_TYPE_AXIS:
	    state = calloc(1, sizeof(axis_status_t));
	    break;
        case OBJECT_TYPE_ENDSTOP:
            state = calloc(1, sizeof(endstop_status_t));
            break;
	case OBJECT_TYPE_HEATER:
	    state = calloc(1, sizeof(heater_status_t));
	    break;
	case OBJECT_TYPE_PROBE:
	    state = calloc(1, sizeof(probe_status_t));
	    break;
        case OBJECT_TYPE_STEPPER:
            state = calloc(1, sizeof(stepper_status_t));
            break;
        case OBJECT_TYPE_THERMISTOR:
            state = calloc(1, sizeof(thermistor_status_t));
	    break;
	default:
	    break;
	}

	if (!state) {
	    Py_INCREF(Py_None);
	    status = Py_None;
	} else {
	    object->get_state(object, state);
	    status = Py_BuildValue("k", state);
	}

	if (PyList_SetItem(result_list, result_idx, status)) {
            Py_XDECREF(status);
            goto fail;
	}

	result_idx++;
    }

    return result_list;

  fail:
    Py_DECREF(result_list);
    return NULL;
}

static PyObject *core_pause(PyObject *self, PyObject *args) {
    bool pause;

    if (!PyArg_ParseTuple(args, "p", &pause))
        return NULL;

    if (pause)
        controller_timer_pause();
    else
        controller_timer_resume();

    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject *core_reset(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    PyObject *object_list = NULL;

    if (!PyArg_ParseTuple(args, "|O", &object_list))
	return NULL;

    if (object_list && !Py_IsNone(object_list) && !PyList_Check(object_list)) {
	PyErr_Format(VortexCoreError, "Argument must be a list or None");
	return NULL;
    }

    controller_timer_pause();
    if (PyList_Check(object_list)) {
	Py_ssize_t size = PyList_Size(object_list);
	Py_ssize_t i;

	for (i = 0; i < size; i++) {
	    PyObject *item = PyList_GetItem(object_list, i);
	    core_object_id_t id;
	    core_object_t *object;

	    if (!PyLong_Check(item)) {
		PyErr_Format(VortexCoreError, "List items must be object IDs");
		return NULL;
	    }

	    id = PyLong_AsUnsignedLong(item);
	    object = core_id_to_object(id);
	    if (object->reset)
		object->reset(object);
	}
    } else {
        core_object_type_t type;

        for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
            core_object_t *object;

	    LIST_FOREACH(object, &core->objects[type], entry) {
		if (object->reset)
		    object->reset(object);
	    }
        }
    }
    controller_timer_resume();

    Py_RETURN_TRUE;
}

void core_log(core_log_level_t level, core_object_type_t type,
	      const char *name, const char *fmt, ...) {
    va_list args;
    PyGILState_STATE state;
    char msg_str[4096];
    int size;
    const char *methods[] = {
	[LOG_LEVEL_CRITICAL] = "critical",
	[LOG_LEVEL_ERROR] = "error",
	[LOG_LEVEL_WARNING] = "warning",
	[LOG_LEVEL_INFO] = "info",
	[LOG_LEVEL_DEBUG] = "debug",
    };

    if (level < logging.level)
	return;

    if (type != OBJECT_TYPE_NONE)
        size = snprintf(msg_str, sizeof(msg_str), "[%s:%s] ",
                        ObjectTypeNames[type], name);
    else
        size = snprintf(msg_str, sizeof(msg_str), "[%s] ", name);

    va_start(args, fmt);
    vsnprintf(msg_str + size, sizeof(msg_str) - size, fmt, args);
    va_end(args);

    state = PyGILState_Ensure();
    if (!PyObject_CallMethod(logging.module, methods[level], "(s)", msg_str))
	PyErr_Print();

    PyGILState_Release(state);
}

static PyMethodDef VortexCoreMethods[] = {
    {"init_objects", core_initialize_object, METH_NOARGS, "Initialize objects"},
    {"start", core_start, METH_VARARGS, "Run the emulator core thread"},
    {"stop", core_stop, METH_NOARGS, "Stop the emulator core thread"},
    {"create_object", (PyCFunction)core_create_object,
     METH_VARARGS | METH_KEYWORDS, "Create core object"},
    {"register_virtual_object", vortex_core_register_virtual_object,
     METH_VARARGS, "Register a virtual object_with the core."},
    {"exec_command", (PyCFunction)core_exec_command,
     METH_VARARGS | METH_KEYWORDS, "Execute command"},
    {"get_clock_ticks", core_get_ticks, METH_NOARGS, "Get current tick count"},
    {"get_runtime", core_get_runtime, METH_NOARGS, "Get controller runtime"},
    {"get_status", core_get_status, METH_VARARGS, "Get object(s) status"},
    {"event_register", core_python_event_register, METH_VARARGS,
     "Register to core object events"},
    {"event_unregister", core_python_event_unregister, METH_VARARGS,
     "Unregister from core object events"},
    {"event_submit", core_python_event_submit, METH_VARARGS,
     "Submit virtual object event"},
    {"pause", core_pause, METH_VARARGS, "Pause emulation"},
    {"reset", core_reset, METH_VARARGS, "Reset controller object state"},
    {NULL, NULL, 0, NULL}
};

static PyTypeObject Vortex_Core_Type = {
    .ob_base = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "Core",
    .tp_doc = PyDoc_STR("HW Core"),
    .tp_basicsize = sizeof(core_t),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = vortex_core_new,
    .tp_init = (initproc)vortex_core_init,
    .tp_dealloc = (destructor)vortex_core_dealloc,
    .tp_methods = VortexCoreMethods,
};


static int vortex_core_module_exec(PyObject *module) {
    core_object_type_t type;
    core_object_event_type_t event;
    PyObject *value_dict;
    PyObject *path;

    path = PyModule_GetFilenameObject(module);
    module_path = PyUnicode_AsUTF8(path);

    if (PyType_Ready(&Vortex_Core_Type) == -1) {
        Py_XDECREF(module);
        return -1;
    }

    if (PyModule_AddObject(module, "VortexCore",
			   (PyObject *)&Vortex_Core_Type) == -1) {
        Py_XDECREF(module);
        return -1;
    }

    VortexCoreError = PyErr_NewException("votex_core.VortexCoreError", NULL,
					 NULL);
    Py_XINCREF(VortexCoreError);
    if (PyModule_AddObject(module, "VortexCoreError", VortexCoreError) < 0)
        goto fail;

    value_dict = PyDict_New();
    if (!value_dict)
        goto fail;

    for (type = 0; type < OBJECT_TYPE_MAX; type++) {
        PyObject *key;
        PyObject *value;
        int ret;

        if (PyModule_AddIntConstant(module, ObjectTypeExportNames[type],
				    type) == -1)
            goto fail;

        key = PyLong_FromLong((long)type);
        if (!key)
            goto fail;

        value = PyUnicode_FromString(ObjectTypeNames[type]);
        if (!value) {
            Py_XDECREF(key);
            goto fail;
        }

        ret = PyDict_SetItem(value_dict, key, value);
        Py_XDECREF(key);
        Py_XDECREF(value);
        if (ret == -1)
            goto fail;
    }

    if (PyModule_AddObject(module, "OBJECT_TYPE_NAMES", value_dict) == -1) {
        Py_XDECREF(value_dict);
        goto fail;
    }

    value_dict = PyDict_New();
    if (!value_dict)
	goto fail;

    for (event = 0; event < OBJECT_EVENT_MAX; event++) {
	PyObject *key;
	PyObject *value;
	int ret;

	if (PyModule_AddIntConstant(module, OBJECT_EVENT_NAMES[event],
				    event) == -1)
	    goto fail;

	key = PyLong_FromLong((long)event);
	if (!key)
	    goto fail;

	value = PyUnicode_FromString(OBJECT_EVENT_NAMES[event]);
	if (!value) {
	    Py_XDECREF(key);
	    goto fail;
	}

	ret = PyDict_SetItem(value_dict, key, value);
        Py_XDECREF(key);
        Py_XDECREF(value);
        if (ret == -1)
            goto fail;
    }

    if (PyModule_AddObject(module, "OBJECT_EVENT_NAMES", value_dict) == -1) {
	Py_XDECREF(value_dict);
	goto fail;
    }

    logging.module = PyImport_ImportModule("logging");
    if (!logging.module)
	goto fail;

    return 0;

  fail:
    Py_XDECREF(VortexCoreError);
    Py_CLEAR(VortexCoreError);
    Py_XDECREF(module);
    return -1;
}

static PyModuleDef_Slot Vortex_Core_Slots[] = {
    {Py_mod_exec, vortex_core_module_exec},
    {0, NULL},
};

static struct PyModuleDef Vortex_Core_module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "_vortex_core",
    .m_doc = PyDoc_STR("HW controller core module"),
    .m_size = 0,
    .m_slots = Vortex_Core_Slots,
};

PyMODINIT_FUNC PyInit__vortex_core(void) {
    PyObject *module = PyModuleDef_Init(&Vortex_Core_module);
    return module;
}

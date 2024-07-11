#define PY_SSIZE_T_CLEAN
#include "objects/common_defs.h"
#include "thread_control.h"
#include <Python.h>
#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <sys/queue.h>
#include <structmember.h>

static PyObject *CoreError;
typedef core_object_t *(*object_create_func_t)(const char *, void *,
                                              complete_cb_t, void *);

typedef LIST_HEAD(CoreCmdList, core_object_command) CoreCmdList_t;
typedef LIST_HEAD(core_objectList, core_object) core_objectList_t;

#define MAX_COMPLETIONS 256

typedef struct {
    struct __comp_entry {
	const char *id;
	int result;
    } *entries;
    size_t size;
    size_t head;
    size_t tail;
} core_object_completion_data_t;

typedef struct {
    PyObject_HEAD void *object_libs[OBJECT_TYPE_MAX];
    object_create_func_t object_create[OBJECT_TYPE_MAX];
    core_objectList_t objects[OBJECT_TYPE_MAX];
    CoreCmdList_t cmds;
    core_object_completion_data_t *completions;
    uint64_t timestep;
    PyObject *comp_cb;
} core_t;

void core_object_update(uint64_t time_step, void *user_data);
void core_process_completions(void *user_data);
void core_object_command_complete(const char *command_id, int result,
                                  void *data);

PyObject *core_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
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

    return (PyObject *)core;
}

int core_init(core_t *self, PyObject *args, PyObject *kwargs) {
    core_object_type_t type;

    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
        LIST_INIT(&self->objects[type]);
    }

    self->timestep = 0;
    self->completions->head = 0;
    self->completions->tail = 0;

    return 0;
}

void core_dealloc(core_t *self) {
    core_object_type_t type;

    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
	core_object_t *object;
	core_object_t *object_next;

	if (LIST_EMPTY(&self->objects[type]))
	    continue;

	object = LIST_FIRST(&self->objects[type]);
	while (object) {
	    object_next = LIST_NEXT(object, entry);
	    object->destroy(object);
	    object = object_next;
	}

	dlclose(self->object_libs[type]);
    }

    Py_TYPE(self)->tp_free((PyObject *)self);
}

PyObject *core_start(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    uint64_t frequency;
    int ret;

    if (PyArg_ParseTuple(args, "KO", &frequency, &core->comp_cb) == -1)
        return NULL;

    if (!PyCallable_Check(core->comp_cb)) {
        PyErr_Format(CoreError, "Completion callback is not callable");
        return NULL;
    }
    Py_INCREF(core->comp_cb);

    ret = controller_timer_start(frequency, core_object_update,
				 core_process_completions, self);
    if (ret) {
    PyErr_Format(CoreError, "Failed to start timer thread: %s", strerror(ret));
    return NULL;
    }

    Py_INCREF(self);
    Py_XINCREF(Py_None);
    return Py_None;
}

PyObject *core_stop(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    controller_timer_stop();
    Py_DECREF(core->comp_cb);
    Py_DECREF(self);
    Py_XINCREF(Py_None);
    return Py_None;
}

static unsigned long load_object(core_t *core, int klass, const char *name,
                                 void *config) {
    core_object_t *new_obj;
    char *libname[] = {
        [OBJECT_TYPE_STEPPER] = "controllers/objects/stepper.so",
        [OBJECT_TYPE_DIGITAL_PIN] = "controllers/objects/dpin.so",
        [OBJECT_TYPE_PWM_PIN] = "controllers/objects/pwmpin.so",
        [OBJECT_TYPE_ENDSTOP] = "controllers/objects/endstop.so",
    };

    if (!core->object_libs[klass]) {
        core->object_libs[klass] = dlopen(libname[klass], RTLD_LAZY);
        if (!core->object_libs[klass]) {
            char *err = dlerror();
            printf("dlopen: %s\n", err);
            return -1UL;
        }
    }

    if (!core->object_create[klass]) {
        core->object_create[klass] = dlsym(core->object_libs[klass],
                                           "object_create");
        if (!core->object_create[klass])
            return -1UL;
    }

    new_obj = core->object_create[klass](name, config,
                                         core_object_command_complete, core);
    if (!new_obj)
        return -1UL;

    LIST_INSERT_HEAD(&core->objects[klass], new_obj, entry);
    return (unsigned long)new_obj;
}


PyObject *core_create_object(PyObject *self, PyObject *args, PyObject *kwargs) {
    char *kw[] = {"klass", "name", "options", NULL};
    int klass;
    char *name;
    void *options = NULL;
    unsigned long object_id;
    PyObject *id;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "isk", kw, &klass, &name,
                                     &options))
        return NULL;

    object_id = load_object((core_t *)self, klass, name, options);
    if (object_id == -1UL) {
        PyErr_Format(CoreError, "Failed to create object %s of klass %s", name,
                     ObjectTypeNames[klass]);
        return NULL;
    }

    id = Py_BuildValue("k", object_id);
    return id;
}

PyObject *core_exec_command(PyObject *self, PyObject *args, PyObject *kwargs) {
    char *kw[] = {"command_id", "object_id", "subcommand_id", "args", NULL};
    core_t *core = (core_t *)self;
    char *cmd_id = NULL;
    uint16_t obj_cmd_id = 0;
    void *cmd_args = NULL;
    core_object_t *object;
    core_object_command_t *cmd;
    PyObject *rc;
    int ret = -1;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "skHk:exec_command", kw,
                                     &cmd_id, &object, &obj_cmd_id, &cmd_args))
        return NULL;

    cmd = calloc(1, sizeof(*cmd));
    if (!cmd) {
        PyErr_Format(CoreError, "Could not allocate command structure");
        return NULL;
    }

    cmd->command_id = cmd_id;
    cmd->object_cmd_id = obj_cmd_id;
    cmd->args = cmd_args;
    LIST_INSERT_HEAD(&core->cmds, cmd, entry);

    ret = object->exec_command(object, cmd);
    rc = Py_BuildValue("i", ret);
    return rc;
}

void core_object_update(uint64_t time_step, void *user_data) {
    core_t *self = (core_t *)user_data;
    core_object_type_t type;

    self->timestep = time_step;
    for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
        core_object_t *object;

        if (LIST_EMPTY(&self->objects[type]))
            continue;

        LIST_FOREACH(object, &self->objects[type], entry) {
            object->update(object, time_step);
        }
    }
}

void core_process_completions(void *arg) {
    core_t *core = (core_t *)arg;
    core_object_completion_data_t *comps = core->completions;

    while (comps->tail != comps->head) {
        PyGILState_STATE state = PyGILState_Ensure();
        PyObject *args = Py_BuildValue("(si)", comps->entries[comps->tail].id,
                                       comps->entries[comps->tail].result);
	if (!args) {
	    PyErr_Print();
	    goto next;
	}

        (void)PyObject_Call(core->comp_cb, args, NULL);
	Py_DECREF(args);
	if (PyErr_Occurred())
	    PyErr_Print();
        PyGILState_Release(state);

      next:
	comps->tail = (comps->tail + 1) % comps->size;
    }

}

void core_object_command_complete(const char *cmd_id, int result, void *data) {
    core_t *core = (core_t *)data;
    core_object_completion_data_t *comps = core->completions;

    printf("comp: %zu\n", comps->head);
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
	    printf("Resizing of completion entries failed! Completions can be missed");
	}

    }
}

PyObject *core_get_timestep(PyObject *self, PyObject *args) {
    core_t *core = (core_t *)self;
    PyObject *timestep = PyLong_FromUnsignedLongLong(core->timestep);
    return timestep;
    }

static PyMethodDef CoreMethods[] = {
    {"start", core_start, METH_VARARGS, "Run the emulator core thread"},
    {"stop", core_stop, METH_NOARGS, "Stop the emulator core thread"},
    {"create_object", (PyCFunction)core_create_object,
     METH_VARARGS | METH_KEYWORDS, "Create core object"},
    {"exec_command", (PyCFunction)core_exec_command,
     METH_VARARGS | METH_KEYWORDS, "Execute command"},
    {"get_timestep", core_get_timestep, METH_NOARGS, "Get current timestep"},
    {NULL, NULL, 0, NULL}};

static PyTypeObject Core_Type = {
		.ob_base = PyVarObject_HEAD_INIT(NULL, 0).tp_name = "Core",
		.tp_doc = PyDoc_STR("HW Core"),
		.tp_basicsize = sizeof(core_t),
		.tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = core_new,
    .tp_init = (initproc)core_init,
    .tp_dealloc = (destructor)core_dealloc,
    .tp_methods = CoreMethods,
};

static struct PyModuleDef Core_module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "core",
    .m_doc = PyDoc_STR("HW controller core module"),
    .m_size = -1
};

PyMODINIT_FUNC PyInit_core(void) {
    PyObject *module = PyModule_Create(&Core_module);
    core_object_type_t type;
    PyObject *type_dict;

    if (PyType_Ready(&Core_Type) == -1) {
        Py_XDECREF(module);
        return NULL;
    }

    if (PyModule_AddObject(module, "Core", (PyObject *)&Core_Type) == -1) {
        Py_XDECREF(module);
        return NULL;
    }

    CoreError = PyErr_NewException("core.CoreError", NULL, NULL);
    Py_XINCREF(CoreError);
    if (PyModule_AddObject(module, "CoreError", CoreError) < 0)
        goto fail;

    type_dict = PyDict_New();
    if (!type_dict)
        goto fail;

    for (type = 0; type < OBJECT_TYPE_MAX; type++) {
        PyObject *key;
        PyObject *value;
        int ret;

        if (PyModule_AddIntConstant(module, ObjectTypeExportNames[type], type) ==
            -1)
            goto fail;

        key = PyLong_FromLong((long)type);
        if (!key)
            goto fail;

        value = PyUnicode_FromString(ObjectTypeNames[type]);
        if (!value) {
            Py_XDECREF(key);
            goto fail;
        }

        ret = PyDict_SetItem(type_dict, key, value);
        if (ret == -1) {
          Py_XDECREF(key);
          Py_XDECREF(value);
          goto fail;
        }
    }

    if (PyModule_AddObject(module, "OBJECT_TYPE_NAMES", type_dict) == -1) {
        Py_XDECREF(type_dict);
        goto fail;
    }

    return module;

  fail:
    Py_XDECREF(CoreError);
    Py_CLEAR(CoreError);
    Py_XDECREF(module);
    return NULL;
}

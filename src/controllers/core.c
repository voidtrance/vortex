#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stddef.h>
#include <stdint.h>
#include <structmember.h>
#include "timing.h"
#include <dlfcn.h>
#include "objects/common_defs.h"

static PyObject *CoreError;
typedef CoreObject_t *(*object_create_func_t)(const char *, void *);

typedef LIST_HEAD(CoreObjectList, core_object) CoreObjectList_t;

typedef struct {
	PyObject_HEAD
	void *object_libs[OBJECT_TYPE_MAX];
	object_create_func_t object_create[OBJECT_TYPE_MAX];
	CoreObjectList_t objects[OBJECT_TYPE_MAX];
	uint64_t timestep;
} Core_t;

int CoreObjectUpdate(uint64_t time_step, void *user_data);

PyObject *Core_new(PyTypeObject *type, PyObject *args, PyObject *kwargs)

{
	Core_t *core;

	core = (Core_t *)type->tp_alloc(type, 0);
	return (PyObject *)core;
}

int Core_init(Core_t *self, PyObject *args, PyObject *kwargs)
{
	CoreObjectType_t type;

	for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
		LIST_INIT(&self->objects[type]);
	}

	self->timestep = 0;

	return 0;
}

void Core_dealloc(Core_t *self)
{
	CoreObjectType_t type;

	for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
		CoreObject_t *object;
		CoreObject_t *object_next;

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


PyObject *Core_start(PyObject *self, PyObject *args)
{
	uint64_t frequency;
	int ret;

	if (PyArg_ParseTuple(args, "K", &frequency) == -1)
		return NULL;

	ret = controller_timer_start(frequency, CoreObjectUpdate, self);
	if (ret) {
		PyErr_Format(CoreError, "Failed to start timer thread: %s",
					 strerror(ret));
		return NULL;
	}

	Py_INCREF(self);
	Py_XINCREF(Py_None);
	return Py_None;
}

PyObject *Core_stop(PyObject *self, PyObject *args)
{
	controller_timer_stop();
	Py_DECREF(self);
	Py_XINCREF(Py_None);
	return Py_None;
}

static unsigned long load_object(Core_t *core, int klass, const char *name,
								 void *config)
{
	CoreObject_t *new_obj;
	char *libname[] = {
		[OBJECT_TYPE_STEPPER] = "controllers/objects/stepper.so",
		[OBJECT_TYPE_DIGITAL_PIN] = "controllers/objects/dpin.so",
		[OBJECT_TYPE_PWM_PIN] = "controllers/objects/pwmpin.so",
		[OBJECT_TYPE_ENDSTOP]  ="controllers/objects/endstop.so",
	};

	printf("type is %u\n", klass);
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

	new_obj = core->object_create[klass](name, config);
	if (!new_obj)
		return -1UL;

	LIST_INSERT_HEAD(&core->objects[klass], new_obj, entry);
	return (unsigned long)new_obj;
}

PyObject *Core_create_object(PyObject *self, PyObject *args, PyObject *kwargs)
{
	char *kw[] = {"klass", "name", "options", NULL};
	int klass;
	char *name;
	void *options = NULL;
	unsigned long object_id;
	PyObject *id;

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "isk", kw, &klass, &name,
									 &options))
		return NULL;

	object_id = load_object((Core_t *)self, klass, name, options);
	if (object_id == -1UL) {
		PyErr_Format(CoreError, "Failed to create object %s of klass %s", name,
					 ObjectTypeNames[klass]);
		return NULL;
	}

	id = Py_BuildValue("k", object_id);
	return id;
}

/*
PyObject *Core_get_commands(PyObject *self, PyObject *args)
{
	Core_t *core = (Core_t *)self;
	PyObject *cmds;
	CoreObject_t *object;
	uint16_t klass;

	if (PyArg_ParseTuple(args, "H", &klass) == -1)
		return NULL;

	if (klass > OBJECT_TYPE_MAX) {
		PyErr_Format(CoreError, "Invalid object class '%s'", klass);
		return NULL;
	}

	if (LIST_EMPTY(&core->objects[klass])) {
		cmds = PyList_New(0);
		return cmds;
	}

	object = LIST_FIRST(&core->objects[klass]);
	cmds = object->get_commands(object);
	if (cmds == NULL)
		PyErr_Format(CoreError, "Could not get commands for klass %u",
					 klass);
	return cmds;
}
*/
PyObject *Core_exec_command(PyObject *self, PyObject *args, PyObject *kwargs)
{
	Py_XINCREF(Py_None);
	return Py_None;
}

int CoreObjectUpdate(uint64_t time_step, void *user_data)
{
	Core_t *self = (Core_t *)user_data;
	CoreObjectType_t type;

	self->timestep = time_step;
	for (type = OBJECT_TYPE_NONE; type < OBJECT_TYPE_MAX; type++) {
		CoreObject_t *object;

		if (LIST_EMPTY(&self->objects[type]))
			continue;

		LIST_FOREACH(object, &self->objects[type], entry) {
			object->update(object, time_step);
		}
	}

	return 0;
}
PyObject *Core_get_timestep(PyObject *self, PyObject *args)
{
	Core_t *core = (Core_t *)self;
	PyObject *timestep = PyLong_FromUnsignedLongLong(core->timestep);
	return timestep;
}

static PyMethodDef CoreMethods[] = {
	{"start", Core_start, METH_VARARGS, "Run the emulator core thread"},
	{"stop", Core_stop, METH_NOARGS, "Stop the emulator core thread"},
	{"create_object", (PyCFunction)Core_create_object,
	 METH_VARARGS | METH_KEYWORDS, "Create core object"},
	//{"get_commands", Core_get_commands, METH_VARARGS,
	// "Get object class command set"},
	{"exec_command", (PyCFunction)Core_exec_command,
	 METH_VARARGS | METH_KEYWORDS, "Execute command"},
	{"get_timestep", Core_get_timestep, METH_NOARGS, "Get current timestep"},
	{NULL, NULL, 0, NULL}
};

static PyTypeObject Core_Type = {
	.ob_base = PyVarObject_HEAD_INIT(NULL, 0)
	.tp_name = "Core",
	.tp_doc = PyDoc_STR("HW Core"),
	.tp_basicsize = sizeof(Core_t),
	.tp_itemsize = 0,
	.tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_new = Core_new,
	.tp_init = (initproc)Core_init,
	.tp_dealloc = (destructor)Core_dealloc,
	.tp_methods = CoreMethods,
};

static struct PyModuleDef Core_module = {
	.m_base = PyModuleDef_HEAD_INIT,
	.m_name = "core",
	.m_doc = PyDoc_STR("HW controller core module"),
	.m_size = -1
};

PyMODINIT_FUNC PyInit_core(void)
{
	PyObject *module = PyModule_Create(&Core_module);
	CoreObjectType_t type;
	PyObject *type_dict;

	if (PyType_Ready(&Core_Type) == -1) {
		Py_XDECREF(module);
		return NULL;
	}

	if (PyModule_AddObject(module, "Core",
						   (PyObject *)&Core_Type) == -1) {
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

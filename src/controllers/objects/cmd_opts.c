#include "cmd_opts.h"

PyObject *CmdOption_new(PyTypeObject *type, PyObject *args, PyObject *kwargs) {
    CmdOption_t *self;

    self = (CmdOption_t *)type->tp_alloc(type, 0);
    if (self == NULL)
        return (PyObject *)self;

    Py_XINCREF(Py_None);
    self->type = Py_None;
    Py_XINCREF(Py_None);

    return (PyObject *)self;
}

int CmdOption_init(CmdOption_t *self, PyObject *args, PyObject *kwargs) {
    static char *kwlist[] = {"type", NULL};
    PyObject *type = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O", kwlist, &type))
        return -1;

    if (type)
        Py_XSETREF(self->type, Py_NewRef(type));

    return 0;
}

void CmdOption_dealloc(CmdOption_t *self) {
    Py_XDECREF(self->type);
    Py_TYPE(self)->tp_free((PyObject *)self);
}

PyObject *CmdOptionSet_new(PyTypeObject *type, PyObject *args,
						   PyObject *kwargs) {
    CmdOptionSet_t *self;

    self = (CmdOptionSet_t *)type->tp_alloc(type, 0);
    if (!self)
        return (PyObject *)self;

    self->__dict__ = PyObject_GenericGetDict((PyObject *)self, NULL);
    if (!self->__dict__) {
        Py_XDECREF((PyObject *)self);
        return NULL;
    }

    return (PyObject *)self;
}

int CmdOptionSet_init(CmdOptionSet_t *self, PyObject *args, PyObject *kwargs) {
    PyObject *value_list;
    char *key;
    PyObject *value;
    Py_ssize_t index;
    Py_ssize_t length;


    if (!kwargs)
        return 0;

    value_list = PyMapping_Items(kwargs);
    if (!value_list) {
        printf("getting items\n");
        return -1;
    }
    value_list = PySequence_Fast(value_list, "Invalid sequence object");
    if (!value_list) {
        printf("getting list\n");
        return -1;
    }

    length = PySequence_Fast_GET_SIZE(value_list);
    for (index = 0; index < length; index++) {
        PyObject *tuple = PySequence_Fast_GET_ITEM(value_list, index);
        if (!PyArg_ParseTuple(tuple, "sO", &key, &value)) {
            printf("parsing tuple\n");
            return -1;
        }

        printf("key = %s\n", key);
        if (PyObject_SetAttrString((PyObject *)self, key, value) == -1) {
            printf("setting attr\n");
            return -1;
        }
    }

    return 0;
}

void CmdOptionSet_dealloc(CmdOptionSet_t *self) {
    Py_TYPE(self)->tp_free((PyObject *)self);
}

PyMODINIT_FUNC PyInit_cmd_opts(void) {
    PyObject *module = PyModule_Create(&Cmd_Opts_module);
	PyObject *c_api;

    if (PyType_Ready(&CmdOption_Type) == -1) {
        Py_XDECREF(module);
        return NULL;
    }
    PyModule_AddObject(module, "CmdOption", (PyObject *)&CmdOption_Type);

    if (PyType_Ready(&CmdOptionSet_Type) == -1) {
        Py_XDECREF(module);
        return NULL;
    }
    PyModule_AddObject(module, "CmdOptionSet", (PyObject *)&CmdOptionSet_Type);

	c_api = PyCapsule_New((void *)Cmd_Opts_API,
						  "controllers.objects.cmd_opts._C_API", NULL);
	if (PyModule_AddObject(module, "_C_API", c_api) == -1) {
		Py_XDECREF(c_api);
		Py_DECREF(module);
		return NULL;
	}

    return module;
}

static PyObject *BuildCmdOptionSet(const object_command_option_t *options,
								   size_t n_options)
{
	PyObject *cmd_option_set;
	size_t i;

	cmd_option_set = PyType_GenericNew(&CmdOptionSet_Type, Py_None, Py_None);
	for (i = 0; i < n_options; i++) {
		const object_command_option_t *option = &options[i];
		PyObject *type;
		PyObject *cmd_opt;
		PyObject *args;

		printf("name: %s, type: %u\n", option->name, option->type);
		switch (option->type) {
		case CMD_OPTION_TYPE_INT:
			type = PyObject_CallObject((PyObject *)&PyLong_Type, NULL);
			break;
		case CMD_OPTION_TYPE_FLOAT:
			type = PyObject_CallObject((PyObject *)&PyFloat_Type, NULL);
			break;
		case CMD_OPTION_TYPE_STRING:
			type = PyObject_CallObject((PyObject *)&PyUnicode_Type, NULL);
			break;
		default:
			return NULL;
		}

		args = Py_BuildValue("(O,)", type);
		cmd_opt = PyObject_CallObject((PyObject *)&CmdOption_Type, args);
		PyObject_SetAttrString(cmd_option_set, option->name, cmd_opt);
	}

	return cmd_option_set;
}

PyObject *Cmd_Opts_build_commands(const object_command_spec_t *commands,
								  size_t n_commands)
{
	PyObject *cmd_set;
	size_t index;
	PyObject *cmd_tuple;
	PyObject *id;
	PyObject *name;
	PyObject *opts;

	cmd_set = PyList_New(0);
	if (!cmd_set)
		return NULL;

	for (index = 0; index < n_commands; index++) {
		const object_command_spec_t *cmd = &commands[index];

		cmd_tuple = NULL;
		id = NULL;
		name = NULL;
		opts = NULL;

		cmd_tuple = PyTuple_New(3);
		if (!cmd_tuple)
			goto fail;

		id = PyLong_FromLong(cmd->id);
		if (!id)
			goto fail;

		name = PyUnicode_FromString(cmd->name);
		if (!name)
			goto fail;

		printf("name: %s, n_options: %zu\n", cmd->name, cmd->n_options);
		opts = BuildCmdOptionSet(cmd->options, cmd->n_options);
		if (!opts)
			goto fail;

		PyTuple_SetItem(cmd_tuple, 0, id);
		PyTuple_SetItem(cmd_tuple, 1, name);
		PyTuple_SetItem(cmd_tuple, 2, opts);

		if (PyList_Append(cmd_set, cmd_tuple))
			goto fail;
	}

	return cmd_set;

fail:
	Py_XDECREF(name);
	Py_XDECREF(id);
	Py_XDECREF(cmd_tuple);
	Py_XDECREF(cmd_set);
	return NULL;
}

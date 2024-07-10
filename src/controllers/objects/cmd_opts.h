#define PY_SSIZE_T_CLEAN
#include <Python.h>
#define CMD_OPTS_MODULE
#include "cmd_opts_module.h"
#include <stddef.h>
#include <structmember.h>
#include "common_defs.h"

typedef struct {
	PyObject_HEAD
	PyObject *type;
} CmdOption_t;

PyObject *CmdOption_new(PyTypeObject *type, PyObject *args, PyObject *kwargs);
int CmdOption_init(CmdOption_t *self, PyObject *args, PyObject *kwargs);
void CmdOption_dealloc(CmdOption_t *self);

static PyMemberDef CmdOption_members[] = {
    {"type", T_OBJECT_EX, offsetof(CmdOption_t, type), 0, "Option type"},
    {NULL}
};

static PyTypeObject CmdOption_Type = {
    .ob_base = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "CmdOption",
    .tp_doc = PyDoc_STR("Emulator object option"),
    .tp_basicsize = sizeof(CmdOption_t),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = CmdOption_new,
    .tp_init = (initproc) CmdOption_init,
    .tp_dealloc = (destructor) CmdOption_dealloc,
    .tp_members = CmdOption_members,
};

typedef struct {
	PyObject_HEAD
	PyObject *__dict__;
} CmdOptionSet_t;

PyObject *CmdOptionSet_new(PyTypeObject *type, PyObject *args, PyObject *kwargs);
int CmdOptionSet_init(CmdOptionSet_t *self, PyObject *args, PyObject *kwargs);
void CmdOptionSet_dealloc(CmdOptionSet_t *self);

static PyMemberDef CmdOptionSet_members[] = {
	{ "__dict__", T_OBJECT, offsetof(CmdOptionSet_t, __dict__), READONLY, 0 },
};

static PyTypeObject CmdOptionSet_Type = {
    .ob_base = PyVarObject_HEAD_INIT(NULL, 0)
    .tp_name = "CmdOptionSet",
    .tp_doc = PyDoc_STR("Emulator object option set"),
    .tp_basicsize = sizeof(CmdOptionSet_t),
    .tp_itemsize = 0,
    .tp_flags = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    .tp_new = CmdOptionSet_new,
    .tp_init = (initproc) CmdOptionSet_init,
    .tp_dealloc = (destructor) CmdOptionSet_dealloc,
	.tp_setattro = PyObject_GenericSetAttr,
    .tp_dictoffset = offsetof(CmdOptionSet_t, __dict__),
	.tp_members = CmdOptionSet_members,
};

PyObject *Cmd_Opts_build_commands(const object_command_spec_t *commands,
								  size_t n_commands);

static void *Cmd_Opts_API[Cmd_Opts_API_pointers] = {
	(void *)Cmd_Opts_build_commands,
};

static struct PyModuleDef Cmd_Opts_module = {
    PyModuleDef_HEAD_INIT,
    "cmd_opts",
    NULL,
    -1
};

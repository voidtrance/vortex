#ifndef CMD_OPTS_MODULE_H
#define CMD_OPTS_MODULE_H
#include "common_defs.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Header file for cmd_opts_module */

/* C API functions */
#define Cmd_Opts_build_commands_NUM 0
#define Cmd_Opts_build_commands_RETURN PyObject *
#define Cmd_Opts_build_commands_PROTO \
	(const object_command_spec_t *command, size_t n_commands)

/* Total number of C API pointers */
#define Cmd_Opts_API_pointers 1


#ifdef CMD_OPTS_MODULE
/* This section is used when compiling cmd_opts.c */

static Cmd_Opts_build_commands_RETURN Cmd_Opts_build_commands
	Cmd_Opts_build_commands_PROTO;

#else
/* This section is used in modules that use cmd_opts's API */

static void **Cmd_Opts_API;

#define Cmd_Opts_build_commands \
 (*(Cmd_Opts_build_commands_RETURN (*)Cmd_Opts_build_commands_PROTO) \
  Cmd_Opts_API[Cmd_Opts_build_commands_NUM])

/* Return -1 on error, 0 on success.
 * PyCapsule_Import will set an exception if there's an error.
 */
static int import_cmd_opts(void)
{
    Cmd_Opts_API = (void **)PyCapsule_Import("controllers.objects.cmd_opts._C_API", 0);
	if (Cmd_Opts_API == NULL)
		PyErr_PrintEx(0);
    return (Cmd_Opts_API != NULL) ? 0 : -1;
}

#endif

#ifdef __cplusplus
}
#endif

#endif /* !defined(CMD_OPTS_MODULE_H) */

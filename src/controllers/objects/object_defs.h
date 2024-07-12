#ifndef __OBJECT_DEFS_H__
#define __OBJECT_DEFS_H__

#include <stdint.h>
#include <sys/queue.h>
#include <stdlib.h>

#define _stringify(x) #x
#define stringify(x) _stringify(x)

typedef enum {
    OBJECT_TYPE_NONE,
    OBJECT_TYPE_STEPPER,
    OBJECT_TYPE_DIGITAL_PIN,
    OBJECT_TYPE_PWM_PIN,
    OBJECT_TYPE_ENDSTOP,
    OBJECT_TYPE_FAN,
    OBJECT_TYPE_HEATER,
    OBJECT_TYPE_THERMISTOR,
    OBJECT_TYPE_MAX
} core_object_type_t;

static const char *const ObjectTypeExportNames[] = {
    [OBJECT_TYPE_NONE] = stringify(OBJECT_TYPE_NONE),
    [OBJECT_TYPE_STEPPER] = stringify(OBJECT_TYPE_STEPPER),
    [OBJECT_TYPE_DIGITAL_PIN] = stringify(OBJECT_TYPE_DIGITAL_PIN),
    [OBJECT_TYPE_PWM_PIN] = stringify(OBJECT_TYPE_PWM_PIN),
    [OBJECT_TYPE_ENDSTOP] = stringify(OBJECT_TYPE_ENDSTOP),
    [OBJECT_TYPE_FAN] = stringify(OBJECT_TYPE_FAN),
    [OBJECT_TYPE_HEATER] = stringify(OBJECT_TYPE_HEATER),
    [OBJECT_TYPE_THERMISTOR] = stringify(OBJECT_TYPE_THERMISTOR),
};

static const char *const ObjectTypeNames[] = {
    [OBJECT_TYPE_NONE] = "none",
    [OBJECT_TYPE_STEPPER] = "stepper",
    [OBJECT_TYPE_DIGITAL_PIN] = "digital_pin",
    [OBJECT_TYPE_PWM_PIN] = "pwm_pin",
    [OBJECT_TYPE_ENDSTOP] = "endstop",
    [OBJECT_TYPE_FAN] = "fan",
    [OBJECT_TYPE_HEATER] = "heater",
    [OBJECT_TYPE_THERMISTOR] = "thermistor",
};

/*
 * Common command structure. This structure will be
 * filled out by the controller core when a object
 * command is submitted and will be passed to the
 * object.
 */
typedef struct core_object_command {
    LIST_ENTRY(core_object_command) entry;
    const char *command_id;
    uint16_t object_cmd_id;
    void *args;
} core_object_command_t;

typedef enum {
    CMD_OPTION_TYPE_NONE,
    CMD_OPTION_TYPE_INT,
    CMD_OPTION_TYPE_FLOAT,
    CMD_OPTION_TYPE_STRING,
    CMD_OPTION_TYPE_MAX,
} command_option_type_t;

typedef struct {
    char name[64];
    command_option_type_t type;
} object_command_option_t;

typedef struct {
    uint16_t id;
    char name[64];
    const object_command_option_t *options;
    size_t n_options;
} object_command_spec_t;

/*
 * Common object structure. Objects should wrap
 * this structure in their own object-specific
 * structure.
 * If wrapped, this structure should be the
 * first member of the object-specific
 * structure.
 */
typedef struct core_object core_object_t;
struct core_object {
    core_object_type_t type;
    const char *name;
    LIST_ENTRY(core_object) entry;
    void (*update)(core_object_t *object, uint64_t timestep);
    int (*exec_command)(core_object_t *object, core_object_command_t *cmd);
    void *(*get_state)(core_object_t *object);
    void (*destroy)(core_object_t *object);
};

#endif

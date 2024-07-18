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
    OBJECT_TYPE_PROBE,
    OBJECT_TYPE_AXIS,
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
    [OBJECT_TYPE_PROBE] = stringify(OBJECT_TYPE_PROBE),
    [OBJECT_TYPE_AXIS] = stringify(OBJECT_TYPE_AXIS),
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
    [OBJECT_TYPE_PROBE] = "probe",
    [OBJECT_TYPE_AXIS] = "axis",
};

typedef unsigned long core_object_id_t;
#define CORE_OBJECT_ID_INVALID (-1UL)

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

typedef struct core_object core_object_t;

#endif

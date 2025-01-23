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
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <math.h>
#include <time.h>
#include <logging.h>
#include <common_defs.h>
#include <events.h>
#include "axis.h"
#include "endstop.h"
#include "object_defs.h"
#include "stepper.h"
#include <utils.h>
#include <cache.h>
#include <random.h>

#define AXIS_NO_LENGTH (-1.0)

typedef struct {
    const char *name;
    core_object_t *obj;
    uint32_t steps_per_mm;
    uint32_t microsteps;
    int64_t initial_step;
    int64_t steps;
    bool move_complete;
    bool enabled;
} axis_motor_t;

typedef struct {
    float length;
    const char type;
    const char **steppers;
    const char endstop[64];
} axis_config_params_t;

typedef struct {
    core_object_t object;
    axis_type_t type;
    axis_motor_t *motors;
    size_t n_motors;
    const char *endstop_name;
    core_object_t *endstop;
    bool homed;
    bool endstop_is_max;
    float length;
    double start_position;
    double position;
} axis_t;

typedef int (*command_func_t)(core_object_t *object, void *args);

static object_cache_t *axis_event_cache = NULL;
static stepper_status_t stepper_status;

static void axis_event_handler(core_object_t *object, const char *name,
                               const core_object_event_type_t event,
                               void *data);

static void axis_reset(core_object_t *object) {
    axis_t *axis = (axis_t *)object;

    axis->homed = false;

    if (axis->length == AXIS_NO_LENGTH) {
        axis->homed = true;
        axis->start_position = 0.0;
    } else {
        kinematics_type_t kin = kinematics_type_get();
        double start = random_double_limit(0, axis->length);
        double r;
        uint32_t spmm;

        switch (kin) {
        case KINEMATICS_COREXY:
            if (axis->type != AXIS_TYPE_Y)
                spmm = axis->motors[0].steps_per_mm;
            else
                spmm = axis->motors[1].steps_per_mm;
            break;
        case KINEMATICS_COREXZ:
            if (axis->type != AXIS_TYPE_Z)
                spmm = axis->motors[0].steps_per_mm;
            else
                spmm = axis->motors[1].steps_per_mm;
            break;
        default:
            spmm = axis->motors[0].steps_per_mm;
        }

        /* Axis position has to be a multiple of the single step distance. */
        r = remainder(start, (double)(1.0 / spmm));
        axis->start_position = start - r;
    }

    axis->position = axis->start_position;
}

static int axis_init(core_object_t *object) {
    axis_t *axis = (axis_t *)object;
    size_t i;

    for (i = 0; i < axis->n_motors; i++) {
        axis->motors[i].obj = CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_STEPPER,
                                                 axis->motors[i].name);
        if (!axis->motors[i].obj)
            return -ENODEV;

        axis->motors[i].obj->get_state(axis->motors[i].obj, &stepper_status);
        axis->motors[i].move_complete = true;
        axis->motors[i].steps_per_mm = stepper_status.steps_per_mm;
        axis->motors[i].initial_step = stepper_status.steps;
        axis->motors[i].microsteps = stepper_status.microsteps;
    }

    if (axis->endstop_name) {
        endstop_status_t status;
        axis->endstop =
            CORE_LOOKUP_OBJECT(axis, OBJECT_TYPE_ENDSTOP, axis->endstop_name);
        if (!axis->endstop)
            return -ENODEV;

        axis->endstop->get_state(axis->endstop, &status);
        if (!strncmp(status.type, "max", 3))
            axis->endstop_is_max = true;
        else
            axis->endstop_is_max = false;
    }

    CORE_EVENT_REGISTER(axis, OBJECT_TYPE_ENDSTOP, OBJECT_EVENT_ENDSTOP_TRIGGER,
                        axis->endstop_name, axis_event_handler);
    axis_reset(object);
    return 0;
}

static void axis_event_handler(core_object_t *object, const char *name,
                               const core_object_event_type_t event,
                               void *data) {
    endstop_trigger_event_data_t *event_data =
        (endstop_trigger_event_data_t *)data;
    axis_t *axis = (axis_t *)object;

    if (!axis->homed && event == OBJECT_EVENT_ENDSTOP_TRIGGER &&
        event_data->triggered)
        axis->homed = true;
}

#define step_distance(motor)                                          \
    ((double)(motor.steps - motor.initial_step) / motor.steps_per_mm)

static void axis_update(core_object_t *object, uint64_t ticks,
                        uint64_t runtime) {
    axis_t *axis = (axis_t *)object;
    coordinates_t coords = { 0 };
    coordinates_t distance = { 0 };
    kinematics_type_t kinematics = kinematics_type_get();
    double average_distance = 0.0;
    size_t i;

    /* TODO: need to figure out how to limit the stepper
     * from going past the axis length. Some possibilities:
     *    - have the stepper query the endstop trigger status.
     *    - have the axis somehow set limits on the number of
     *      steps the stepper can perform.
     */
    for (i = 0; i < axis->n_motors; i++) {
        axis->motors[i].obj->get_state(axis->motors[i].obj, &stepper_status);
        axis->motors[i].steps = stepper_status.steps;
    }

    if (kinematics == KINEMATICS_COREXY &&
        (axis->type == AXIS_TYPE_X || axis->type == AXIS_TYPE_Y)) {
        coords.x = step_distance(axis->motors[0]);
        coords.y = step_distance(axis->motors[1]);
    } else if (kinematics == KINEMATICS_COREXZ &&
               (axis->type == AXIS_TYPE_X || axis->type == AXIS_TYPE_Z)) {
        coords.x = step_distance(axis->motors[0]);
        coords.z = step_distance(axis->motors[1]);
    } else {
        /*
         * Average out the axis position based on the position of
         * motor.
         */
        for (i = 0; i < axis->n_motors; i++)
            average_distance += step_distance(axis->motors[i]);

        coords.x = average_distance / axis->n_motors;
    }

    compute_axis_movement(&coords, &distance);

    switch (kinematics) {
    case KINEMATICS_COREXY:
        if (axis->type != AXIS_TYPE_Y)
            axis->position = axis->start_position + distance.x;
        else
            axis->position = axis->start_position + distance.y;
        break;
    case KINEMATICS_COREXZ:
        if (axis->type != AXIS_TYPE_Z)
            axis->position = axis->start_position + distance.x;
        else
            axis->position = axis->start_position + distance.y;
        break;
    default:
        axis->position = axis->start_position + distance.x;
        break;
    }

    log_debug(axis, "position: %.15f, homed: %u", axis->position, axis->homed);
}

static void axis_status(core_object_t *object, void *status) {
    axis_t *axis = (axis_t *)object;
    axis_status_t *s = (axis_status_t *)status;
    size_t i;

    s->homed = axis->homed;
    s->length = axis->length;
    s->type = axis->type;
    s->position = axis->position;
    if (axis->endstop_name)
        strncpy(s->endstop, axis->endstop_name, sizeof(s->endstop));
    memset(s->motors, 0, sizeof(s->motors));
    for (i = 0; i < axis->n_motors; i++) {
        strncpy(s->motors[i], axis->motors[i].name, ARRAY_SIZE(s->motors[i]));
    }
}

static void axis_destroy(core_object_t *object) {
    axis_t *axis = (axis_t *)object;
    size_t i;

    core_object_destroy(object);
    object_cache_destroy(axis_event_cache);
    free((char *)axis->endstop_name);
    for (i = 0; i < axis->n_motors; i++)
        free((char *)axis->motors[i].name);
    free(axis->motors);
    free(axis);
}

axis_t *object_create(const char *name, void *config_ptr) {
    axis_t *axis;
    axis_config_params_t *config = (axis_config_params_t *)config_ptr;
    const char *stepper;
    kinematics_type_t kinematics = kinematics_type_get();
    size_t i = 0;

    if (object_cache_create(&axis_event_cache,
                            sizeof(axis_homed_event_data_t)))
        return NULL;

    axis = calloc(1, sizeof(*axis));
    if (!axis) {
        object_cache_destroy(axis_event_cache);
        return NULL;
    }

    axis->object.type = OBJECT_TYPE_AXIS;
    axis->object.name = strdup(name);
    axis->object.init = axis_init;
    axis->object.update = axis_update;
    axis->object.reset = axis_reset;
    axis->object.get_state = axis_status;
    axis->object.destroy = axis_destroy;
    if (config->endstop[0] != '\0')
        axis->endstop_name = strdup(config->endstop);

    axis->type = kinematics_axis_type_from_char(config->type);

    /* First, we have to find out how many motors are
     * defined.
     */
    stepper = *config->steppers;
    while (stepper) {
        stepper = config->steppers[++i];
    }

    axis->motors = calloc(i, sizeof(*axis->motors));
    if (!axis->motors) {
        object_cache_destroy(axis_event_cache);
        free((char *)axis->endstop_name);
        free(axis);
        return NULL;
    }

    axis->n_motors = i;
    if (((kinematics == KINEMATICS_COREXY &&
          (axis->type == AXIS_TYPE_X || axis->type == AXIS_TYPE_Y))
         || (kinematics == KINEMATICS_COREXZ &&
             (axis->type == AXIS_TYPE_X || axis->type == AXIS_TYPE_Z))) &&
        axis->n_motors != 2) {
        log_error(axis, "Kinematics model requires 2 motors for axis");
        free(axis->motors);
        object_cache_destroy(axis_event_cache);
        free((char *)axis->endstop_name);
        free(axis);
        return NULL;
    }

    for (i = 0; i < axis->n_motors; i++)
        axis->motors[i].name = strdup(config->steppers[i]);

    axis->length = config->length;

    return axis;
}

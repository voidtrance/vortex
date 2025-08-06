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
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <math.h>
#include <time.h>
#include <logging.h>
#include <common_defs.h>
#include <events.h>
#include <kinematics.h>
#include "axis.h"
#include "endstop.h"
#include "object_defs.h"
#include "stepper.h"
#include <utils.h>
#include <cache.h>
#include <random.h>

#define AXIS_NO_LENGTH (0.0)

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
    const char endstop[ENDSTOP_NAME_SIZE];
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
    float min;
    float max;
    float length;
    double start_position;
    double position;
    stepper_status_t stepper_status;
} axis_t;

typedef int (*command_func_t)(core_object_t *object, void *args);

static object_cache_t *axis_event_cache = NULL;
static coordinates_t randomized_motor_position = { 0 };

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
        double start = 0;
        double r;
        uint32_t spmm;

        switch (kin) {
        case KINEMATICS_COREXY:
            start = random_double_limit(axis->min, axis->max);
            if (axis->type != AXIS_TYPE_Y)
                spmm = axis->motors[0].steps_per_mm;
            else
                spmm = axis->motors[1].steps_per_mm;
            break;
        case KINEMATICS_COREXZ:
            start = random_double_limit(axis->min, axis->max);
            if (axis->type != AXIS_TYPE_Z)
                spmm = axis->motors[0].steps_per_mm;
            else
                spmm = axis->motors[1].steps_per_mm;
            break;
        case KINEMATICS_DELTA:
            if (randomized_motor_position.a == 0.0 &&
                randomized_motor_position.b == 0.0 &&
                randomized_motor_position.c == 0.0) {
                delta_kinematics_config_t *delta_config =
                    (delta_kinematics_config_t *)kinematics_get_config();
                float max_x = delta_config->radius * sin(DEG2RAD(45));
                float max_y = delta_config->radius * cos(DEG2RAD(45));
                coordinates_t position = { 0 };

                log_debug(axis, "Axis X min/max: %f/%f", -max_x, max_x);
                log_debug(axis, "Axis Y min/max: %f/%f", -max_y, max_y);
                position.x = random_float_limit(-max_x, max_x);
                log_debug(axis, "Position X: %f", position.x);
                position.y = random_float_limit(-max_y, max_y);
                log_debug(axis, "Position Y: %f", position.y);
                position.z = random_float_limit(0.0, delta_config->z_length);
                log_debug(axis, "Position Z: %f", position.z);

                kinematics_get_motor_movement(&position,
                                              &randomized_motor_position);
            }

            switch (axis->type) {
            case AXIS_TYPE_A:
                start = randomized_motor_position.a;
                break;
            case AXIS_TYPE_B:
                start = randomized_motor_position.b;
                break;
            case AXIS_TYPE_C:
                start = randomized_motor_position.c;
                break;
            default:
                start = 0.0; // Should not happen
            }

            spmm = axis->motors[0].steps_per_mm;
            break;
        default:
            start = random_double_limit(axis->min, axis->max);
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
        axis->motors[i].obj = CORE_LOOKUP_OBJECT(axis, OBJECT_KLASS_STEPPER,
                                                 axis->motors[i].name);
        if (!axis->motors[i].obj) {
            log_error(axis, "Failed to find stepper motor %s",
                      axis->motors[i].name);
            return -ENODEV;
        }

        axis->motors[i].obj->get_state(axis->motors[i].obj,
                                       &axis->stepper_status);
        axis->motors[i].move_complete = true;
        axis->motors[i].steps_per_mm = axis->stepper_status.steps_per_mm;
        axis->motors[i].initial_step = axis->stepper_status.steps;
        axis->motors[i].microsteps = axis->stepper_status.microsteps;
    }

    if (axis->endstop_name) {
        endstop_status_t status;
        axis->endstop =
            CORE_LOOKUP_OBJECT(axis, OBJECT_KLASS_ENDSTOP, axis->endstop_name);
        if (!axis->endstop) {
            log_error(axis, "Failed to find endstop %s", axis->endstop_name);
            return -ENODEV;
        }

        axis->endstop->get_state(axis->endstop, &status);
        if (!strncmp(status.type, "max", 3))
            axis->endstop_is_max = true;
        else
            axis->endstop_is_max = false;
    }

    CORE_EVENT_REGISTER(axis, OBJECT_KLASS_ENDSTOP,
                        OBJECT_EVENT_ENDSTOP_TRIGGER, axis->endstop_name,
                        axis_event_handler);
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

static inline void set_axis_distance(axis_t *axis, coordinates_t *coords,
                                     double distance) {
    switch (axis->type) {
    case AXIS_TYPE_X:
        coords->x = distance;
        break;
    case AXIS_TYPE_Y:
        coords->y = distance;
        break;
    case AXIS_TYPE_Z:
        coords->z = distance;
        break;
    case AXIS_TYPE_E:
        coords->e = distance;
        break;
    case AXIS_TYPE_A:
        coords->a = distance;
        break;
    case AXIS_TYPE_B:
        coords->b = distance;
        break;
    case AXIS_TYPE_C:
        coords->c = distance;
        break;
    default:
        break;
    }
}

static inline double get_axis_distance(axis_t *axis, coordinates_t *coords) {
    double distance;

    switch (axis->type) {
    case AXIS_TYPE_X:
        distance = coords->x;
        break;
    case AXIS_TYPE_Y:
        distance = coords->y;
        break;
    case AXIS_TYPE_Z:
        distance = coords->z;
        break;
    case AXIS_TYPE_E:
        distance = coords->e;
        break;
    case AXIS_TYPE_A:
        distance = coords->a;
        break;
    case AXIS_TYPE_B:
        distance = coords->b;
        break;
    case AXIS_TYPE_C:
        distance = coords->c;
        break;
    default:
        distance = 0.0;
    }

    return axis->start_position + distance;
}

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
        axis->motors[i].obj->get_state(axis->motors[i].obj,
                                       &axis->stepper_status);
        axis->motors[i].steps = axis->stepper_status.steps;
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

        set_axis_distance(axis, &coords, average_distance / axis->n_motors);
    }

    kinematics_get_axis_movement(&coords, &distance);
    axis->position = get_axis_distance(axis, &distance);
    log_debug(axis, "position: %.15f, homed: %u", axis->position, axis->homed);
}

static void axis_status(core_object_t *object, void *status) {
    axis_t *axis = (axis_t *)object;
    axis_status_t *s = (axis_status_t *)status;
    size_t i;

    s->homed = axis->homed;
    s->min = axis->min;
    s->max = axis->max;
    s->type = axis->type;
    s->position = axis->position;
    if (axis->endstop_name)
        strncpy(s->endstop, axis->endstop_name, sizeof(s->endstop) - 1);
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

    axis->object.klass = OBJECT_KLASS_AXIS;
    axis->object.name = strdup(name);
    axis->object.init = axis_init;
    axis->object.update = axis_update;
    axis->object.update_frequency = 5000; /* 5kHz */
    axis->object.reset = axis_reset;
    axis->object.get_state = axis_status;
    axis->object.destroy = axis_destroy;
    if (config->endstop[0] != '\0')
        axis->endstop_name = strdup(config->endstop);

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

    axis->type = kinematics_axis_type_from_char(config->type);

    switch (kinematics) {
    case KINEMATICS_COREXY:
        if ((axis->type == AXIS_TYPE_X || axis->type == AXIS_TYPE_Y) &&
            axis->n_motors != 2)
            goto error;
    case KINEMATICS_COREXZ:
        if (kinematics == KINEMATICS_COREXZ &&
            (axis->type == AXIS_TYPE_X || axis->type == AXIS_TYPE_Z) &&
            axis->n_motors != 2)
            goto error;
    case KINEMATICS_CARTESIAN: {
        cartesian_kinematics_config_t *kin_config __maybe_unused;
        kin_config = kinematics_get_config();
        axis->min = kin_config->limits[axis->type].min;
        axis->max = kin_config->limits[axis->type].max;
        axis->length = axis->max - axis->min;
        for (i = 0; i < axis->n_motors; i++)
            axis->motors[i].name = strdup(config->steppers[i]);
        break;
    }
    case KINEMATICS_DELTA: {
        delta_kinematics_config_t *kin_config __maybe_unused;
        kin_config = kinematics_get_config();
        axis->min = kin_config->limits[axis->type].min;
        axis->max = kin_config->limits[axis->type].max;
        axis->length = axis->max - axis->min;
        for (i = 0; i < axis->n_motors; i++)
            axis->motors[i].name = strdup(config->steppers[i]);
        break;
    }
    default:
        goto error;
    }

    return axis;

error:
    free(axis->motors);
    object_cache_destroy(axis_event_cache);
    free((char *)axis->endstop_name);
    free(axis);
    return NULL;
}

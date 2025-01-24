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
#include "stepper.h"
#include <common_defs.h>
#include <logging.h>
#include "object_defs.h"
#include <cache.h>
#include <math.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <utils.h>

typedef struct {
    uint32_t steps_per_rotation;
    uint32_t microsteps;
    uint32_t start_speed;
    uint32_t steps_per_mm;
    const char driver[16];
    char enable_pin[8];
    char dir_pin[8];
    char step_pin[8];
} stepper_config_params_t;

typedef struct {
    double rate;
    double time;
    double distance;
    uint64_t start;
} accel_data_t;

typedef struct {
    core_object_t object;
    core_object_command_t *current_cmd;
    stepper_config_params_t config;
    uint64_t last_timestep;
    uint64_t move_steps;
    int64_t current_step;
    double steps;
    double rps;
    double spns;
    accel_data_t accel;
    accel_data_t decel;
    stepper_move_dir_t dir;
    bool enabled;
    bool use_pins;
    uint8_t pin_word;
    pthread_t pin_thread;
} stepper_t;

static object_cache_t *stepper_event_cache = NULL;

static void stepper_update(core_object_t *object, uint64_t ticks,
                           uint64_t timestep);
static int stepper_exec(core_object_t *object, core_object_command_t *cmd);
static int stepper_enable(core_object_t *object, uint64_t id, void *args);
static int stepper_set_speed(core_object_t *object, uint64_t id, void *args);
static int stepper_set_accel(core_object_t *object, uint64_t id, void *args);
static int stepper_move(core_object_t *object, uint64_t id, void *args);
static int stepper_use_pins(core_object_t *object, uint64_t id, void *args);
static void stepper_reset(core_object_t *object);
static void stepper_status(core_object_t *object, void *status);
static void stepper_destroy(core_object_t *object);

typedef int (*command_func_t)(core_object_t *object, uint64_t id, void *args);

static const command_func_t command_handlers[] = {
    [STEPPER_COMMAND_ENABLE] = stepper_enable,
    [STEPPER_COMMAND_SET_SPEED] = stepper_set_speed,
    [STEPPER_COMMAND_SET_ACCEL] = stepper_set_accel,
    [STEPPER_COMMAND_MOVE] = stepper_move,
    [STEPPER_COMMAND_USE_PINS] = stepper_use_pins,
};

stepper_t *object_create(const char *name, void *config_ptr) {
    stepper_t *stepper;
    stepper_config_params_t *config = (stepper_config_params_t *)config_ptr;

    stepper = calloc(1, sizeof(*stepper));
    if (!stepper)
        return NULL;

    stepper->object.type = OBJECT_TYPE_STEPPER;
    stepper->object.update = stepper_update;
    stepper->object.get_state = stepper_status;
    stepper->object.reset = stepper_reset;
    stepper->object.destroy = stepper_destroy;
    stepper->object.exec_command = stepper_exec;
    stepper->object.name = strdup(name);
    memcpy(&stepper->config, config, sizeof(stepper->config));
    stepper->spns = (double)config->start_speed / SEC_TO_NSEC(1);

    if (object_cache_create(&stepper_event_cache,
                            sizeof(stepper_move_comeplete_event_data_t))) {
        core_object_destroy(&stepper->object);
        free(stepper);
        return NULL;
    }

    stepper_reset((core_object_t *)stepper);
    return stepper;
}

static void stepper_reset(core_object_t *object) {
    stepper_t *stepper = (stepper_t *)object;

    stepper->current_step = 0;
    stepper->current_cmd = 0;
    stepper->dir = MOVE_DIR_NONE;
    stepper->steps = 0;
    stepper->move_steps = 0;
    memset(&stepper->accel, 0, sizeof(stepper->accel));
    memset(&stepper->decel, 0, sizeof(stepper->decel));
    stepper->enabled = false;
}

static int stepper_enable(core_object_t *object, uint64_t id, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_enable_args *opts = (struct stepper_enable_args *)args;

    stepper->enabled = !!opts->enable;
    log_debug(stepper, "Enabling %s %u", stepper->object.name,
              stepper->enabled);
    return 0;
}

static int stepper_set_speed(core_object_t *object, uint64_t id, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_set_speed_args *opts = (struct stepper_set_speed_args *)args;

    log_debug(stepper, "SPS: %f", opts->steps_per_second);
    stepper->spns = opts->steps_per_second / SEC_TO_NSEC(1);
    return 0;
}

static int stepper_set_accel(core_object_t *object, uint64_t id, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_set_accel_args *opts = (struct stepper_set_accel_args *)args;

    log_debug(stepper, "accel: %f, decel: %f", opts->accel, opts->decel);
    stepper->accel.rate = (double)opts->accel / pow(SEC_TO_NSEC(1), 2);
    if (!opts->decel)
        opts->decel = opts->accel;
    stepper->decel.rate = (double)opts->decel / pow(SEC_TO_NSEC(1), 2);

    // Compute the number of steps required to stop based
    // on deceleration rate. The number of steps to reach
    // the desired speed is just an
    stepper->accel.time = stepper->spns / stepper->accel.rate;
    stepper->accel.distance =
        0.5 * stepper->accel.rate * pow(stepper->accel.time, 2);
    stepper->decel.time = stepper->spns / stepper->decel.rate;
    stepper->decel.distance = 0.5 * pow(stepper->spns, 2) / stepper->decel.rate;
    return 0;
}

static int stepper_move(core_object_t *object, uint64_t id, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_move_args *opts = (struct stepper_move_args *)args;

    if (!stepper->enabled)
        return -1;

    stepper->dir = opts->direction;
    stepper->move_steps = opts->steps;
    stepper->steps = 0;
    stepper->accel.start = 0;
    stepper->decel.start = 0;

    log_debug(stepper, "Stepper %s moving %lu steps in %u",
              stepper->object.name, stepper->move_steps, stepper->dir);
    return 0;
}

enum {
    ENABLE_PIN = (1 << 0),
    DIR_PIN = (1 << 1),
    STEP_PIN = (1 << 2),
};

#define EN_DIR_MASK (ENABLE_PIN | DIR_PIN)

static void *pin_monitor_thread(void *args) {
    stepper_t *stepper = (stepper_t *)args;
    struct timespec sleep = { .tv_sec = 0, .tv_nsec = 1000 };

    while (*(volatile bool *)&stepper->use_pins) {
        uint8_t val = __atomic_fetch_and(&stepper->pin_word, EN_DIR_MASK,
                                         __ATOMIC_SEQ_CST);
        stepper->enabled = val & ENABLE_PIN;
        stepper->dir = MOVE_DIR_BACK - !!(val & DIR_PIN);
        stepper->current_step += (!!(val & ENABLE_PIN) & !!(val & STEP_PIN)) *
                                 (-1 + !!(val & DIR_PIN) * 2);
        nanosleep(&sleep, NULL);
    }

    return NULL;
}

static int stepper_use_pins(core_object_t *object, uint64_t id, void *args) {
    stepper_t *stepper = (stepper_t *)object;
    struct stepper_use_pin_args *opts = (struct stepper_use_pin_args *)args;
    int ret = 0;

    if (opts->enable && !stepper->use_pins) {
        pthread_attr_t attrs;

        stepper->use_pins = true;
        ret = pthread_attr_init(&attrs);
        if (!ret)
            ret = pthread_create(&stepper->pin_thread, &attrs,
                                 pin_monitor_thread, stepper);

        pthread_attr_destroy(&attrs);
    } else if (!opts->enable) {
        // This will also stop the thread.
        stepper->use_pins = false;
        pthread_join(stepper->pin_thread, NULL);
    }

    CORE_CMD_COMPLETE(stepper, id, ret);
    return ret;
}

static int stepper_exec(core_object_t *object, core_object_command_t *cmd) {
    stepper_t *stepper = (stepper_t *)object;
    int ret;

    if (stepper->current_cmd)
        return -1;

    ret = command_handlers[cmd->object_cmd_id](object, cmd->command_id,
                                               cmd->args);
    if (ret)
        return ret;

    stepper->current_cmd = cmd;
    return 0;
}

static void stepper_status(core_object_t *object, void *status) {
    stepper_status_t *s = (stepper_status_t *)status;
    stepper_t *stepper = (stepper_t *)object;

    memset(s, 0, sizeof(*s));
    s->enabled = stepper->enabled;
    s->steps = stepper->current_step;
    s->spr = stepper->config.steps_per_rotation;
    s->microsteps = stepper->config.microsteps;
    s->speed = stepper->spns;
    s->accel = stepper->accel.rate;
    s->decel = stepper->accel.rate;
    s->steps_per_mm = stepper->config.steps_per_mm;
    s->pin_addr = stepper->use_pins ? (unsigned long)&stepper->pin_word : 0;
    memcpy(s->enable_pin, stepper->config.enable_pin,
           sizeof(s->enable_pin) + sizeof(s->dir_pin) + sizeof(s->step_pin));
}

static void stepper_update(core_object_t *object, uint64_t ticks,
                           uint64_t timestep) {
    stepper_t *stepper = (stepper_t *)object;
    uint64_t delta = timestep - stepper->last_timestep;

    if (stepper->use_pins || !stepper->current_cmd)
        goto done;

    if (stepper->current_cmd->object_cmd_id != STEPPER_COMMAND_MOVE) {
        CORE_CMD_COMPLETE(stepper, stepper->current_cmd->command_id, 0);
        stepper->current_cmd = NULL;
        goto done;
    }

    if (stepper->steps < stepper->move_steps) {
        double current_speed;
        double steps;

        if (stepper->accel.rate && stepper->steps < stepper->accel.distance) {
            if (!stepper->accel.start)
                stepper->accel.start = timestep;
            current_speed =
                (timestep - stepper->accel.start) * stepper->accel.rate;
        } else if (stepper->decel.rate &&
                   stepper->move_steps - stepper->steps <=
                   stepper->decel.distance) {
            current_speed = stepper->spns - ((timestep - stepper->decel.start) *
                                             stepper->decel.rate);
        } else {
            stepper->decel.start = timestep;
            current_speed = stepper->spns;
        }

        steps = current_speed * delta;

        if (steps > stepper->move_steps - stepper->steps)
            steps = stepper->move_steps - stepper->steps;

        if (stepper->dir == MOVE_DIR_BACK)
            stepper->current_step -= steps;
        else
            stepper->current_step += steps;

        stepper->steps += steps;
        log_debug(stepper, "Current steps: %.15f, inc: %.15f, remaining: %.15f",
                  stepper->current_step, steps,
                  stepper->move_steps - stepper->steps);
    } else if (stepper->current_cmd->object_cmd_id == STEPPER_COMMAND_MOVE) {
        stepper_move_comeplete_event_data_t *data;

        CORE_CMD_COMPLETE(stepper, stepper->current_cmd->command_id, 0);
        stepper->current_cmd = NULL;
        stepper->steps = 0.0;
        stepper->move_steps = 0.0;

        data = object_cache_alloc(stepper_event_cache);
        if (data) {
            data->steps = stepper->current_step;
            CORE_EVENT_SUBMIT(stepper, OBJECT_EVENT_STEPPER_MOVE_COMPLETE,
                              data);
        }
    }

done:
    stepper->last_timestep = timestep;
}

static void stepper_destroy(core_object_t *object) {
    stepper_t *stepper = (stepper_t *)object;

    if (stepper->use_pins) {
        stepper->use_pins = false;
        pthread_join(stepper->pin_thread, NULL);
    }

    core_object_destroy(object);
    object_cache_destroy(stepper_event_cache);
    free(stepper);
}

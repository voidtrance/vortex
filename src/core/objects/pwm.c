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
#include "vobj_defs.h"
#include <common_defs.h>
#include <string.h>
#include <cache.h>
#include "pwm.h"

typedef struct {
    uint8_t pwm_max;
    char pin[PIN_NAME_SIZE];
} pwm_config_t;

typedef struct {
    core_object_t object;
    pwm_config_t config;
    uint64_t last_timestamp;
    char obj_name[OBJECT_NAME_SIZE];
    core_object_t *obj;
    uint32_t pwm_counter_remain;
    uint32_t duty_cycle;
    uint16_t prescaler;
    core_object_klass_t obj_type;
    bool state;
    object_cache_t *cache;
} pwm_t;

static int pwm_init(core_object_t *object) {
    pwm_t *pwm = (pwm_t *)object;

    pwm->last_timestamp = 0;
    pwm->duty_cycle = 0;
    return 0;
}

static void pwm_state(core_object_t *object, void *state) {
    pwm_t *pwm = (pwm_t *)object;
    pwm_state_t *pwm_state = (pwm_state_t *)state;

    memset(pwm_state, 0, sizeof(*pwm_state));
    pwm_state->counter = pwm->config.pwm_max;
    pwm_state->on = pwm->state;
    pwm_state->pwm_max = pwm->config.pwm_max;
    pwm_state->duty_cycle = pwm->duty_cycle;
    strncpy(pwm_state->pin, pwm->config.pin, PIN_NAME_SIZE);
}

static void pwm_update(core_object_t *object, uint64_t ticks,
                       uint64_t timestamp) {
    pwm_t *pwm = (pwm_t *)object;
    uint64_t delta = timestamp - pwm->last_timestamp;
    uint32_t pwm_counter_value;
    struct digital_pin_set_args *args;

    if (!pwm->prescaler || !pwm->obj || !pwm->duty_cycle)
        return;

    pwm_counter_value = (delta / pwm->prescaler) + pwm->pwm_counter_remain;
    pwm->pwm_counter_remain = pwm_counter_value % pwm->config.pwm_max;
    pwm->last_timestamp = timestamp;
    pwm->state = pwm->pwm_counter_remain < pwm->duty_cycle;
    args = object_cache_alloc(pwm->cache);
    args->state = pwm->state;
    CORE_CMD_SUBMIT(pwm, pwm->obj, DIGITAL_PIN_SET, NULL, args);
}

static int pwm_exec(core_object_t *object, core_object_command_t *cmd) {
    pwm_t *pwm = (pwm_t *)object;

    if (cmd->object_cmd_id == PWM_SET_PARAMS) {
        struct pwm_set_parms_args *args = cmd->args;
        pwm->prescaler = args->prescaler;
    } else if (cmd->object_cmd_id == PWM_SET_OBJECT) {
        struct pwm_set_object_args *args = cmd->args;
        pwm->obj_type = args->type;
        strncpy(pwm->obj_name, args->object_name, OBJECT_NAME_SIZE);
        pwm->obj = CORE_LOOKUP_OBJECT(pwm, pwm->obj_type, pwm->obj_name);
        if (!pwm->obj)
            return -1;
    } else if (cmd->object_cmd_id == PWM_SET_DUTY_CYCLE) {
        struct pwm_set_duty_cycle_args *args = cmd->args;
        if (args->duty_cycle > pwm->config.pwm_max)
            return -1;
        pwm->duty_cycle = args->duty_cycle;
    }

    CORE_CMD_COMPLETE(pwm, cmd->command_id, 0, NULL);
    return 0;
}

static void pwm_destroy(core_object_t *object) {
    pwm_t *pwm = (pwm_t *)object;

    core_object_destroy(object);
    free(pwm);
}

pwm_t *object_create(const char *name, void *config_ptr) {
    pwm_t *pwm;

    pwm = calloc(1, sizeof(*pwm));
    if (!pwm)
        return NULL;

    pwm->object.klass = OBJECT_KLASS_PWM;
    pwm->object.update_frequency = 100000;
    pwm->object.name = strdup(name);
    pwm->object.init = pwm_init;
    pwm->object.update = pwm_update;
    pwm->object.exec_command = pwm_exec;
    pwm->object.get_state = pwm_state;
    pwm->object.destroy = pwm_destroy;
    memcpy(&pwm->config, config_ptr, sizeof(pwm->config));

    if (object_cache_create(&pwm->cache, sizeof(struct digital_pin_set_args))) {
        free(pwm);
        return NULL;
    }

    return pwm;
}
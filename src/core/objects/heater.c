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
#include <stdlib.h>
#include <pthread.h>
#include "object_defs.h"
#include <common_defs.h>
#include "heater_compute.h"
#include <utils.h>
#include "heater.h"
#include <cache.h>
#include <atomics.h>
#include <debug.h>
#include <errno.h>
#include <math.h>

#define PRECISION 3

typedef struct {
    float kp; // Proportional gain
    float ki; // Integral gain
    float kd; // Derivative gain
    float prev_error; // Previous error value
    float integral; // Integral accumulator
    float output_min; // Minimum output limit (anti-windup)
    float output_max; // Maximum output limit (anti-windup)
} heater_pid_control_t;

typedef struct {
    uint16_t power;
    char pin[PIN_NAME_SIZE];
    float max_temp;
    float kp;
    float ki;
    float kd;
    heater_layer_t layers[MAX_LAYER_COUNT];
} heater_config_params_t;

typedef struct {
    float power; /* watts */
    float max_temp;
    float current; /* celsius */
    float ambient; /* celsius */
    float target; /* celsius */
    heater_data_t *compute;
} temp_data_t;

typedef struct {
    core_object_t object;
    core_object_command_t command;
    uint64_t timestep;
    temp_data_t temp_data;
    char pin[PIN_NAME_SIZE];
    bool use_pins;
    uint8_t pin_word;
    pthread_t pin_thread;
    heater_pid_control_t pid_control;
} heater_t;

static object_cache_t *heater_event_cache = NULL;

static void heater_update(core_object_t *object, uint64_t ticks,
                          uint64_t timestamp);
static int heater_set_temp(heater_t *heater,
                           struct heater_set_temperature_args *args);
static int heater_use_pins(heater_t *heater,
                           struct heater_use_pins_args *args);
static int heater_exec_cmd(core_object_t *object, core_object_command_t *cmd);
static void heater_status(core_object_t *object, void *status);
static int heater_init(core_object_t *object);
static void heater_reset(core_object_t *object);
static void heater_destroy(core_object_t *object);

// Initialize the PID controller
static void pid_init(heater_pid_control_t *pid, float kp, float ki, float kd,
                     float output_min, float output_max) {
    pid->kp = kp;
    pid->ki = ki;
    pid->kd = kd;
    pid->prev_error = 0.0;
    pid->integral = 0.0;
    pid->output_min = output_min;
    pid->output_max = output_max;
}

heater_t *object_create(const char *name, void *config_ptr) {
    heater_t *heater;
    heater_config_params_t *config = (heater_config_params_t *)config_ptr;

    heater = calloc(1, sizeof(*heater));
    if (!heater)
        return NULL;

    heater->object.type = OBJECT_TYPE_HEATER;
    heater->object.update = heater_update;
    heater->object.update_frequency = 25; /* 25 Hz */
    heater->object.init = heater_init;
    heater->object.reset = heater_reset;
    heater->object.destroy = heater_destroy;
    heater->object.exec_command = heater_exec_cmd;
    heater->object.get_state = heater_status;
    heater->object.name = strdup(name);
    heater->temp_data.power = config->power;
    heater->temp_data.max_temp = config->max_temp;
    strncpy(heater->pin, config->pin, sizeof(heater->pin));

    if (object_cache_create(&heater_event_cache,
                            sizeof(heater_temp_reached_event_data_t))) {
        core_object_destroy(&heater->object);
        free(heater);
        return NULL;
    }


    heater->temp_data.compute = heater_compute_init(config->layers);
    if (!heater->temp_data.compute) {
        core_object_destroy(&heater->object);
        free(heater);
        return NULL;
    }

    pid_init(&heater->pid_control, config->kp, config->ki, config->kd, 0.0,
             100.0);
    heater_reset((core_object_t *)heater);
    return heater;
}

static int heater_init(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    if (heater->pid_control.kp == 0.0 || heater->pid_control.ki == 0.0 ||
        heater->pid_control.kd == 0.0) {
        log_error(heater, "Invalid PID parameters for heater %s",
                  heater->object.name);
        return -1;
    }

    heater_reset(object);
    return 0;
}

static void heater_reset(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    heater->temp_data.current = AMBIENT_TEMP;
    heater_compute_clear(heater->temp_data.compute);
}

static int heater_set_temp(heater_t *heater,
                           struct heater_set_temperature_args *args) {

    if (args->temperature < 0 || args->temperature > heater->temp_data.max_temp)
        return -1;

    heater->temp_data.target = args->temperature;

    if (heater->temp_data.current == heater->temp_data.target) {
        CORE_CMD_COMPLETE(heater, heater->command.command_id, 0, NULL);
        return 0;
    }

    return 0;
}

static void *pin_monitor_thread(void *args) {
    heater_t *heater = (heater_t *)args;
    struct timespec sleep = { .tv_sec = 0, .tv_nsec = 1000 };

    while (*(volatile bool *)&heater->use_pins) {
        uint8_t val = __atomic_load_n(&heater->pin_word, __ATOMIC_SEQ_CST);
        heater_compute_set_power(heater->temp_data.compute,
                                 val ? heater->temp_data.power : 0);
        nanosleep(&sleep, NULL);
    }

    return NULL;
}

static int heater_use_pins(heater_t *heater,
                           struct heater_use_pins_args *args) {
    int ret = 0;
    struct heater_use_pins_data *data = NULL;

    if (args->enable && !heater->use_pins) {
        pthread_attr_t attrs;

        heater->use_pins = true;
        ret = pthread_attr_init(&attrs);
        if (!ret)
            ret = pthread_create(&heater->pin_thread, &attrs,
                                 pin_monitor_thread, heater);
        pthread_attr_destroy(&attrs);
        if (!ret) {
            data = calloc(1, sizeof(*data));
            if (data)
                data->pin_addr = (unsigned long)&heater->pin_word;
            else
                ret = -ENOMEM;
        }
    } else if (!args->enable) {
        heater->use_pins = false;
        pthread_join(heater->pin_thread, NULL);
    }

    CORE_CMD_COMPLETE(heater, heater->command.command_id, ret, data);
    heater->command.command_id = 0;
    return ret;
}

static int heater_exec_cmd(core_object_t *object, core_object_command_t *cmd) {
    heater_t *heater = (heater_t *)object;
    int ret = -1;

    // If a command is still running, immediately complete it.
    if (heater->command.command_id)
        CORE_CMD_COMPLETE(heater, heater->command.command_id, 0, NULL);

    heater->command = *cmd;

    switch (cmd->object_cmd_id) {
    case HEATER_COMMAND_SET_TEMP:
        ret = heater_set_temp(heater, cmd->args);
        break;
    case HEATER_COMMAND_USE_PINS:
        ret = heater_use_pins(heater, cmd->args);
        break;
    }

    return ret;
}

static void heater_status(core_object_t *object, void *status) {
    heater_status_t *s = (heater_status_t *)status;
    heater_t *heater = (heater_t *)object;

    s->temperature = heater->temp_data.current;
    s->max_temp = heater->temp_data.max_temp;
    strncpy(s->pin, heater->pin, sizeof(s->pin));
    s->pin_addr = heater->use_pins ? (unsigned long)&heater->pin_word : 0;
}

// Update the PID controller and compute the output
static float pid_update(heater_pid_control_t *pid, float setpoint,
                        float measurement, uint64_t delta) {
    float error = setpoint - measurement;
    float derivative;
    float output;
    double dt;

    dt = (double)delta / SEC_TO_NSEC(1);
    pid->integral += error * dt;
    pid->integral = min(pid->integral, pid->output_max);
    pid->integral = max(pid->integral, pid->output_min);
    derivative = (error - pid->prev_error) / dt;
    output = pid->kp * error + pid->ki * pid->integral + pid->kd * derivative;
    output = min(output, pid->output_max);
    output = max(output, pid->output_min);
    pid->prev_error = error;

    return output / pid->output_max;
}

static void heater_update(core_object_t *object, uint64_t ticks,
                          uint64_t timestep) {
    heater_t *heater = (heater_t *)object;
    uint64_t time_delta = timestep - heater->timestep;
    heater_temp_reached_event_data_t *data;

    heater->timestep = timestep;

    /*
     * Use interpolation function to approximate temperature
     * ramp.
     */
    heater_compute_iterate(heater->temp_data.compute, time_delta, 0);
    heater->temp_data.current =
        heater_compute_get_temperature(heater->temp_data.compute);

    log_debug(heater, "heater %s temp: %f", heater->object.name,
              heater->temp_data.current);

    if (!heater->use_pins) {
        float power = pid_update(&heater->pid_control, heater->temp_data.target,
                                 heater->temp_data.current, time_delta);
        heater_compute_set_power(heater->temp_data.compute,
                                 heater->temp_data.power * power);
    }

    if (heater->command.command_id &&
        heater->command.object_cmd_id == HEATER_COMMAND_SET_TEMP) {
        float factor = pow(10, PRECISION);
        float temp = roundf(heater->temp_data.current * factor) / factor;

        if (temp != heater->temp_data.target)
            return;

        CORE_CMD_COMPLETE(heater, heater->command.command_id, 0, NULL);
        heater->command.command_id = 0;
        heater->command.object_cmd_id = HEATER_COMMAND_MAX;

        data = object_cache_alloc(heater_event_cache);
        if (data) {
            data->temp = heater->temp_data.current;
            CORE_EVENT_SUBMIT(heater, OBJECT_EVENT_HEATER_TEMP_REACHED, data);
        }
    }
}

static void heater_destroy(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    heater_compute_free(heater->temp_data.compute);
    core_object_destroy(object);
    object_cache_destroy(heater_event_cache);
    free(heater);
}

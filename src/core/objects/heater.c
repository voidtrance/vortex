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

typedef struct {
    uint16_t power;
    char pin[8];
    float max_temp;
    heater_layer_t layers[MAX_LAYER_COUNT];
} heater_config_params_t;

typedef struct {
    uint64_t compute_start; /* nanoseconds */
    double power; /* watts */
    double max_temp;
    double current; /* celsius */
    double ambient; /* celsius */
    double target; /* celsius */
    heater_data_t *compute;
} temp_data_t;

typedef struct {
    core_object_t object;
    core_object_command_t command;
    uint64_t timestep;
    temp_data_t temp_data;
    char pin[8];
    bool use_pins;
    uint8_t pin_word;
    pthread_t pin_thread;
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
static void heater_reset(core_object_t *object);
static void heater_destroy(core_object_t *object);

heater_t *object_create(const char *name, void *config_ptr) {
    heater_t *heater;
    heater_config_params_t *config = (heater_config_params_t *)config_ptr;

    heater = calloc(1, sizeof(*heater));
    if (!heater)
        return NULL;

    heater->object.type = OBJECT_TYPE_HEATER;
    heater->object.update = heater_update;
    heater->object.reset = heater_reset;
    heater->object.destroy = heater_destroy;
    heater->object.exec_command = heater_exec_cmd;
    heater->object.get_state = heater_status;
    heater->object.name = strdup(name);
    heater->temp_data.compute_start = 0;
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

    heater_reset((core_object_t *)heater);
    return heater;
}

static void heater_reset(core_object_t *object) {
    heater_t *heater = (heater_t *)object;

    heater->temp_data.current = AMBIENT_TEMP;
    heater->temp_data.compute_start = 0;
    heater_compute_clear(heater->temp_data.compute);
}

static int heater_set_temp(heater_t *heater,
                           struct heater_set_temperature_args *args) {

    if (args->temperature < 0 || args->temperature > heater->temp_data.max_temp)
        return -1;

    heater->temp_data.target = args->temperature;

    if (heater->temp_data.current == heater->temp_data.target) {
        CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);
        return 0;
    }

    if (heater->temp_data.target > heater->temp_data.current)
        heater_compute_set_power(heater->temp_data.compute,
                                 heater->temp_data.power);
    else
        heater_compute_set_power(heater->temp_data.compute, 0);

    heater->temp_data.compute_start = 0;
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

    if (args->enable && !heater->use_pins) {
        pthread_attr_t attrs;

        heater->use_pins = true;
        ret = pthread_attr_init(&attrs);
        if (!ret)
            ret = pthread_create(&heater->pin_thread, &attrs,
                                 pin_monitor_thread, heater);

        pthread_attr_destroy(&attrs);
    } else if (!args->enable) {
        heater->use_pins = false;
        pthread_join(heater->pin_thread, NULL);
    }

    CORE_CMD_COMPLETE(heater, heater->command.command_id, ret);
    heater->command.command_id = 0;
    return ret;
}

static int heater_exec_cmd(core_object_t *object, core_object_command_t *cmd) {
    heater_t *heater = (heater_t *)object;
    int ret = -1;

    // If a command is still running, immediately complete it.
    if (heater->command.command_id)
        CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);

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

static void heater_update(core_object_t *object, uint64_t ticks,
                          uint64_t timestep) {
    heater_t *heater = (heater_t *)object;
    uint64_t time_delta = timestep - heater->timestep;
    heater_temp_reached_event_data_t *data;

    if (heater->temp_data.compute_start == 0)
        heater->temp_data.compute_start = timestep;

    heater->timestep = timestep;

    /*
     * Use interpolation function to approximate temperature
     * ramp.
     */
    heater_compute_iterate(heater->temp_data.compute, time_delta,
        timestep - heater->temp_data.compute_start);
    heater->temp_data.current =
        heater_compute_get_temperature(heater->temp_data.compute);

    log_debug(heater, "heater %s temp: %f", heater->object.name,
              heater->temp_data.current);

    if (heater->command.command_id &&
        heater->command.object_cmd_id == HEATER_COMMAND_SET_TEMP) {
        if (heater->temp_data.current != heater->temp_data.target)
            return;

        CORE_CMD_COMPLETE(heater, heater->command.command_id, 0);
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

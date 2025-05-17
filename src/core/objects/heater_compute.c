/*
 * Copyright (c) 2023-2023 Paniel Detersson
 * Copyright (c) 2024  Mitko Haralanov
 *
 * Permission is hereby granted, free of charge, to any person obtaining
 * a copy of this software and associated documentation files
 * (the "Software"), to deal in the Software without restriction,
 * including without limitation the rights to use, copy, modify, merge,
 * publish, distribute, sublicense, and/or sell copies of the Software,
 * and to permit persons to whom the Software is furnished to do so,
 * subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 * MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 * IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
 * CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
 * TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
 * SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
 */
#include "heater_compute.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <utils.h>
#include <sys/types.h>

/* Stefan-Boltzmann constant */
#define kSB 0.0000000567

/* Emissivity compensation factor */
#define ECF 0.85

/* Object element resolution.
 * Heater objects will be split into elements based on
 * this value.
 */
#define RESOLUTION 0.005

/* Conversion factors */
#define MM_TO_M(x) ((x) / 1000)
#define CM_TO_M(x) ((x) / 100)
#define M_TO_CM(x) ((x) * 100)

#define C_TO_KELVIN(x) ((x) + 273)

static double Ta4;

typedef struct {
    size_t x;
    size_t y;
    size_t z;
} elem_t;

typedef struct {
    heater_layer_type_t type;
    heater_material_t material;
    heater_object_size_t size;
    elem_t elems;
} layer_t;

typedef struct {
    size_t heater_start_x;
    size_t heater_start_y;
    size_t heater_end_x;
    size_t heater_end_y;
} iteration_values_t;

struct heater_data {
    double *dQs;
    double *temperature;
    size_t size;
    layer_t *layers;
    size_t n_layers;
    ssize_t body;
    ssize_t heater;
    elem_t sensor;
    double power;
    iteration_values_t values;
};

static size_t elemIndex(layer_t *layer, size_t x, size_t y, size_t z) {
		return z * layer->elems.x * layer->elems.y + y * layer->elems.x + x;
}

static void compute_elems(layer_t *layer, heater_object_size_t *size) {
    layer->size.x = MM_TO_M(size->x);
    layer->elems.x = max(layer->size.x / RESOLUTION, 1);
    layer->size.y = MM_TO_M(size->y);
    layer->elems.y = max(layer->size.y / RESOLUTION, 1);
    layer->size.z = MM_TO_M(size->z);
    layer->elems.z = max(layer->size.z / RESOLUTION, 1);
}

heater_data_t *heater_compute_init(heater_layer_t *layers) {
    heater_data_t *data;
    double layers_height = 0.0;
    double current_height = 0.0;
    size_t i;

    data = calloc(1, sizeof(*data));
    if (!data)
        return NULL;

    data->layers = calloc(MAX_LAYER_COUNT, sizeof(*data->layers));
    if (!data->layers)
        goto bail;

    data->body = -1;
    data->heater = -1;
    for (i = 0; i < MAX_LAYER_COUNT; i++) {
        if (layers[i].type == HEATER_LAYER_TYPE_NONE)
            break;
        memcpy(&data->layers[i], &layers[i], sizeof(layers[i]));
        compute_elems(&data->layers[i], &layers[i].size);
        layers_height += data->layers[i].size.z;
        if (data->layers[i].type == HEATER_LAYER_TYPE_BODY)
             data->body = i;
        else if (data->layers[i].type == HEATER_LAYER_TYPE_HEATER)
             data->heater = i;
     }

     data->n_layers = i;
     data->size = data->layers[data->body].elems.x *
         data->layers[data->body].elems.y * data->n_layers;

	 if (data->body == -1 || data->heater == -1)
         goto bail_layers;

     data->sensor.x = (size_t)(data->layers[data->body].size.x / 2 / RESOLUTION);
     data->sensor.y = (size_t)(data->layers[data->body].size.y / 2 / RESOLUTION);

     for (i = 0; i < data->n_layers; i++) {
         current_height += data->layers[i].size.z;
         if (layers_height / 2 < current_height) {
             data->sensor.z = i;
             break;
         }
     }

     data->dQs = malloc(data->size * sizeof(*data->dQs));
     if (!data->dQs)
         goto bail_layers;

     data->temperature = malloc(data->size * sizeof(*data->temperature));
     if (!data->temperature)
         goto bail_dqs;

     heater_compute_clear(data);

     data->values.heater_start_x =
         (size_t)floor((double)(data->layers[data->body].elems.x -
                                  data->layers[data->heater].elems.x) / 2);
     data->values.heater_start_y =
         (size_t)floor((double)(data->layers[data->body].elems.y -
                                  data->layers[data->heater].elems.y) / 2);
     data->values.heater_end_x = data->values.heater_start_x +
         data->layers[data->heater].elems.x;
     data->values.heater_end_y = data->values.heater_start_y +
         data->layers[data->heater].elems.y;

     Ta4 = pow(C_TO_KELVIN(AMBIENT_TEMP), 4);
     return data;

 bail_dqs:
     free(data->dQs);
 bail_layers:
     free(data->layers);
 bail:
     free(data);
     return NULL;
}

void heater_compute_set_power(heater_data_t *data, double wattage) {
    data->power = wattage;
}

static void compute_conduction(heater_data_t *data, layer_t *layer, size_t elem,
                               size_t next, double dt) {
    double dT = data->temperature[elem] - data->temperature[next];
    double kH = layer->material.conductivity;
    double A = layer->size.z * RESOLUTION;
    double dx = RESOLUTION;
    double dQ = kH * A * dT * dt / dx;

    data->dQs[elem] -= dQ;
    data->dQs[next] += dQ;
}

static void compute_convection(heater_data_t *data, double z_size, size_t elem,
                               double emissivity, double convection,
                               double dt) {
    double A = z_size * RESOLUTION;
    double temp = data->temperature[elem];
    double k_temp = C_TO_KELVIN(temp);
    double dTa = temp - AMBIENT_TEMP;
    double p_temp = 1;
    size_t i = 0;

    data->dQs[elem] -= convection * A * dt * dTa;

    // Open-coding pow(k_temp, 4) is significantly faster than
    // using the pow() function.
    while (i++ < 4)
        p_temp *= k_temp;

    data->dQs[elem] -= emissivity * kSB * A * (p_temp - Ta4) * dt * ECF;
}

void heater_compute_iterate(heater_data_t *data, uint64_t delta,
                            uint64_t runtime) {
    double dt = (double)delta / SEC_TO_NSEC(1);
    layer_t *heater = &data->layers[data->heater];
    layer_t *body = &data->layers[data->body];
    double JpI = data->power * dt;
    double JpE = JpI / (heater->elems.x * heater->elems.y);
    size_t x;
    size_t y;
    size_t l;

    memset(data->dQs, 0, sizeof(*data->dQs) * data->size);

    for (y = 0; y < body->elems.y; y++) {
        for (x = 0; x < body->elems.x; x++) {
            if ((x >= data->values.heater_start_x &&
                 x < data->values.heater_end_x) &&
                (y >= data->values.heater_start_y &&
                 y < data->values.heater_end_y))
                data->dQs[elemIndex(body, x, y, 0)] = JpE;
        }
    }

    /* Compute heat conduction between elements */
    for (l = 0; l < data->n_layers; l++) {
        for (y = 0; y < body->elems.y; y++) {
            for (x = 0; x < body->elems.x; x++) {
                size_t elem = elemIndex(body, x, y, l);
                layer_t *layer = &data->layers[l];

                if (x < body->elems.x - 1) {
                    compute_conduction(data, layer, elem,
                                       elemIndex(body, x + 1, y, l), dt);
                }

                if (y < body->elems.y - 1) {
                    compute_conduction(data, layer, elem,
                                       elemIndex(body, x, y + 1, l), dt);
                }

                if (l < data->n_layers - 1) {
                    size_t next = elemIndex(body, x, y, l + 1);
                    layer_t *next_layer = &data->layers[l + 1];
                    double dT = data->temperature[elem] -
                        data->temperature[next];
                    double k1Inv = 0.5 * layer->size.z /
                        layer->material.conductivity;
                    double k2Inv = 0.5 * next_layer->size.z /
                        next_layer->material.conductivity;
                    double kH_dx = 1 / (k1Inv + k2Inv);
                    double A = RESOLUTION * RESOLUTION;
                    double dQ = kH_dx * A * dT * dt;

                    data->dQs[elem] -= dQ;
                    data->dQs[next] += dQ;
                }
            }
        }
    }

    /* Compute TOP convection */
    for (y = 0; y < body->elems.y; y++) {
        layer_t *layer = &data->layers[data->n_layers - 1];

        for (x = 0; x < body->elems.x; x++)
            compute_convection(data, RESOLUTION, elemIndex(body, x, y,
                                                           data->n_layers - 1),
                               layer->material.emissivity,
                               body->material.convection[CONV_TOP], dt);
    }

    /* Compute BOTTOM convection */
    for (y = 0; y < body->elems.y; y++) {
        layer_t *layer = &data->layers[data->heater];

        for (x = 0; x < body->elems.x; x++)
            compute_convection(data, RESOLUTION, elemIndex(body, x, y, 0),
                               layer->material.emissivity,
                               body->material.convection[CONV_BOTTOM], dt);
    }

    /* Compute FRONT convection */
    for (l = 0; l < data->n_layers; l++) {
        layer_t *layer = &data->layers[l];

        for (x = 0; x < body->elems.x; x++)
            compute_convection(data, layer->size.z, elemIndex(body, x, 0, l),
                               layer->material.emissivity,
                               body->material.convection[CONV_TOP], dt);
    }

    /* Compute BACK convection */
    for (l = 0; l < data->n_layers; l++) {
        layer_t *layer = &data->layers[l];

        for (x = 0; x < body->elems.x; x++)
            compute_convection(data, layer->size.z, elemIndex(body, x,
                                                              body->elems.y - 1,
                                                              l),
                               layer->material.emissivity,
                               body->material.convection[CONV_TOP], dt);
    }

    /* Compute LEFT convection */
    for (l = 0; l < data->n_layers; l++) {
        layer_t *layer = &data->layers[l];

        for (y = 0; y < body->elems.y; y++)
            compute_convection(data, layer->size.z, elemIndex(body, 0, y, l),
                               layer->material.emissivity,
                               body->material.convection[CONV_TOP], dt);
    }

    /* Compute RIGHT convection */
    for (l = 0; l < data->n_layers; l++) {
        layer_t *layer = &data->layers[l];

        for (y = 0; y < body->elems.y; y++)
            compute_convection(data, layer->size.z, elemIndex(body,
                                                              body->elems.x - 1,
                                                              y, l),
                               layer->material.emissivity,
                               body->material.convection[CONV_TOP], dt);
    }

    /* Compute element temperatures */
    for (l = 0; l < data->n_layers; l++) {
        layer_t *layer = &data->layers[l];
        double c = layer->material.capacity * layer->material.density *
            RESOLUTION * RESOLUTION * layer->size.z;

        for (y = 0; y < body->elems.y; y++) {
            for (x = 0; x < body->elems.x; x++) {
                size_t elem = elemIndex(body, x, y, l);

                data->temperature[elem] += data->dQs[elem] / c;
            }
        }
    }
}

double heater_compute_get_temperature(heater_data_t *data) {
    size_t elem = elemIndex(&data->layers[data->body], data->sensor.x,
                            data->sensor.y, data->sensor.z);

    return data->temperature[elem];
}

void heater_compute_clear(heater_data_t *data) {
    size_t i;

    memset(data->dQs, 0, sizeof(*data->dQs) * data->size);
    for (i = 0; i < data->size; i++)
        data->temperature[i] = AMBIENT_TEMP;
}

void heater_compute_free(heater_data_t *data) {
    free(data->temperature);
    free(data->dQs);
    free(data->layers);
    free(data);
}

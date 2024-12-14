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

#ifndef __HEATER_COMPUTE_H__
#define __HEATER_COMPUTE_H__
#include <stdint.h>
#include <stddef.h>

#define MAX_LAYER_COUNT 8

typedef enum {
    HEATER_LAYER_TYPE_NONE,
    HEATER_LAYER_TYPE_HEATER,
    HEATER_LAYER_TYPE_BODY,
    HEATER_LAYER_TYPE_OTHER,
    HEATER_LAYER_TYPE_MAX
} heater_layer_type_t;

typedef enum {
    CONV_TOP,
    CONV_BOTTOM,
    CONV_MAX
} convection_type_t;

typedef struct {
    double x;
    double y;
    double z;
} heater_object_size_t;

typedef struct {
    double density;
    double capacity;
    double conductivity;
    double emissivity;
    float convection[CONV_MAX];
} heater_material_t;

typedef struct {
    heater_layer_type_t type;
    heater_material_t material;
    heater_object_size_t size;
} heater_layer_t;

#define AMBIENT_TEMP 25.0

typedef struct heater_data heater_data_t;

heater_data_t *heater_compute_init(heater_layer_t *layers);
void heater_compute_set_power(heater_data_t *data, double wattage);
void heater_compute_iterate(heater_data_t *data, uint64_t delta, uint64_t runtime);
double heater_compute_get_temperature(heater_data_t *data);
void heater_compute_clear(heater_data_t *data);
void heater_compute_free(heater_data_t *data);

#endif

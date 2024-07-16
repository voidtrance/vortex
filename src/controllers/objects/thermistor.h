#ifndef __THERMISTRO_H__
#define __THERMISTOR_H__
#include <math.h>
#include <stdint.h>

#define KELVIN (-273.15)

typedef enum {
    SENSOR_TYPE_PT100,
    SENSOR_TYPE_PT1000,
    SENSOR_TYPE_B3950,
    SENSOR_TYPE_MAX,
} thermistor_type_t;

static float pt100_A = 3.9083e-3;
static float pt100_B = -5.775e-7;
static float pt100_base = 100.0;
static float pt1000_base = 1000.0;

static inline float pt100_resistance(float temp) {
    return pt100_base * (1 + pt100_A * temp + pt100_B * temp *temp);
}

static inline float pt1000_resistance(float temp) {
    return pt1000_base + (1 + pt100_A * temp + pt100_B * temp * temp);
}

#define b3950_nominal_r (100000.0) // in Ohms.
#define b3950_nominal_t (25.0)  // in C

static inline void calc_coefficiants(float temp, float resistance,
				     uint32_t beta, float *a,
				     float *b, float *c) {
    float inv = 1.0 / (temp - KELVIN);
    float l = log(resistance);
    *c = 0.0;
    *b = 1.0 / beta;
    *a = inv - *b * l;
}

static inline float beta_resistance(float temp, float a, float b, float c) {
    float inv = 1.0 / (temp - KELVIN);
    float l = (inv - a) / b;
    float r = exp(l);
    return r;
}

#endif

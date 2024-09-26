#!/usr/bin/env python3
import sys
import math
import time

def powin(a, b):
    return math.pow(a, b)

def powout(a, b):
    return 1 - math.pow(1-a, b)

def powinout(a, b):
    a *= 2
    if a < 1:
        return 0.5 * math.pow(a, b)
    return 1 - 0.5 * math.fabs(math.pow(2-a, b))

LINEAR              = 0x01,
QUADRATIC_IN        = 0x02,
QUADRATIC_OUT       = 0x03,
QUADRATIC_INOUT     = 0x04,
CUBIC_IN            = 0x05,
CUBIC_OUT           = 0x06,
CUBIC_INOUT         = 0x07,
QUARTIC_IN          = 0x08,
QUARTIC_OUT         = 0x09,
QUARTIC_INOUT       = 0x0A,
QUINTIC_IN          = 0x0B,
QUINTIC_OUT         = 0x0C,
QUINTIC_INOUT       = 0x0D,
SINUSOIDAL_IN       = 0x0E,
SINUSOIDAL_OUT      = 0x0F,
SINUSOIDAL_INOUT    = 0x10,
EXPONENTIAL_IN      = 0x11,
EXPONENTIAL_OUT     = 0x12,
EXPONENTIAL_INOUT   = 0x13,
CIRCULAR_IN         = 0x14,
CIRCULAR_OUT        = 0x15,
CIRCULAR_INOUT      = 0x16,
ELASTIC_IN          = 0x17,
ELASTIC_OUT         = 0x18,
ELASTIC_INOUT       = 0x19,
BACK_IN             = 0x1A,
BACK_OUT            = 0x1B,
BACK_INOUT          = 0x1C,
BOUNCE_IN           = 0x1D,
BOUNCE_OUT          = 0x1E,
BOUNCE_INOUT        = 0x1F

def calc(k, mode):
    if k == 0 or k == 1:
        return k
    if mode == QUADRATIC_IN:
        return powin(k,2)
    if mode == QUADRATIC_OUT:
        return powout(k,2)
    if mode == QUADRATIC_INOUT:
        return powinout(k,2)
    if mode == CUBIC_IN:
        return powin(k,3)
    if mode == CUBIC_OUT:
        return powout(k,3)
    if mode == CUBIC_INOUT:
        return powinout(k,3)
    if mode == QUARTIC_IN:
        return powin(k,4)
    if mode == QUARTIC_OUT:
        return powout(k,4)
    if mode == QUARTIC_INOUT:
        return powinout(k,4)
    if mode == QUINTIC_IN:
        return powin(k,5)
    if mode == QUINTIC_OUT:
        return powout(k,5)
    if mode == QUINTIC_INOUT:
        return powinout(k,5)
    if mode == SINUSOIDAL_IN:
        return 1-math.cos(k*(math.pi/2))
    if mode == SINUSOIDAL_OUT:
        return math.sin(k*(math.pi/2))
    if mode == SINUSOIDAL_INOUT:
        return -0.5*(math.cos(math.pi*k)-1)
    if mode == EXPONENTIAL_IN:
        return pow(2,10*(k-1))
    if mode == EXPONENTIAL_OUT:
        return (1-pow(2,-10*k))
    if mode == EXPONENTIAL_INOUT:
        k *= 2.
        if (k<1):
            return 0.5*pow(2,10*(k-1));
        k -= 1
        return 0.5*(2-pow(2,-10*k))
    if mode == CIRCULAR_IN:
        return -(math.sqrt(1-k*k)-1)
    if mode == CIRCULAR_OUT:
        k -= 1
        return math.sqrt(1-k*k)
    if mode == CIRCULAR_INOUT:
        k *= 2
        if (k<1):
            return -0.5*(math.sqrt(1-k*k)-1)
        k -= 2
        return 0.5*(math.sqrt(1-k*k)+1)
    if mode == ELASTIC_IN:
        k -= 1
        a = 1
        p = 0.3*1.5
        s = p*math.asin(1/a) / (2*math.pi);
        return -a*math.pow(2,10*k)*math.sin((k-s)*(2*math.pi)/p)
    if mode == ELASTIC_OUT:
        a = 1
        p = 0.3
        s = p*math.asin(1/a) / (2*math.pi);
        return (a*math.pow(2,-10*k)*math.sin((k-s)*(2*math.pi)/p)+1)
    if mode == ELASTIC_INOUT:
        k = k*2 - 1
        a = 1
        p = 0.3*1.5
        s = p*math.asin(1/a) / (2*math.pi)
        if ((k + 1) < 1):
            return -0.5*a*math.pow(2,10*k)*math.sin((k-s)*(2*math.pi)/p)
        return a*pow(2,-10*k)*math.sin((k-s)*(2*math.pi)/p)*0.5+1
    if mode == BACK_IN:
        s = 1.70158
        return k*k*((s+1)*k-s)
    if mode == BACK_OUT:
        k -= 1
        s = 1.70158
        return k*k*((s+1)*k+s)+1
    if mode == BACK_INOUT:
        k *= 2
        s = 1.70158
        s *= 1.525
        if (k < 1):
            return 0.5*k*k*((s+1)*k-s)
        k -= 2
        return 0.5*k*k*((s+1)*k+s)+1
    if mode == BOUNCE_IN:
        return 1-calc(1-k,BOUNCE_OUT)
    if mode == BOUNCE_OUT:
        if (k < (1/2.75)):
            return 7.5625*k*k
        if (k < (2/2.75)):
            k -= 1.5/2.75
            return 7.5625*k*k+0.75
        if (k < (2.5/2.75)):
            k -= (2.25/2.75)
            return 7.5625*k*k+0.9375
        k -= (2.625/2.75)
        return 7.5625*k*k+0.984375
    if mode == BOUNCE_INOUT:
        if (k < 0.5):
            return calc(k*2,BOUNCE_IN)*0.5
        return calc(k*2-1,BOUNCE_OUT)*0.5+0.5
    return k
        

pos = 0
t = time.time_ns()
def ramp(a, b, dur, mode):
    global pos, t
    dur *= 1000000000
    now = time.time_ns()
    delta = now - t
    t = now
    if pos + delta < dur:
        pos += delta
    else:
        pos = dur
    k = pos / dur
    print(f"delta={delta:f} k={k:.20f}")
    if b >= a:
        val = (a + (b-a)*calc(k,mode))
    else:
        val = (a - (a-b)*calc(k,mode))
    return val

if len(sys.argv) == 0:
    print("ramp_test.py <start> <end> <duration> <algorithm>")
    sys.exit(0)

a = float(sys.argv[1])
b = float(sys.argv[2])
d = float(sys.argv[3])
c = eval(f"{sys.argv[4].upper()}")

x = a
step = 1
while x != b:
    x = ramp(a, b, d, c)
    print(f"{int(time.time())}: temp {x:f}")
    step += 1
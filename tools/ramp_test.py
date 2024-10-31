#!/usr/bin/env python3
import math
import time
import argparse
import plotly.graph_objects as go

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

ALGOS = [
    'LINEAR',
    'QUADRATIC_IN',
    'QUADRATIC_OUT',
    'QUADRATIC_INOUT',
    'CUBIC_IN',
    'CUBIC_OUT',
    'CUBIC_INOUT',
    'QUARTIC_IN',
    'QUARTIC_OUT',
    'QUARTIC_INOUT',
    'QUINTIC_IN',
    'QUINTIC_OUT',
    'QUINTIC_INOUT',
    'SINUSOIDAL_IN',
    'SINUSOIDAL_OUT',
    'SINUSOIDAL_INOUT',
    'EXPONENTIAL_IN',
    'EXPONENTIAL_OUT',
    'EXPONENTIAL_INOUT',
    'CIRCULAR_IN',
    'CIRCULAR_OUT',
    'CIRCULAR_INOUT',
    'ELASTIC_IN',
    'ELASTIC_OUT',
    'ELASTIC_INOUT',
    'BACK_IN',
    'BACK_OUT',
    'BACK_INOUT',
    'BOUNCE_IN',
    'BOUNCE_OUT',
    'BOUNCE_INOUT',
]

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
        

class RampData:
    def __init__(self):
        self.p = 0
        self.t = 0
    @property
    def pos(self):
        return self.p
    @pos.setter
    def pos(self, value):
        self.p = value
    @property
    def delta(self):
        n = time.time()
        d = n - self.t
        self.t = n
        return d
    def reset(self):
        self.p = 0
        self.t = time.time()

def ramp(a, b, dur, mode, data):
    delta = data.delta
    if data.pos + delta < dur:
        data.pos += delta
    else:
        data.pos = dur
    k = data.pos / dur
    if b >= a:
        val = (a + (b-a)*calc(k,mode))
    else:
        val = (a - (a-b)*calc(k,mode))
    return val

def ramp_hybrid(a, b, c, dur, modes, ranges, data):
    print(c, ranges, modes)
    for i, r in enumerate(ranges):
        if c >= r[0] and c < r[1]:
            break
    mode = modes[i]
    print(mode, r)
    delta = data.delta
    if data.pos + delta < dur:
        data.pos += delta
    else:
        data.pos = dur
    k = data.pos / dur
    if b >= a:
        bp = ((b - a) * 0.8) + a
        val = (a + (b-a)*calc(k, mode))
    else:
        val = (a - (a-b)*calc(k, mode))
    return val

def make_graph(data):
    graph = go.Scatter(x=list(range(1, len(data)+1)),
                        y=data,
                       mode="lines")
    fig = go.Figure()
    fig.add_trace(graph)
    fig.update_layout(autosize=False, height=200, width=200,
                      margin={'autoexpand': False, 'l': 0, 'r': 0,
                              't': 0, 'b': 0})
    return fig

def output_graph(graphs, filename):
    prefix = """<html>
<head>
<style>
div.plotly-graph-top { display: inline-block; }
table { display: inline-block; vertical-align: top; }
th { text-align: left; background-color: #e4f0f5; }
th.title { text-align: center; background-color: #3f87a6; }
</style>
</head>
<body>"""
    suffix = "</body></html>"""

    with open(filename, 'w') as fd:
        fd.write(prefix)
        for algo in graphs:
            fd.write(f"<table><tr><th class='title'>{algo}</th></tr>")
            fd.write("<tr><td>")
            html = graphs[algo].to_html(full_html=False, include_plotlyjs=True)
            html = html.replace("<div>", "<div class=\"plotly-graph-top\">")
            fd.write(html)
            fd.write("</td></tr></table></div></div>")
        fd.write(suffix)

parser = argparse.ArgumentParser()
parser.add_argument("--graph", type=str, default=None,
                    help="""If present, it is the filename where
                    graphs will be generated""")
parser.add_argument("--algo", choices=ALGOS + ["ALL"], nargs="+",
                    help="Ramp algorithm")
parser.add_argument("--hybrid", default=None, type=str)
parser.add_argument("--breakpoints", type=int, nargs="*",
                    help="Breakpoint value for hybrid ramps.")
parser.add_argument("start", type=float, help="Start of ramp range")
parser.add_argument("end", type=float, help="End of ramp range")
parser.add_argument("duration", type=int, help="Ramp duration (in seconds)")

opts = parser.parse_args()

if opts.algo == ["ALL"]:
    opts.algo = ALGOS

if opts.hybrid:
    opts.algo = ["hybrid"]
values = {x: [] for x in opts.algo}
graphs = {x: None for x in opts.algo}
markers = "-\\|/"
ramp_data = RampData()
use_hybric = False
for algo in opts.algo:
    if opts.hybrid:
        algos = opts.hybrid.split(',')
        algosv = [eval(f"{x.upper()}") for x in algos]
        use_hybric = True
    else:
        algov = eval(f"{algo.upper()}")
    value = opts.start
    ramp_data.reset()
    while value != opts.end:
        print(f"Generating {algo.upper()} values... {markers[len(values[algo]) % len(markers)]}\r", end="")
        if use_hybric:
            assert len(algosv) == len(opts.breakpoints) + 1
            assert opts.breakpoints[0] > opts.start and opts.breakpoints[-1] < opts.end
            r = [opts.start] + opts.breakpoints + [opts.end]
            ranges = []
            for i in range(len(r) - 1):
                ranges.append((r[i], r[i+1] - 1))
            value = ramp_hybrid(opts.start, opts.end, value, opts.duration, algosv,
                                ranges, ramp_data)
        else:
            value = ramp(opts.start, opts.end, opts.duration, algov, ramp_data)
        values[algo].append(value)
        time.sleep(0.5)
    print()

    if opts.graph:
        graphs[algo] = make_graph(values[algo])

output_graph(graphs, opts.graph)
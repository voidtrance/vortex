#!/usr/bin/env python3
import sys
import time
import math
import argparse
from functools import reduce
from argparse import Namespace
from collections import namedtuple
import plotly.graph_objects as go

def make_graph(name, data):
    t_graph = go.Scatter(x=[x[0] for x in data],
                         y=[x[1] for x in data], mode="lines",
                         line_shape="spline",
                         name=name)
    return t_graph

def make_figure(graphs):
    layout = go.Layout(autosize=False, width=1800, height=1800,
                       xaxis=go.layout.XAxis(title="Time", linecolor="black", linewidth=1, mirror=True),
                       yaxis=go.layout.YAxis(title="Temperature", linecolor="black", linewidth=1, mirror=True),
                       margin=go.layout.Margin(l=50, r=50, b=100, t=100, pad=4))
    fig = go.Figure(graphs, layout=layout)
    return fig

def make_runtime(data):
    t_graph = go.Bar(x=[x[0] for x in data],
                     y=[x[1] for x in data])
    layout = go.Layout(autosize=False, width=1800, height=1800,
                       xaxis=go.layout.XAxis(title="Run", linecolor="black", linewidth=1, mirror=True),
                       yaxis=go.layout.YAxis(title="Time (ns)", linecolor="black", linewidth=1, mirror=True),
                       margin=go.layout.Margin(l=50, r=50, b=100, t=100, pad=4))
    fig = go.Figure(t_graph, layout=layout)
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
        for algo, figure in graphs.items():
            if not figure:
                continue
            fd.write(f"<table><tr><th class='title'>{algo}</th></tr>")
            fd.write("<tr><td>")
            html = figure.to_html(full_html=False, include_plotlyjs=True)
            html = html.replace("<div>", "<div class=\"plotly-graph-top\">")
            fd.write(html)
            fd.write("</td></tr></table></div></div>")
        fd.write(suffix)


Size = namedtuple("Size", ["x", "y", "z"])

class Layer:
    def __init__(self, density, capacity, conductivity, emissivity, covection, size, resolution):
        self.density = density
        self.capacity = capacity
        self.conductivity = conductivity
        self.emissivity = emissivity
        self.resolution = resolution
        self.convection_top, self.convection_bottom = covection
        self.size = Size._make([float(x) / 1000 for x in size.split(",")])
        self.elems = Size(int(round(self.size.x / resolution)) or 1,
                          int(round(self.size.y / resolution)) or 1, 0)
    
def elem(layer, x, y, z):
    return z * layer.elems.x * layer.elems.y + y * layer.elems.x + x

kSb = 0.0000000567
emisivity_compensation = 0.85

def compute(data, dt):
    for x in range(len(data.dqs)):
        data.dqs[x] = 0

    heater, bed = data.layers[:2]

    joules_per_iteration = data.power * dt
    joules_per_element = joules_per_iteration / (heater.elems.x * heater.elems.y)

    heaterStartX = math.floor((bed.elems.x - heater.elems.x) / 2)
    heaterStartY = math.floor((bed.elems.y - heater.elems.y) / 2)

    heaterEndX = heaterStartX + heater.elems.x
    heaterEndY = heaterStartY + heater.elems.y

    for y in range(bed.elems.y):
        for x in range(bed.elems.x):
            if x >= heaterStartX and x < heaterEndX and y >= heaterStartY and y < heaterEndY:
                data.dqs[elem(bed, x, y, 0)] = joules_per_element

    for l in range(len(data.layers)):
        for y in range(bed.elems.y):
            for x in range(bed.elems.x):
                idx = elem(bed, x, y, l)

                if x < bed.elems.x - 1:
                    idx_1 = elem(bed, x + 1, y, l)
                    dT = data.temp[idx] - data.temp[idx_1]
                    kH = data.layers[l].conductivity
                    A = data.layers[l].resolution * data.layers[l].size.z
                    dx = data.layers[l].resolution
                    dQ = kH * A * dT * dt / dx
                    data.dqs[idx] -= dQ
                    data.dqs[idx_1] += dQ

                if y < bed.elems.y - 1:
                    idx_1 = elem(bed, x, y + 1, l)
                    dT = data.temp[idx] - data.temp[idx_1]
                    kH = data.layers[l].conductivity
                    A = data.layers[l].resolution * data.layers[l].size.z
                    dx = data.layers[l].resolution
                    dQ = kH * A * dT * dt / dx
                    data.dqs[idx] -= dQ
                    data.dqs[idx_1] += dQ

                if l < len(data.layers) - 1:
                    idx_1 = elem(bed, x, y, l + 1)
                    dT = data.temp[idx] - data.temp[idx_1]
                    k1Inv = 0.5 * data.layers[l].size.z / data.layers[l].conductivity
                    k2Inv = 0.5 * data.layers[l + 1].size.z / data.layers[l + 1].conductivity
                    kH_dx = 1 / (k1Inv + k2Inv)
                    A = data.layers[l].resolution * data.layers[l].resolution
                    dQ = kH_dx * A * dT * dt
                    data.dqs[idx] -= dQ
                    data.dqs[idx_1] += dQ

    Ta4 = math.pow(data.ambient + 273, 4)

    # TOP
    for y in range(bed.elems.y):
        e = data.layers[-1].emissivity
        A = bed.resolution * bed.resolution

        for x in range(bed.elems.x):
            idx = elem(bed, x, y, len(data.layers) - 1)
            dTa = data.temp[idx] - data.ambient
            data.dqs[idx] -= bed.convection_top * A * dt * dTa
            data.dqs[idx] -= e * kSb * A * (math.pow(data.temp[idx] + 273, 4) - Ta4) * dt * emisivity_compensation

    # BOTTOM
    for y in range(bed.elems.y):
        e = heater.emissivity
        A = heater.resolution * heater.resolution

        for x in range(bed.elems.x):
            idx = elem(bed, x, y, 0)
            dTa = data.temp[idx] - data.ambient
            data.dqs[idx] -= bed.convection_bottom * A * dt * dTa
            data.dqs[idx] -= e * kSb * A * (math.pow(data.temp[idx] + 273, 4) - Ta4) * dt * emisivity_compensation

    # FRONT
    for l in range(len(data.layers)):
        e = data.layers[l].emissivity
        A = data.layers[l].resolution * data.layers[l].size.z

        for x in range(bed.elems.x):
            idx = elem(bed, x, 0, l)
            dTa = data.temp[idx] - data.ambient
            data.dqs[idx] -= bed.convection_top * A * dt * dTa
            data.dqs[idx] -= e * kSb * A * (math.pow(data.temp[idx] + 273, 4) - Ta4) * dt * emisivity_compensation

    # BACK
    for l in range(len(data.layers)):
        e = data.layers[l].emissivity
        A = data.layers[l].resolution * data.layers[l].size.z

        for x in range(bed.elems.x):
            idx = elem(bed, x, bed.elems.y - 1, l)
            dTa = data.temp[idx] - data.ambient
            data.dqs[idx] -= bed.convection_top * A * dt * dTa
            data.dqs[idx] -= e * kSb * A * (math.pow(data.temp[idx] + 273, 4) - Ta4) * dt * emisivity_compensation

    # LEFT
    for l in range(len(data.layers)):
        e = data.layers[l].emissivity
        A = data.layers[l].resolution * data.layers[l].size.z

        for y in range(bed.elems.y):
            idx = elem(bed, 0, y, l)
            dTa = data.temp[idx] - data.ambient
            data.dqs[idx] -= bed.convection_top * A * dt * dTa
            data.dqs[idx] -= e * kSb * A * (math.pow(data.temp[idx] + 273, 4) - Ta4) * dt * emisivity_compensation

    # RIGHT
    for l in range(len(data.layers)):
        e = data.layers[l].emissivity
        A = data.layers[l].resolution * data.layers[l].size.z

        for y in range(bed.elems.y):
            idx = elem(bed, bed.elems.x - 1, y, l)
            dTa = data.temp[idx] - data.ambient
            data.dqs[idx] -= bed.convection_top * A * dt * dTa
            data.dqs[idx] -= e * kSb * A * (math.pow(data.temp[idx] + 273, 4) - Ta4) * dt * emisivity_compensation

    for l in range(len(data.layers)):
        c = data.layers[l].capacity * data.layers[l].density * data.layers[l].resolution * data.layers[l].resolution * data.layers[l].size.z
        for y in range(bed.elems.y):
            for x in range(bed.elems.x):
                idx = elem(bed, x, y, l)
                data.temp[idx] += data.dqs[idx] / c

    return

def parse_compare(fd, ambient):
    temp_data = []
    prev_temp = -1
    run_start = 0
    run_end = 0
    for line in fd:
        parts = [x.strip() for x in line.split(":")]
        if len(parts) == 3:
            parts = parts[1:]
        timestamp, temp = parts
        try:
            timestamp = int(timestamp)
            sec_time = timestamp / 1000000000
        except ValueError:
            sec_time = float(timestamp)
        temp = round(float(temp), 3)
        run_end = sec_time
        if not run_start:
            run_start = run_end
        if temp != prev_temp:
            temp_data.append((sec_time, temp))
            prev_temp = temp
    return temp_data, run_end - run_start

def parse_convection(value):
    try:
        top, bottom = [float(x) for x in value.split(",")]
    except:
        return [-1,-1]
    return [top, bottom]

def create_layers(args):
    convection = parse_convection(args.convection)
    if convection[0] == -1:
        print("Invalid convection value")
        sys.exit(1)

    return [Layer(1100000, 0.9, args.heater_conductivity, 0.9, [0, 0], args.heater, args.resolution),
            Layer(2650000, 0.9, args.bed_conductivity, 0.2, convection, args.bed, args.resolution),
            Layer(3700000, 0.9, 0.25, 0.9, [0,0], ",".join(args.bed.split(",")[:2] + ["1.2"]), args.resolution),
            Layer(5500000, 0.6, 0.6, 0.9, [0,0], ",".join(args.bed.split(",")[:2] + ["0.75"]), args.resolution)]

def run_simulation(args):
    data = Namespace()
    data.layers = create_layers(args)
    data.power = args.power
    data.ambient = args.ambient
    data.dqs = [0] * (data.layers[1].elems.x * data.layers[1].elems.y * len(data.layers))
    data.temp = [data.ambient] * len(data.dqs)
    data.sensor = Namespace()
    sensor_coords = [data.layers[1].size.x / 2,
                     data.layers[1].size.y / 2,
                     reduce(lambda x, y: x + y.size.z, data.layers, 0) / 2]
    height = 0
    for idx in range(len(data.layers)):
        height += data.layers[idx].size.z
        if sensor_coords[2] < height:
            break
    sensor_coords = [sensor_coords[0] / args.resolution, sensor_coords[1] / args.resolution, idx]
    sensor_coords = map(int, sensor_coords)
    data.sensor = Size._make(sensor_coords)

    if args.runtime == 0.:
        args.runtime = 10 * 100

    sensor_elem = elem(data.layers[1], data.sensor.x, data.sensor.y, data.sensor.z)
    temps = []
    timer = 0
    timestep = 1
    iter_per_step = 25
    start = time.time_ns()
    time_delta = timestep / iter_per_step
    while timer < args.runtime:
        for i in range(iter_per_step):
            compute(data, time_delta)
            temps.append((timer + i * time_delta, data.temp[sensor_elem]))
        timer += 1
    if args.down:
        data.power = 0
        while timer < args.runtime * 2:
            for i in range(iter_per_step):
                compute(data, time_delta)
                temps.append((timer + i * time_delta, data.temp[sensor_elem]))
            timer += 1
    end = time.time_ns()
    return temps, end - start

def create_graph_name(args):
    return f"power={args.power},ambient={args.ambient},\n" + \
        f"convection={args.convection},bed-conductivity={args.bed_conductivity},\n" + \
        f"heater-conductivity={args.heater_conductivity},resolution={args.resolution}"

parser = argparse.ArgumentParser()
parser.add_argument("--compare", type=argparse.FileType("r"),
                    help="When comparing temperatures, the file containting the data")
parser.add_argument("--commands", type=argparse.FileType("r"),
                    help="File containing list of arguments")
parser.add_argument("--output", type=str, default="temp_graphs.html",
                    help="Output graph filename.")
parser.add_argument("--bed", type=str, default=None,
                    help="Bed size (in mm): <width>,<depth>,<height>")
parser.add_argument("--power", type=float, default=None,
                    help="Heater power in watts")
parser.add_argument("--resolution", type=float, default=0.005,
                    help="Element resolution")
parser.add_argument("--heater", type=str, default=None,
                    help="The size of the heater. Format is same as --bed.")
parser.add_argument("--ambient", type=float, default=25.0,
                    help="Ambient temperature. Default is 25C")
parser.add_argument("--runtime", type=float, default=0.0,
                    help="""Simulation runtime in seconds. If comparing, the
                    runtime will be computed based on the runtime in the file.""")
parser.add_argument("--down", action="store_true",
                    help="""If set, the simulation's power will be set to 0 half way
                    through the runtime.""")
sim_params = parser.add_argument_group("Simulation parameters")
sim_params.add_argument("--convection", type=str, default="8,4",
                        help="Bed convection values")
sim_params.add_argument("--bed-conductivity", type=float, default=120,
                        help="Bed thermal conductivity")
sim_params.add_argument("--heater-conductivity", type=float, default=0.3,
                        help="Heater thermal conductivity")
args = parser.parse_args()

graphs = []
runtimes = []
figure_runtime = None
if args.commands:
    for line in args.commands:
        print(f"Simulation parameters: {line.strip()}")
        args = parser.parse_args(line.split())
        temps, duration = run_simulation(args)
        graphs.append(make_graph(create_graph_name(args), temps))
        runtimes.append((create_graph_name(args), duration))
    figure = make_figure(graphs)
    figure_runtime = make_runtime(runtimes)
else:
    if not args.bed or not args.power or not args.heater:
        print("Arguments '--bed', '--heater', and '--power' are required")
        sys.exit(1)
    comp_temps = None
    if args.compare:
        comp_temps, args.runtime = parse_compare(args.compare, args.ambient)
        print(f"Simulating {args.runtime} seconds")
        graphs.append(make_graph("Compare", comp_temps))
    temps, _ = run_simulation(args)
    graphs.append(make_graph("Simulation", temps))
    figure = make_figure(graphs)

output_graph({"Heater Simulation": figure, "Runtimes": figure_runtime}, args.output)

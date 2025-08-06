#!/usr/bin/env python3
# vortex - GCode machine emulator
# Copyright (C) 2024-2025 Mitko Haralanov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import sys
import time
import math
import errno
import argparse
from functools import reduce
from argparse import Namespace
from collections import namedtuple
from vortex.emulator import config
from vortex.core import ObjectKlass
import plotly.graph_objects as go

SIMULATION_RESOLUTION = 0.005
AMBIENT_TEMP = 25.0

kSb = 0.0000000567
emisivity_compensation = 0.85

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
        self.size = Size._make([x / 1000 for x in size])
        self.elems = Size(int(round(self.size.x / resolution)) or 1,
                          int(round(self.size.y / resolution)) or 1, 0)
    
def elem(layer, x, y, z):
    return z * layer.elems.x * layer.elems.y + y * layer.elems.x + x

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

def create_layers(config):
    hls = []
    for i in range(1, 1000):
        if not hasattr(config, f"layers_{i}_type"):
            break
        l = Layer(int(getattr(config, f"layers_{i}_density")),
                  float(getattr(config, f"layers_{i}_capacity")),
                  float(getattr(config, f"layers_{i}_conductivity")),
                  float(getattr(config, f"layers_{i}_emissivity")),
                  parse_convection(getattr(config, f"layers_{i}_convection")),
                  getattr(config, f"layers_{i}_size"),
                  SIMULATION_RESOLUTION)
        ltype = int(getattr(config, f"layers_{i}_type"))
        if ltype != 3:
            hls.insert(ltype, l)
        else:
            hls.append(l)
    return hls

def create_simulation_data(config):
    data = Namespace()
    data.layers = create_layers(config)
    data.max_power = config.power
    data.power = 0
    data.ambient = AMBIENT_TEMP
    data.iter_per_step = 25
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
    sensor_coords = [sensor_coords[0] / SIMULATION_RESOLUTION,
                     sensor_coords[1] / SIMULATION_RESOLUTION, idx]
    sensor_coords = map(int, sensor_coords)
    data.sensor = Size._make(sensor_coords)
    data.sensor_elem = elem(data.layers[1], data.sensor.x, data.sensor.y, data.sensor.z)
    return data

def reset_simulation_data(data):
    data.dqs = [0] * (data.layers[1].elems.x * data.layers[1].elems.y * len(data.layers))
    data.temp = [data.ambient] * len(data.dqs)

def run_simulation(data, runtime, down):
    if runtime == 0.:
        runtime = 10 * 100

    temps = []
    timer = 0
    timestep = 1
    start = time.time_ns()
    time_delta = timestep / data.iter_per_step
    while timer < runtime:
        for i in range(data.iter_per_step):
            compute(data, time_delta)
            temps.append((timer + i * time_delta, data.temp[data.sensor_elem]))
        timer += 1
    if down:
        data.power = 0
        while timer < runtime * 2:
            for i in range(data.iter_per_step):
                compute(data, time_delta)
                temps.append((timer + i * time_delta, data.temp[data.sensor_elem]))
            timer += 1
    end = time.time_ns()
    return temps, end - start

def create_graph_name(args):
    return f"power={args.power},ambient={args.ambient},\n" + \
        f"convection={args.convection},bed-conductivity={args.bed_conductivity},\n" + \
        f"heater-conductivity={args.heater_conductivity},resolution={args.resolution}"

def tune_pid(data, setpoint, steps=10):
    """Tune PID values using grid search."""
    get_temp = lambda d: d.temp[d.sensor_elem]

    ranges_top = []
    ranges_bottom = []
    sim_time = 0
    time_delta = 1. / data.iter_per_step
    for i in range(steps):
        data.power = data.max_power
        current_temp = get_temp(data)
        done_heating = False
        peak = 0
        while current_temp < setpoint:
            for i in range(data.iter_per_step):
                compute(data, time_delta)
                sim_time += time_delta
                current_temp = get_temp(data)
                if current_temp >= setpoint:
                    peak = current_temp
                    break
        data.power = 0
        while not done_heating:
            for i in range(data.iter_per_step):
                compute(data, time_delta)
                sim_time += time_delta
                current_temp = get_temp(data)
                if current_temp > peak:
                    peak = current_temp
                else:
                    done_heating = True
                    break
            if done_heating:
                ranges_top.append((peak, sim_time))
                break
        while current_temp >= setpoint - 5:
            for i in range(data.iter_per_step):
                compute(data, time_delta)
                sim_time += time_delta
                current_temp = get_temp(data)
                if current_temp <= setpoint - 5:
                    ranges_bottom.append((current_temp, sim_time))
                    break
    cycles = [(ranges_top[p][1] - ranges_top[p-1][1], p) \
              for p in range(1, len(ranges_top))]
    mid = sorted(cycles)[len(cycles)//2][1]
    temp_diff = ranges_top[mid][0] - ranges_bottom[mid][0]
    time_diff = ranges_top[mid][1] - ranges_top[mid-1][1]
    amplitude = .5 * abs(temp_diff)
    Ku = 4. / (math.pi * amplitude)
    Tu = time_diff
    Ti = 0.5 * Tu
    Td = 0.125 * Tu
    Kp = 0.6 * Ku * 255
    Ki = Kp / Ti
    Kd = Kp * Td
    return Kp, Ki, Kd

def pid_update(pid, target, current, dt):
    error = target - current
    pid.integral += error * dt

    pid.integral = min(pid.integral, pid.output_max)
    pid.integral = max(pid.integral, pid.output_min)

    derivative = (error - pid.prev_error) / dt
    output = pid.kp * error + pid.ki * pid.integral + pid.kd * derivative;

    output = min(output, pid.output_max)
    output = max(output, pid.output_min)

    pid.prev_error = error
    return output

def run_pid_simulation(data, runtime, target, kp, ki, kd):
    if runtime == 0.:
        runtime = 10 * 100

    pid = Namespace()
    pid.kp = kp
    pid.ki = ki
    pid.kd = kd
    pid.prev_error = 0.
    pid.integral = 0.
    pid.output_min = 0.
    pid.output_max = 1.

    temps = []
    timer = 0
    start = time.time_ns()
    time_delta = 1 / data.iter_per_step
    get_temp = lambda d: d.temp[d.sensor_elem]
    while timer < runtime:
        for i in range(data.iter_per_step):
            temp = get_temp(data)
            data.power = data.max_power * pid_update(pid, target, temp, time_delta)
            compute(data, time_delta)
            temps.append((timer + i * time_delta, get_temp(data)))
        timer += 1
    end = time.time_ns()
    return temps, end - start

def parse_pid_pair(value):
    min_val, max_val = [float(x.strip()) for x in value.split(",")]
    return min_val, max_val

def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-C", dest="config", type=str, required=True,
                        help="""Emulator configuration file. This option is
                        required so heater settings can be read.""")
    parser.add_argument("--heater", action="append", default=[],
                         help="""Heater name to work with. If not specified
                         the tool will use all heaters in the configuration
                         file.""")
    parser.add_argument("--compare", type=argparse.FileType("r"),
                        help="""With this option, the tool will compare temperatures
                        read from a file with temperatures simulated based on 
                        configuration file values. This is useful for verifying
                        heater behavior in the emulation. A graph with both curves
                        will be generated""")
    parser.add_argument("--output", type=str, default="temp_graphs.html",
                        help="Output graph filename.")
    parser.add_argument("--runtime", type=float, default=0.0,
                        help="""Simulation runtime in seconds. If comparing, the
                        runtime will be computed based on the runtime in the file.""")
    parser.add_argument("--down", action="store_true",
                        help="""If set, the simulation's power will be set to 0 half way
                        through the runtime.""")
    pid_params = parser.add_argument_group("PID tuning parameters")
    parser.add_argument("--pid-tune", action="store_true", dest="tune_pid",
                                     help="Run PID tuning cycles and generate PID values.")
    pid_params.add_argument("--target", type=float, default=60,
                            help="Target temperature for PID tuning.")
    pid_params.add_argument("--steps", type=int, default=5, help="Cycle count")
    pid_run_params = parser.add_argument_group("PID control parameters")
    pid_run_params.add_argument("--pid-control", action="store_true",
                                help="""Run PID control test. This will simulate heater
                                behavior based on PID control values.""")
    pid_run_params.add_argument("--temp", type=float,
                                help="Temperate target to be maintained by the PID controller.")
    pid_run_params.add_argument("--kp", type=float,
                                 help="""PID control KP value. If this value is given, it will
                                 override the value in the configuration file.""")
    pid_run_params.add_argument("--ki", type=float,
                                 help="""PID control KI value. If this value is given, it will
                                 override the value in the configuration file.""")
    pid_run_params.add_argument("--kd", type=float,
                                help="""PID control KD value. If this value is given it will
                                override the value in the configuration file.""")
    return parser

def main():
    parser = create_parser()
    args = parser.parse_args()

    conf = config.Configuration()
    conf.read(args.config)

    if not args.heater:
        args.heater = [name for klass, name, c in conf if klass == ObjectKlass.HEATER]

    heaters = args.heater[:]
    for heater in heaters:
        if f"{str(ObjectKlass.HEATER).lower()} {heater}" not in conf:
            print(f"ERROR: Heater '{heater}' not found")
            args.heater.remove(heater)

    for heater in args.heater:
        c = conf.get_section(ObjectKlass.HEATER, heater)
        output = f"{heater}-{args.output}"
        sim_data = create_simulation_data(c)
        graphs = []
        if args.tune_pid:
            if not args.target:
                print(f"ERROR: '--target' is required for PID tunning")
                return errno.EINVAL
            if args.target > c.max_temp:
                print(f"ERROR: PID tune target temperature exceed maximum heater temperature")
            print(f"Running PID tuning for heater '{heater}...")
            params = tune_pid(sim_data, args.target, args.steps)
            print(f"{heater} PID: Kp: {params[0]}, Ki: {params[1]}, Kd: {params[2]}")
        elif args.pid_control:
            if not args.temp:
                print(f"ERROR: '--temp' is required for PID control")
                return errno.EINVAL
            if args.temp > c.max_temp:
                print(f"ERROR: Target temperature exceed maximum heater temperature")
            kp = args.kp if args.kp is not None else c.kp
            ki = args.ki if args.ki is not None else c.ki
            kd = args.kd if args.kd is not None else c.kd
            temps, _ = run_pid_simulation(sim_data, args.runtime, args.temp,
                                          kp, ki, kd)
            graphs.append(make_graph("PID Simulation", temps))
            figure = make_figure(graphs)
            output_graph({f"Heater PID Control Simulation - {heater}": figure}, output)
        else:
            comp_temps = None
            if args.compare:
                comp_temps, args.runtime = parse_compare(args.compare, AMBIENT_TEMP)
                print(f"Simulating {args.runtime} seconds")
                graphs.append(make_graph("Compare", comp_temps))
            else:
                sim_data.power = sim_data.max_power
                temps, _ = run_simulation(sim_data, args.runtime, args.down)
                graphs.append(make_graph("Simulation", temps))
                figure = make_figure(graphs)
            output_graph({f"Heater Simulation - {heater}": figure}, output)

    return 0

sys.exit(main())
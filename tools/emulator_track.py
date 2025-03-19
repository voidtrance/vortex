#!/usr/bin/env python3
# vortex - GCode machine emulator
# Copyright (C) 2024-2025  Mitko Haralanov
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
import csv
import time
import socket
import pickle
import argparse
import threading
import plotly.graph_objects as go
from dash import Dash, dcc, html, set_props
from dash.dependencies import Input, Output
from vortex.controllers.types import ModuleTypes
import collections
from weakref import proxy

class Link(object):
    __slots__ = 'prev', 'next', 'key', '__weakref__'

class OrderedSet(collections.abc.MutableSet):
    'Set the remembers the order elements were added'
    # Big-O running times for all methods are the same as for regular sets.
    # The internal self.__map dictionary maps keys to links in a doubly linked list.
    # The circular doubly linked list starts and ends with a sentinel element.
    # The sentinel element never gets deleted (this simplifies the algorithm).
    # The prev/next links are weakref proxies (to prevent circular references).
    # Individual links are kept alive by the hard reference in self.__map.
    # Those hard references disappear when a key is deleted from an OrderedSet.

    def __init__(self, iterable=None):
        self.__root = root = Link()         # sentinel node for doubly linked list
        root.prev = root.next = root
        self.__map = {}                     # key --> link
        if iterable is not None:
            self |= iterable

    def __len__(self):
        return len(self.__map)

    def __contains__(self, key):
        return key in self.__map

    def add(self, key):
        # Store new key in a new link at the end of the linked list
        if key not in self.__map:
            self.__map[key] = link = Link()            
            root = self.__root
            last = root.prev
            link.prev, link.next, link.key = last, root, key
            last.next = root.prev = proxy(link)

    def discard(self, key):
        # Remove an existing item using self.__map to find the link which is
        # then removed by updating the links in the predecessor and successors.        
        if key in self.__map:        
            link = self.__map.pop(key)
            link.prev.next = link.next
            link.next.prev = link.prev

    def __iter__(self):
        # Traverse the linked list in order.
        root = self.__root
        curr = root.next
        while curr is not root:
            yield curr.key
            curr = curr.next

    def __reversed__(self):
        # Traverse the linked list in reverse order.
        root = self.__root
        curr = root.prev
        while curr is not root:
            yield curr.key
            curr = curr.prev

    def pop(self, last=True):
        if not self:
            raise KeyError('set is empty')
        key = next(reversed(self)) if last else next(iter(self))
        self.discard(key)
        return key

    def __repr__(self):
        if not self:
            return '%s()' % (self.__class__.__name__,)
        return '%s(%r)' % (self.__class__.__name__, list(self))

socket_path = "/tmp/vortex_monitor"

def connect(path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except (FileNotFoundError, ConnectionRefusedError):
        return None
    return sock

def get(conn, request):
    conn.sendall(pickle.dumps(request))
    data = conn.recv(8192)
    return pickle.loads(data)

def get_toolhead_id(conn):
    response = get(conn, {"request" : "object_list"})
    toolheads = response["objects"][ModuleTypes.TOOLHEAD]
    if len(toolheads) > 1:
        return 0
    return toolheads[0]["id"]

def get_heaters_id(conn):
    response = get(conn, {"request" : "object_list"})
    heaters = response["objects"][ModuleTypes.HEATER]
    return [x["id"] for x in heaters]

def get_objects(conn, *args):
    return get(conn, {"request": "query", "objects": list(args)})

def get_data(conn, toolhead, *heaters):
    state = get_objects(conn, toolhead, *heaters)
    idxs = [i for i in state[toolhead]["axes"] if i != 7]
    pos = [state[toolhead]["position"][i] for i in idxs]
    temps = dict.fromkeys(heaters, 0.)
    for h in heaters:
        temps[h] = state[h]["temperature"]
    return pos, temps

def draw(filename, data, times, heaters):
    x = [x[0] for x in data]
    y = [x[1] for x in data]
    z = [x[2] for x in data]
    g = go.Scatter3d(name="shape", mode="lines", x=x, y=y, z=z)
    l = go.Layout(autosize=False, width=1800, height=1800,
                  margin=go.layout.Margin(l=50, r=50, b=100, t=100, pad=4))
    fig = go.Figure(g, layout=l)

    tfig = go.Figure()
    for h in heaters:
        t = go.Scatter(x=times, y=heaters[h], mode="lines", line_shape="spline", name=f"heater {h}")
        tfig.add_trace(t)

    prefix = """<html>
<head>
<style>
div.plotly-graph-top { display: inline-block; }
table { display: inline-block; vertical-align: top; }
th { text-align: left; background-color: #e4f0f5; }
th.title { text-align: center; background-color: #3f87a6; }
</style>
</head>
<body>
<table>"""
    suffix = "</table></body></html>"""

    filename.write(prefix)
    filename.write("<tr><th class='title'>Toolhead trace</th></tr><tr><td>")
    html = fig.to_html(full_html=False, include_plotlyjs=True)
    html = html.replace("<div>", "<div class=\"plotly-graph-top\">")
    filename.write(html)
    filename.write("</td></tr>")
    filename.write("<tr><th class='title'>Heater Temps</th></tr><tr><td>")
    html = tfig.to_html(full_html=False, include_plotlyjs=False)
    html = html.replace("<div>", "<div class=\"plotly-graph-top\">")
    filename.write(html)
    filename.write("</td></tr>")
    filename.write(suffix)

def run_dash_server(connection, toolhead, *heaters):
    def stop_app(err):
        set_props('interval-component', dict(disabled=True))
        set_props('temp-interval-component', dict(disabled=True))

    app = Dash("Emulator Trace", on_error=stop_app)

    g = go.Scatter3d(name="shape", mode="lines", x=[], y=[], z=[])
    l = go.Layout(autosize=False, width=1800, height=1800,
                    margin=go.layout.Margin(l=50, r=50, b=100, t=100, pad=4))
    fig = go.Figure(g, layout=l)
    
    tfig = go.Figure()
    for h in heaters:
        t = go.Scatter(x=[], y=[], mode="lines", line_shape="spline", name=f"heater {h}")
        tfig.add_trace(t)

    app.layout = html.Div([
        html.Div([
            html.Button('Stop Refresh', id='refresh-control', n_clicks=0)
        ], title="Refresh Control"),
        html.Div([
            dcc.Graph(id="travel-plot", figure=fig),
            dcc.Interval(id="interval-component", interval=40, n_intervals=0)
        ]),
        html.Div([
            dcc.Graph(id="heater-temps", figure=tfig),
            dcc.Interval(id="temp-interval-component", interval=1000, n_intervals=0)
        ])
    ])

    start_time = time.time()

    @app.callback(Output('travel-plot', 'extendData'),
                  Input('interval-component', 'n_intervals'))
    def update_path_data(n):
        pos, temps = get_data(connection, toolhead, *heaters)
        print(f"X={pos[0]}, Y={pos[1]}, Z={pos[2]}")
        data = {'x':[[pos[0]]], 'y': [[pos[1]]], 'z': [[pos[2]]]}
        return data

    @app.callback(Output('heater-temps', 'extendData'),
                  Input('interval-component', 'n_intervals'))
    def update_temp_data(n):
        pos, temps = get_data(connection, toolhead, *heaters)
        runtime = round(time.time() - start_time, 3)
        runtime = time.strftime("%H:%M:%S", time.localtime(runtime))
        data = {'x': [[runtime], [runtime]], 'y':[[temps[h]] for h in heaters]}
        return data, [0, 1], 100
    
    @app.callback(Output('interval-component', 'disabled'),
                  Output('refresh-control', 'children'),
                  Input('refresh-control', 'n_clicks'))
    def refresh_control(n_clicks):
        stop = bool(n_clicks & 1)
        return stop, f"{'Start' if stop else 'Stop'} Refresh"
    
    app.run(debug=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=argparse.FileType('w'),
                        default="toolhead_graph.html",
                        help="Graph filename")
    parser.add_argument("--csv", type=argparse.FileType('w'),
                        default=None,
                        help="Output file for toolhead coordinates")
    parser.add_argument("--data", type=argparse.FileType('r'),
                        default=None, help="Toolhead coordinates data")
    parser.add_argument("--real-time", action="store_true",
                        help="Create dynamic graph")
    args = parser.parse_args()

    positions = []
    timestamps = []
    if args.data is None:
        connection = connect(socket_path)
        if connection is None:
            print("Could not connect to emulator socket.")
            return -1

        id = get_toolhead_id(connection)
        print(f"Toolhead ID: {id}")
        if id == 0:
            return -1

        heater_ids = get_heaters_id(connection)
        print(f"Heaters: {", ".join([str(h) for h in heater_ids])}")
    
    if args.real_time:
        run_dash_server(connection, id, *heater_ids)
        return 0

    if args.data is None:
        heaters = {x: [] for x in heater_ids}
        while True:
            try:
                timestamps.append(time.time())
                position, temps = get_data(connection, id, *heater_ids)
                positions.append(position)
                for h in heater_ids:
                    heaters[h].append(temps[h])
                time.sleep(0.02)
            except KeyboardInterrupt:
                break
            except BrokenPipeError:
                print("Emulator socket closed remotely.", file=sys.stderr)
                break

        if args.csv:
            c = csv.writer(args.csv)
            for i, p in enumerate(positions):
                for h in heater_ids:
                    p.append(heaters[h][i])
                c.writerow(p)
            args.csv.close()
    else:
        c = csv.reader(args.data)
        positions = [x for x in c]
        args.data.close()
    draw(args.graph, positions, timestamps, heaters)
    args.graph.close()
    return 0

sys.exit(main())
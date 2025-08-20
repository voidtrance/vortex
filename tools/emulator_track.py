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
import plotly.graph_objects as go
from dash import Dash, dcc, html, set_props, Patch
from dash.dependencies import Input, Output
from vortex.core import ObjectKlass
import vortex.emulator.remote.api as api
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

socket_path = "/tmp/vortex-remote"

def connect(path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except (FileNotFoundError, ConnectionRefusedError):
        return None
    return sock

def get(conn, request):
    conn.sendall(pickle.dumps(request))
    data = b""
    incoming = conn.recv(8192)
    while incoming:
        data += incoming
        try:
            incoming = conn.recv(1024, socket.MSG_DONTWAIT)
        except BlockingIOError:
            break
    return pickle.loads(data)

def get_object_ids(conn, klass):
    request = api.Request(api.RequestType.OBJECT_LIST)
    response = get(conn, request)
    if klass not in response.data:
        return []
    objects = response.data[klass]
    return [(x["id"], x["name"]) for x in objects]

def get_object_status(conn, *args):
    request = api.Request(api.RequestType.OBJECT_STATUS)
    request.objects = list(args)
    response = get(conn, request)
    return response.data

def get_data(conn, objects, properties={}):
    data = {k: {} for k in properties.keys()}
    for klass in properties:
        if not objects[klass]:
            continue
        state = get_object_status(conn, *[x[0] for x in objects[klass]])
        for obj_id, obj_name in objects[klass]:
            if not properties[klass]:
                data[klass][obj_id] = state[obj_id]
            else:
                data[klass][obj_id] = {k: v for k, v in state[obj_id].items() if k in properties[klass]}
            if klass == ObjectKlass.TOOLHEAD and "position" in properties[klass]:
                idxs = [i for i, axis in enumerate(state[obj_id]["axes"]) if axis != 7]
                pos = [state[obj_id]["position"][i] for i in idxs]
                data[klass][obj_id]["position"] = pos
    return data

def draw(filename, properties, objects, data, timestamps):
    layout_3d = go.Layout(autosize=False, width=1800, height=1800,
                                  margin=go.layout.Margin(l=50, r=50, b=100, t=100, pad=4))
    layout = go.Layout(autosize=False, width=1800, height=300)
    figures = {}
    for klass in properties:
        figures[klass] = {}
        for obj_id in objects[klass]:
            figures[klass][obj_id] = {p: None for p in properties[klass]}
    for klass in properties:
        for property in properties[klass]:
            fig = go.Figure(layout=(layout_3d if klass == ObjectKlass.TOOLHEAD and \
                                    property == "position" else layout))
            figures[klass][property] = fig
            for obj_id, obj_name in objects[klass]:
                data_set = [d[klass][obj_id][property] for d in data]
                #print(data_set)

                if klass == ObjectKlass.TOOLHEAD and property == "position":
                    x = [x[0] for x in data_set]
                    y = [x[1] for x in data_set]
                    z = [x[2] for x in data_set]
                    g = go.Scatter3d(name=f"Toolhead {obj_name}", mode="lines", x=x, y=y, z=z)
                    fig.add_trace(g)
                else:
                    t = go.Scatter(x=timestamps, y=data_set, mode="lines", line_shape="spline",
                                   name=f"{str(klass).capitalize()} {obj_name}")
                    fig.add_trace(t)

    prefix = """<html>
<head>
<style>
div.plotly-graph-top { display: inline-block; border: 1px solid #3f87a6; }
table { display: inline-block; vertical-align: top; }
th { text-align: left; background-color: #e4f0f5; }
th.title { text-align: center; background-color: #3f87a6; font-size: 16px;}
th.subtitle {text-align: center; background-color: lightblue; font-size: 12px;}
</style>
</head>
<body>
<table>"""
    suffix = "</table></body></html>"""

    include = True
    filename.write(prefix)
    for klass in properties:
        filename.write(f"<tr><th class='title'>{str(klass).capitalize()} Traces</th></tr>\n")
        for property in properties[klass]:
            filename.write(f"<tr><th class='subtitle'>{property.capitalize()}</th></tr>\n")
            filename.write("<tr><td>\n")
            fig = figures[klass][property]
            html = fig.to_html(full_html=False, include_plotlyjs=include)
            include = False
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
    
    l = go.Layout(autosize=False, width=1800, height=300)
    tfig = go.Figure(layout=l)
    for h in heaters:
        t = go.Scatter(x=[], y=[], mode="lines", name=f"heater {h}")
        tfig.add_trace(t)
    tfig.update_xaxes(tickformat="%H:%M:%S")

    app.layout = html.Div([
        html.Div([
            html.Button('Stop Refresh', id='refresh-control', n_clicks=0),
        ], title="Refresh Control"),
        html.Div(["Toolhead Tracking"], id='toolhead-tracking',
                 style={'fontSize': 18, 'textAlign': 'center',
                        'backgroundColor': '#3f87a6', 'width': '1802px',
                        'margin-top': '10px'}),
        html.Div([
            dcc.Graph(id="travel-plot", figure=fig),
            dcc.Interval(id="interval-component", interval=40, n_intervals=0)
        ],
        style={'border': '1px solid #3f87a6', 'display': 'inline-block'}),
        html.Div(["Heater Tracking"], id='heater-tracking',
                 style={'fontSize': 18, 'textAlign': 'center',
                        'backgroundColor': '#3f87a6', 'width': '1802px',
                        'margin-top': '10px'}),
        html.Div([
            dcc.Graph(id="heater-temps", figure=tfig),
            dcc.Interval(id="temp-interval-component", interval=1000, n_intervals=0)
        ],
        style={'border': '1px solid #3f87a6', 'display': 'inline-block'}),
    ])

    start_time = time.time()

    @app.callback(Output('travel-plot', 'extendData'),
                  Input('interval-component', 'n_intervals'))
    def update_path_data(n):
        pos, temps = get_data(connection, toolhead, *heaters)
        data = {'x':[[pos[0]]], 'y': [[pos[1]]], 'z': [[pos[2]]]}
        return data

    @app.callback(Output('heater-temps', 'extendData'),
                  Input('interval-component', 'n_intervals'))
    def update_temp_data(n):
        pos, temps = get_data(connection, toolhead, *heaters)
        runtime = round(time.time() - start_time, 3)
        millis = int((runtime - int(runtime)) * 1000)
        runtime = time.strftime("%H:%M:%S", time.localtime(runtime))
        # Combine formatted time with milliseconds
        formatted_runtime = f"1900-01-01 {runtime}.{millis:03d}"
        data = {'x': [[formatted_runtime], [formatted_runtime]], 'y':[[temps[h]] for h in heaters]}
        return (data, [0, 1], 10000)
    
    @app.callback(Output('interval-component', 'disabled'),
                  Output('refresh-control', 'children'),
                  Input('refresh-control', 'n_clicks'))
    def refresh_control(n_clicks):
        stop = bool(n_clicks & 1)
        return stop, f"{'Start' if stop else 'Stop'} Refresh"
    
    app.run(debug=True)

def object_track_param(value):
    try:
        klass, properties = value.split(":")
    except ValueError:
        klass, properties = value, ""

    klass = klass.lower()
    if klass == "all" and properties:
        raise argparse.ArgumentTypeError("cannot use properties when tracking all klasses.")

    properties = [x.lower() for x in properties.split(",")]
    return klass, properties

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
    parser.add_argument("--track", type=object_track_param, action="extend",
                        nargs="+",
                        default=[("toolhead", ["position"]), ("heater", ["temperature"])],
                        help="<klass>[:<property>[,<property>]]")
    args = parser.parse_args()

    properties = {ObjectKlass[klass.upper()]: p for klass, p in args.track}
    objects = dict.fromkeys(ObjectKlass, [])

    if args.data is None:
        connection = connect(socket_path)
        if connection is None:
            print("Could not connect to emulator socket.")
            return -1

        for klass in properties:
            objects[klass] = get_object_ids(connection, klass)
            print(f"Objects ({str(klass)}): {' '.join([x[1] for x in objects[klass]])}")
    
    if args.real_time:
        run_dash_server(connection, objects, properties)
        return 0

    track_data = {}
    if args.data is None:
        while True:
            try:
                track_data[time.time()] = get_data(connection, objects, properties)
                time.sleep(0.02)
            except KeyboardInterrupt:
                break
            except BrokenPipeError:
                print("Emulator socket closed remotely.", file=sys.stderr)
                break

        if args.csv:
            c = csv.writer(args.csv)
            for data_set in track_data:
                c.writerow(data_set)
            args.csv.close()
    else:
        c = csv.reader(args.data)
        for row in c:
            track_data[row[0]] = row[1:]
        args.data.close()

    #print(track_data)
    origin_time = list(track_data.keys())[0]
    timestamps = [x - origin_time for x in track_data.keys()]
    draw(args.graph, properties, objects, track_data.values(), timestamps)
    args.graph.close()
    return 0

sys.exit(main())
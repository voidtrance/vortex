#!/usr/bin/env python3
import plotly.graph_objects as go
import sys
import os.path

def make_graph(data):
    graph = go.Scatter(x=data["times"], y=data["temps"],
                       mode="lines")
    fig = go.Figure()
    fig.add_trace(graph)
    return fig

def output_graph(graph, filename):
    prefix = """<html>
<head>
<style>
div.plotly-graph-top {{ display: inline-block; }}
table {{ display: inline-block; vertical-align: top; }}
th {{ text-align: left; background-color: #e4f0f5; }}
th.title {{ text-align: center; background-color: #3f87a6; }}
</style>
</head>
<body>"""
    suffix = "</body></html>"""

    with open(filename, 'w') as fd:
        fd.write(prefix)
        html = graph.to_html(full_html=False, include_plotlyjs=True)
        html = html.replace("<div>", "<div class=\"plotly-graph-top\">")
        fd.write(html)
        fd.write(suffix)

def parse_log(filename):
    times, temps = [], []
    path = os.path.join(os.path.dirname(__file__), filename)
    path = os.path.abspath(path)
    with open(path, 'r') as fd:
        for line in fd:
            fields = line.strip().split()
            times.append(int(fields[0][:-1]))
            temps.append(float(fields[-1]))
    return times, temps

data = {"times":None, "temps":None}
data["times"], data["temps"] = parse_log(sys.argv[1])
graph = make_graph(data)
output_graph(graph, "temps.html")

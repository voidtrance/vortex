#!/usr/bin/env python
import json
import pprint
import sys


with open(sys.argv[1], 'r') as fd:
    d = json.load(fd)

pprint.pprint(d)
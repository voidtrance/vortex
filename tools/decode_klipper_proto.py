#!/usr/bin/python
import vortex.frontends.klipper.msgproto as mp
import sys
import re
import json

reg = r'^(?P<type>[^:]+): \[(?P<data>[^\]]+)]$'

r = re.compile(reg)
m = mp.MessageParser()
identity = json.dumps({"commands": mp.DefaultMessages, "responses": {}})
m.process_identify(identity, False)

identity = b''
with open(sys.argv[1], 'r') as fd:
    for line in fd:
        pos = mp.MESSAGE_HEADER_SIZE
        match = r.match(line)
        data = bytearray([int(x) for x in match["data"].split()])
        msgid, pp = m.msgid_parser.parse(data, pos)
        mid = m.messages_by_id.get(msgid, m.unknown)
        params, pos = mid.parse(data, pos)
        if mid.name == "identify_response":
            identity += params["data"]

m.process_identify(identity)
with open(sys.argv[1], 'r') as fd:
    for line in fd:
        pos = mp.MESSAGE_HEADER_SIZE
        match = r.match(line)
        data = bytearray([int(x) for x in match["data"].split()])
        msgid, pp = m.msgid_parser.parse(data, pos)
        mid = m.messages_by_id.get(msgid, m.unknown)
        try:
            params, pos = mid.parse(data, pos)
            print(f"{mid.name}, {params}")
        except IndexError:
            print(f"ERROR: {line}, {data}, {pos}")
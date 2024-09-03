#!/usr/bin/env python3
import sys
import os
from ast import literal_eval
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import frontends.klippy.msgproto as msg

data = bytearray()
with open(sys.argv[1], 'r') as fd:
    for line in fd:
        if line.startswith("MSG[response]") and "identify_response" in line:
            line = line.strip()[15:]
            d = literal_eval(line)
            data += d['data']

mp = msg.MessageParser()
mp.process_identify(data)
print(dir(mp))
print(mp.messages)
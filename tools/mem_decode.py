#!/usr/bin/env python3
import sys

allocations = {}
with open(sys.argv[1], 'rb') as fd:
    i = 1
    for line in fd:
        fields = line.strip().split(b":")
        pid = int(fields[1])
        addr = int(fields[2], 16)
        caller = fields[-2:]
        if pid not in allocations:
            allocations[pid] = {}
        if fields[0] == b"free":
            #assert addr in allocations[pid]
            if addr in allocations[pid]:
                allocations[pid].pop(addr)
        else:
            #if fields[0] in (b"malloc", b"calloc"):
            #    assert addr not in allocations[pid]
            allocations[pid][addr] = caller

for pid in allocations:
    for addr in allocations[pid]:
        print(f"[{pid}] {addr:x}: {allocations[pid][addr]}")

#!/usr/bin/env python
import re
import sys
from ast import literal_eval

UART_DATAGRAM_LENGTH = 40 # bits

class UARTDatagram:
    SYNC_MASK = 0xff
    SYNC_SHIFT = 0
    NODEADDR_MASK = 0xff
    NODEADDR_SHIFT = 8
    ADDR_MASK = 0x7f # includes R/W bit
    ADDR_SHIFT = 16
    ADDR_RW_MASK = 1
    ADDR_RW_SHIFT = 23
    DATA_MASK = 0xffff
    DATA_SHIFT = 24
    CRC_MASK = 0xff
    CRC_SHIFT_WRITE = 56
    CRC_SHIFT_READ = 24

    def __init__(self, datagram):
        if not isinstance(datagram, bytearray):
            raise ValueError("Datagram should be a bytearray")
        data, crc = self.__decode(datagram)
        self.node = (data >> self.NODEADDR_SHIFT) & self.NODEADDR_MASK
        addr = (data >> self.ADDR_SHIFT) & self.ADDR_MASK
        self.addr = addr & ~(self.ADDR_RW_MASK << self.ADDR_RW_SHIFT)
        self.rw = (data >> self.ADDR_RW_SHIFT) & self.ADDR_RW_MASK
        if self.rw:
            self.data = (data >> self.DATA_SHIFT) & self.DATA_MASK
            self.crc = (data >> self.CRC_SHIFT_WRITE) & self.CRC_MASK
        else:
            self.data = 0
            self.crc = (data >> self.CRC_SHIFT_READ) & self.CRC_MASK
        if self.crc != crc:
            raise ValueError("Datagram CRC does not match")
    def __decode(self, datagram):
        data = 0
        for i, d in enumerate(datagram):
            data |= d << (i * 8)
        dec = 0
        i = 0
        while data:
            dec |= ((data >> 1) & 0xff) << (i * 8)
            data = data >> 10
            i += 1
        bdec = bytearray()
        for i in range(0, len(bin(dec)[2:]) - 8, 8):
            bdec.append((dec >> i) & 0xff)
        crc = self._calc_crc8(bdec)
        return dec, crc
    def _calc_crc8(self, data):
        # Generate a CRC8-ATM value for a bytearray
        crc = 0
        for b in data:
            for i in range(8):
                if (crc >> 7) ^ (b & 0x01):
                    crc = (crc << 1) ^ 0x07
                else:
                    crc = (crc << 1)
                crc &= 0xff
                b >>= 1
        return crc
    def __str__(self):
        return f"Datagram(node={self.node:x},addr={self.addr:x},rw={self.rw},data={self.data})"
        
def decode_response(data):
    # Extract a uart read response message
    if len(data) != 10:
        return None
    # Convert data into a long integer for easy manipulation
    mval = pos = 0
    for d in bytearray(data):
        mval |= d << pos
        pos += 8
    # Extract register value
    val = ((((mval >> 31) & 0xff) << 24) | (((mval >> 41) & 0xff) << 16)
           | (((mval >> 51) & 0xff) << 8) | ((mval >> 61) & 0xff))
    # Verify start/stop bits and crc
    #encoded_data = self._encode_write(0x05, 0xff, reg, val)
    #if data != encoded_data:
    #    return None
    return val

# MSG[send] tmcuart_send tmcuart_send oid=1 write=bytearray(b'\xea\x03H \xe4') read=10
# MSG[response]: {'oid': 1, 'read': b'\n\xfaO \x80\x00\x02\xe8\xb2\xee', '#name': 'tmcuart_response'}
# MSG[send] tmcuart_send tmcuart_send oid=1 write=bytearray(b'\xea\x03\x080\x80\x00\n\x08\xb8\x87') read=0
# MSG[response]: {'oid': 1, 'read': b'', '#name': 'tmcuart_response'}
request_re = r'^MSG\[send\] tmcuart_send tmcuart_send oid=(?P<oid>[0-9]+) ' + \
            r'write=bytearray\((?P<data>[^\)]*)\) read=(?P<bytes>[0-9]+)$'

def main():
    request = re.compile(request_re)
    with open(sys.argv[1], 'r') as fd:
        for line in fd:
            match = request.match(line)
            if match:
                data = match.group('data').replace('\\\\', '\\')
                b = literal_eval(data)
                data = bytearray(b)
                datagram = UARTDatagram(data)
                print(str(datagram) if datagram.rw == 1 else "")
            elif line.startswith("MSG[response]") and "tmcuart_response" in line:
                d = literal_eval(line.strip()[15:])
                data = bytearray(d["read"])
                print(decode_response(data))

main()

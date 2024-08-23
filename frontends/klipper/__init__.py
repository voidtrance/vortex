# vortex - GCode machine emulator
# Copyright (C) 2024  Mitko Haralanov
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
import ctypes
import select
import os
from vortex.frontends import BaseFrontend
import vortex.frontends.klipper as msgproto
import vortex.frontends.lib

def create_message(size):
    class MessageBlock(ctypes.Structure):
        _fields_ = [("length", ctypes.c_byte),
                    ("sequence", ctypes.c_byte),
                    ("data", ctypes.c_byte * (size - 5)),
                    ("crc", ctypes.c_byte * 2),
                    ("sync", ctypes.c_byte)]
    return MessageBlock

class KlipperFrontend(BaseFrontend):
    PIPE_FILE = "/tmp/klipper_uds"
    BLOCK_SYNC = 0x7e
    MIN_MSG_LEN = 5
    MAX_MSG_LEN = 64
    SEQ_DEST = 0x10
    SEQ_NUM_MASK = 0xF

    def __init__(self):
        super().__init__()
        self.next_sequence = self.SEQ_DEST
        self.serial_data = bytes()
        self.mp = msgproto.MessageParser()

    def _calc_crc(self, data):
        crc = ctypes.c_uint16(0xffff)
        for i in range(len(data) - 3):
            e = ctypes.c_uint8(data[i])
            e.value = e.value ^ (crc.value & 0xff)
            e.value = e.value ^ (e.value << 4)
            crc.value = ((e.value << 8) | crc.value >> 8) ^ (e.value >> 4) ^ (e.value << 3)
        return crc
 
    def _forward_to_next(self, data):
        if data[0] == self.BLOCK_SYNC:
            return None, data[1:]
        
        i = data.find(bytes([self.BLOCK_SYNC]))
        if i == -1:
            return None, data
        return None, data[i+1:]
    
    def parse_message_block(self, data):
        if len(data) < self.MIN_MSG_LEN:
            return None, data
        
        msg_len = data[0]
        if msg_len < self.MIN_MSG_LEN or msg_len > self.MAX_MSG_LEN:
            return self._forward_to_next(data)            
        
        if len(data) < msg_len:
            return None, data
        
        message = data[:msg_len]
        print(message)
        # verify sync byte
        if message[-1] != self.BLOCK_SYNC:
            print("msg sync failed")
            return self._forward_to_next(data)
        
        # verify sequence destination
        if message[1] & ~self.SEQ_NUM_MASK != self.SEQ_DEST:
            print("msg dest failed")
            return self._forward_to_next(data)
        
        # verify CRC
        msg_crc = message[-3] << 8 | message[-2]
        crc = self._calc_crc(message)
        if crc != msg_crc:
            print("msg crc failed")
            return self._forward_to_next(data)
        
        if message[1] != self.next_sequence:
            print("msg seq failed")
            return None, data[msg_len+1:]
        
        # Advance the sequence number only on successful message
        # parsing. This way all other cases end up sending a NAK.
        self.next_sequence = (message[1] + 1) & self.SEQ_NUM_MASK | self.SEQ_DEST
        return message[3:-3], data
    
    def send_ack_nak(self, device):
        msg = bytearray(self.MIN_MSG_LEN)
        msg[0] = self.MIN_MSG_LEN
        msg[1] = self.next_sequence
        crc = self._calc_crc(msg)
        msg[2] = crc.value >> 8
        msg[3] = crc.value & 0xF
        msg[4] = self.BLOCK_SYNC
        device.write(msg)

    def _process_command(self, data):
        self.serial_data += data
        while 1:
            i = self.mp.check_packet(self.serial_data)
            if i == 0:
                break
            elif i < 0:
                self.serial_data = self.serial_data[-i:]
                continue
            msg_params = self.mp.parse(self.serial_data[:i])
            print(msg_params)
            self.serial_data = self.serial_data[i:]

def create():
    return KlipperFrontend()
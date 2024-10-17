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
import zlib
import json
import time
from vortex.frontends import BaseFrontend
from vortex.lib.utils import Counter
from vortex.controllers.types import ModuleTypes
import vortex.frontends.klipper.msgproto as msgproto
import vortex.frontends.klipper.klipper_proto as proto

def create_message(size):
    class MessageBlock(ctypes.Structure):
        _fields_ = [("length", ctypes.c_byte),
                    ("sequence", ctypes.c_byte),
                    ("data", ctypes.c_byte * (size - 5)),
                    ("crc", ctypes.c_byte * 2),
                    ("sync", ctypes.c_byte)]
    return MessageBlock

# The following set of commands must be implemented at a
# minimum:
# (Source: https://github.com/Annex-Engineering/anchor/blob/master/anchor/src/lib.rs)
# | `get_uptime`     | Must respond with `uptime` |
# | `get_clock`      | Must respond with `clock`  |
# | `emergency_stop` | Can be a no-op             |
# | `allocate_oids`  | Can be a no-op             |
# | `get_config`     | Must reply with `config`   |
# | `config_reset`   | See example                |
# | `finalize_config`| See example                |

class KlipperFrontend(BaseFrontend):
    STATS_SUMSQ_BASE = 256
    def __init__(self):
        super().__init__()
        self.next_sequence = 1
        self.serial_data = bytes()
        self.mp = msgproto.MessageParser()
        # Skip first two values used by default messages
        self.counter = Counter(2)
        self.all_commands = {}
        self.identity = None
        #self.stats_count = 0
        #self.stats_sum = 0
        #self.stats_sumsq = 0
        self.move_queue = []
        self.config_crc = 0
        self.shutdown = False
        self.oid_count = 0

    def _add_commands(self, cmd_set):
        for name, cmd in vars(cmd_set).items():
            self.all_commands[name] = cmd
            self.identity["commands"][cmd.command] = self.counter.next()
            if cmd.response:
                self.identity["responses"][cmd.response] = self.counter.next()

    def create_identity(self):
        self.identity = {x: {} for x in \
                         ["commands", "enumerations",
                          "config", "responses"]}
        self.identity["version"] = "96cceed2"
        self.tag_to_cmd = {}
        base, pins = 0, {}
        for pin_set in self._raw_controller_params["pins"]:
            pins[f"{pin_set.name}{pin_set.min}"] = \
                [base + pin_set.min, len(pin_set)]
            base += len(pin_set)
        self.identity["enumerations"]["pin"] = pins

        # Setup basic Klipper commands
        # Identify commands use static tags
        msg = list(msgproto.DefaultMessages.keys())[0]
        self.identity["responses"][msg] = msgproto.DefaultMessages[msg]
        msg = list(msgproto.DefaultMessages.keys())[1]
        self.identity["commands"][msg] = msgproto.DefaultMessages[msg]
        for name, cmd in vars(proto.KLIPPER_PROTOCOL.basecmd).items():
            self.all_commands[name] = cmd
            if cmd.command in msgproto.DefaultMessages:
                continue
            self.identity["commands"][cmd.command] = self.counter.next()
            if cmd.response:
                self.identity["responses"][cmd.response] = self.counter.next()
        self.identity["config"]["CLOCK_FREQ"] = self.emulation_frequency
        self.identity["config"]["STATS_SUMSQ_BASE"] = self.STATS_SUMSQ_BASE

        # Setup stepper commands
        if self.get_object_id_set(ModuleTypes.STEPPER):
            self._add_commands(proto.KLIPPER_PROTOCOL.stepper)

        # Setup endstop commands
        if self.get_object_id_set(ModuleTypes.ENDSTOP):
            self._add_commands(proto.KLIPPER_PROTOCOL.gpiocmds)

        self.identity_resp = json.dumps(self.identity).encode()
        # Create local command maps
        self.mp.process_identify(self.identity_resp, False)
        print(self.identity)
        self.identity_resp = zlib.compress(self.identity_resp)

    #def klipper_stats(self):
    #    tick = self.get_controller_clock_ticks()
    #    diff = tick - self.start_tick
    #    self.stats_sum += diff

    def run(self):
        self.create_identity()
        self.start_tick = self.get_controller_clock_ticks()
        super().run()

    def respond(self, data=[]):
        msg_len = msgproto.MESSAGE_MIN + len(data)
        seq = (self.next_sequence & msgproto.MESSAGE_SEQ_MASK) | msgproto.MESSAGE_DEST
        msg = [msg_len, seq] + data
        msg += msgproto.crc16_ccitt(msg)
        msg.append(msgproto.MESSAGE_SYNC)
        #print("response: ", msg)
        self._fd.write(bytearray(msg))
        self._fd.flush()

    def identify(self, cmd, offset, count):
        self._test = None
        response = cmd.response
        msg = self.mp.lookup_command(response)
        data = self.identity_resp[offset:offset+count]
        resp = msg.encode_by_name(offset=offset, data=data)
        self.respond(resp)
        return True

    def get_uptime(self, cmd):
        runtime = self.get_controller_clock_ticks() - self.start_tick
        msg = self.mp.lookup_command(cmd.response)
        resp = msg.encode_by_name(high=((runtime >> 32) & 0xffffffff),
                                  clock=(runtime & 0xffffffff))
        self.respond(resp)
        return True

    def get_clock(self, cmd):
        now = self.get_controller_clock_ticks()
        msg = self.mp.lookup_command(cmd.response)
        resp = msg.encode_by_name(clock=(now & 0xffffffff))
        self.respond(resp)
        return True

    def get_config(self, cmd):
        move_count = len(self.move_queue)
        msg = self.mp.lookup_command(cmd.response)
        resp = msg.encode_by_name(is_config=int(move_count != 0),
                                  crc=self.config_crc, is_shutdown=self.shutdown,
                                  move_count=move_count)
        self.respond(resp)
        return True

    def allocate_oids(self, cmd, count):
        self.oid_count = count
        return True

    def finalize_config(self, cmd, crc):
        self.config_crc = crc
        return True

    def _process_command(self, data):
        self.serial_data += data
        while 1:
            i = self.mp.check_packet(self.serial_data)
            if i == 0:
                break
            elif i < 0:
                self.serial_data = self.serial_data[-i:]
                continue
            block = self.serial_data[:i]
            #print("recv'ed: ", [x for x in block])
            block_seq = block[msgproto.MESSAGE_POS_SEQ] & msgproto.MESSAGE_SEQ_MASK
            if block_seq == self.next_sequence:
                self.next_sequence = (self.next_sequence + 1) & msgproto.MESSAGE_SEQ_MASK
                pos = msgproto.MESSAGE_HEADER_SIZE
                while 1:
                    msgid, param_pos = self.mp.msgid_parser.parse(block, pos)
                    mid = self.mp.messages_by_id.get(msgid, self.mp.unknown)
                    msg_params, pos = mid.parse(block, pos)
                    print("message: ", mid.name, msg_params)
                    cmd = self.all_commands[mid.name]
                    handler = getattr(self, mid.name)
                    if not handler(cmd=cmd, **msg_params):
                        raise self.mp._error("Failed command handler")
                    if pos >= len(block) - msgproto.MESSAGE_TRAILER_SIZE:
                        break
            self.respond()
            self.serial_data = self.serial_data[i:]

def create():
    return KlipperFrontend()
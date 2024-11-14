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
import zlib
import json
import logging
from vortex.controllers.types import ModuleTypes
from vortex.frontends import BaseFrontend
from vortex.frontends.klipper.helpers import *
from vortex.lib.utils import Counter
import vortex.frontends.klipper.msgproto as msgproto
import vortex.frontends.klipper.klipper_proto as proto

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

STATIC_STRINGS = [
    "ADC out of range",
    "Unsupported command",
    "Command failure",
    "Invalid count parameter",
    "Stepper initialization failure",
]

class KlipperFrontend(BaseFrontend):
    STATS_SUMSQ_BASE = 256
    def __init__(self):
        super().__init__(1024)
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
        self.config_crc = 0
        self.oid_count = 0
        self._oid_map = {}
        self._string_map = {}
        self._shutdown = False
        self._shutdown_reason = None

    def _add_commands(self, cmd_set):
        for name, cmd in vars(cmd_set).items():
            self.all_commands[name] = cmd
            if cmd.command:
                self.identity["commands"][cmd.command] = self.counter.next()
            if cmd.response:
                self.identity["responses"][cmd.response] = self.counter.next()

    def create_identity(self):
        self.identity = {x: {} for x in ["commands", "enumerations",
                                         "config", "responses"]}
        self.identity["version"] = "96cceed2"
        self.tag_to_cmd = {}

        # Setup enumerations
        base, pins = 0, {}
        for pin_set in self._raw_controller_params["hw"]["pins"]:
            pins[f"{pin_set.name}{pin_set.min}"] = \
                [base + pin_set.min, len(pin_set)]
            base += len(pin_set)
        self.identity["enumerations"]["pin"] = pins

        static_string_counter = Counter()
        for string in STATIC_STRINGS:
            self._string_map[string] = static_string_counter.next()
        self.identity["enumerations"]["static_string_id"] = self._string_map

        # Setup basic config variables
        self.identity["config"]["CLOCK_FREQ"] = self.emulation_frequency
        self.identity["config"]["STATS_SUMSQ_BASE"] = self.STATS_SUMSQ_BASE

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

        # Shutdown commands
        self._add_commands(proto.KLIPPER_PROTOCOL.shutdown)

        # Setup stepper commands
        if self._raw_controller_params["hw"]["motors"]:
            self._add_commands(proto.KLIPPER_PROTOCOL.stepper)
            self._add_commands(proto.KLIPPER_PROTOCOL.trsync)

        # Setup endstop commands
        if self._raw_controller_params["hw"]["endstops"] or \
            self._raw_controller_params["hw"]["digital"]:
            self._add_commands(proto.KLIPPER_PROTOCOL.gpiocmds)
            self._add_commands(proto.KLIPPER_PROTOCOL.endstop)

        # Setup thermistor commands
        if self._raw_controller_params["hw"]["thermistors"]:
            self._add_commands(proto.KLIPPER_PROTOCOL.thermocouple)
            self._add_commands(proto.KLIPPER_PROTOCOL.adccmds)

        if self._raw_controller_params["hw"]["heaters"] or \
            self._raw_controller_params["hw"]["pwm"]:
            self._add_commands(proto.KLIPPER_PROTOCOL.pwmcmds)
            self.identity["config"]["ADC_MAX"] = \
                    self._raw_controller_params["hw"]["adc_max"]

        self.identity_resp = json.dumps(self.identity).encode()
        # Create local command maps
        self.mp.process_identify(self.identity_resp, False)
        self.identity_resp = zlib.compress(self.identity_resp)

    #def klipper_stats(self):
    #    tick = self.get_controller_clock_ticks()
    #    diff = tick - self.start_tick
    #    self.stats_sum += diff

    def run(self):
        self.create_identity()
        self.start_tick = self.get_controller_clock_ticks()
        super().run()

    def respond(self, type, cmd=None, **kwargs):
        if type == proto.ResponseTypes.RESPONSE:
            if not cmd:
                raise AttributeError("Command required for response")
            if not cmd.response:
                return
            msg = self.mp.lookup_command(cmd.response)
            logging.debug(f"response: {msg.format_params(kwargs)}")
            data = msg.encode_by_name(**kwargs)
        else:
            data = []
        msg_len = msgproto.MESSAGE_MIN + len(data)
        seq = (self.next_sequence & msgproto.MESSAGE_SEQ_MASK) | msgproto.MESSAGE_DEST
        packet = [msg_len, seq] + data
        packet += msgproto.crc16_ccitt(packet)
        packet.append(msgproto.MESSAGE_SYNC)
        self._fd.write(bytearray(packet))
        self._fd.flush()

    def _find_object(self, pin, *klasses):
        def find(pin, objects):
            object_status = self.query_object(objects)
            for obj_id, status in object_status.items():
                pins = []
                for k, v in status.items():
                    if k == "pin" or "_pin" in k:
                        pins.append(v)
                if pin in pins:
                    return obj_id
        if not klasses:
            klasses = ModuleTypes
        for klass in klasses:
            objects = self.get_object_id_set(klass)
            obj_id = find(pin, objects)
            if obj_id is not None:
                return obj_id, klass
        return None, None
    
    def find_existing_object(self, obj_id):
        for obj in self._oid_map.values():
            if not isinstance(obj, int):
                if obj.id == obj_id:
                    return obj
        return None

    def identify(self, cmd, offset, count):
        self._test = None
        data = self.identity_resp[offset:offset+count]
        self.respond(proto.ResponseTypes.RESPONSE, cmd, offset=offset, data=data)
        return True

    def shutdown(self, reason):
        self._shutdown_reason = reason
        self._shutdown = True
        for obj in self._oid_map.values():
            obj.shutdown()
        self.respond(proto.ResponseTypes.RESPONSE,
                     proto.KLIPPER_PROTOCOL.shutdown.shutdown,
                     clock=self.get_controller_clock_ticks(),
                     static_string_id=reason)

    def is_shutdown(self, reson):
        self.respond(proto.ResponseTypes.RESPONSE,
                     proto.KLIPPER_PROTOCOL.shutdown.is_shutdown,
                     static_string_id=self._shutdown_reason)

    def emergency_stop(self, cmd):
        for oid, obj in self._oid_map.items():
            obj.shutdown()
        self.reset()
        return True

    def get_uptime(self, cmd):
        runtime = self.get_controller_clock_ticks() - self.start_tick
        self.respond(proto.ResponseTypes.RESPONSE, cmd,
                     high=((runtime >> 32) & 0xffffffff),
                     clock=(runtime & 0xffffffff))
        return True

    def get_clock(self, cmd):
        now = self.get_controller_clock_ticks()
        self.respond(proto.ResponseTypes.RESPONSE, cmd, clock=(now & 0xffffffff))
        return True

    def get_config(self, cmd):
        move_count = self._queue.max_size if self.config_crc else 0
        self.respond(proto.ResponseTypes.RESPONSE, cmd, is_config=int(move_count != 0),
                      crc=self.config_crc, is_shutdown=self._shutdown,
                      move_count=move_count)
        return True

    def allocate_oids(self, cmd, count):
        self.oid_count = count
        return True

    def finalize_config(self, cmd, crc):
        self.config_crc = crc
        return True

    def config_analog_in(self, cmd, oid, pin):
        obj_id, klass = self._find_object(pin, ModuleTypes.THERMISTOR)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        self._oid_map[oid] = AnalogPin(self, oid, obj_id, klass, name)
        return True
    
    def query_analog_in(self, cmd, oid, clock, sample_ticks, sample_count,
                        rest_ticks, min_value, max_value, range_check_count):
        pin = self._oid_map[oid]
        pin.schedule_query(cmd, clock, sample_ticks, sample_count,
                           rest_ticks, min_value, max_value, range_check_count)
        return True

    def config_digital_out(self, cmd, oid, pin, value, default_value,
                           max_duration):
        obj_id, klass = self._find_object(pin)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        if klass == ModuleTypes.HEATER:
            pin = HeaterPin(self, oid, obj_id, name)
        elif klass == ModuleTypes.STEPPER:
            stepper = self.find_existing_object(obj_id)
            if stepper is None or not stepper.owns_pin(pin):
                return False
            pin = stepper.configure_pin(oid, pin)
        else:
            pin = DigitalPin(self, oid, obj_id, klass, name)
        pin.set_initial_value(value, default_value)
        pin.set_max_duration(max_duration)
        self._oid_map[oid] = pin
        return True

    def set_digital_out_pwm_cycle(self, cmd, oid, cycle_ticks):
        pin = self._oid_map[oid]
        pin.set_cycle_ticks(cycle_ticks)
        return True

    def queue_digital_out(self, cmd, oid, clock, on_ticks):
        pin = self._oid_map[oid]
        pin.schedule_cycle(clock, on_ticks)
        return True

    def config_stepper(self, cmd, oid, step_pin, dir_pin, invert_step,
                       step_pulse_ticks):
        obj_id, klass = self._find_object(step_pin, ModuleTypes.STEPPER)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        try:
            self._oid_map[oid] = Stepper(self, oid, obj_id, name,
                                         invert_step, step_pulse_ticks)
        except ValueError:
            self.shutdown("Stepper initialization failed")
        return True

    def stepper_get_position(self, cmd, oid):
        stepper = self._oid_map[oid]
        self.respond(proto.ResponseTypes.RESPONSE, cmd, oid=oid, pos=stepper.position)
        return True

    def stepper_stop_on_trigger(self, cmd, oid, trsync_oid):
        stepper = self._oid_map[oid]
        trsync = self._oid_map[trsync_oid]
        trsync.add_signal(stepper.stop_moves)
        return True

    def set_next_step_dir(self, cmd, oid, dir):
        stepper = self._oid_map[oid]
        stepper.set_next_move_dir(dir)
        return True

    def queue_step(self, cmd, oid, interval, count, add):
        stepper = self._oid_map[oid]
        stepper.queue_move(interval, count, add)
        return True

    def reset_step_clock(self, cmd, oid, clock):
        stepper = self._oid_map[oid]
        stepper.reset_clock(clock)
        return True

    def config_endstop(self, cmd, oid, pin, pull_up):
        obj_id, klass = self._find_object(pin, ModuleTypes.ENDSTOP,
                                          ModuleTypes.PROBE)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        self._oid_map[oid] = EndstopPin(self, oid, obj_id, name)
        return True

    def endstop_home(self, cmd, oid, clock, sample_ticks, sample_count, rest_ticks,
                     pin_value, trsync_oid, trigger_reason):
        endstop = self._oid_map[oid]
        trsync = self._oid_map[trsync_oid]
        endstop.home(clock, sample_ticks, sample_count, rest_ticks, pin_value,
                     trsync, trigger_reason)
        return True

    def endstop_query_state(self, cmd, oid):
        endstop = self._oid_map[oid]
        state = endstop.get_state()
        state.update({"oid": oid})
        self.respond(proto.ResponseTypes.RESPONSE, cmd, **state)
        return True

    def config_trsync(self, cmd, oid):
        self._oid_map[oid] = TRSync(self, oid)
        return True

    def trsync_start(self, cmd, oid, report_clock, report_ticks, expire_reason):
        trsync = self._oid_map[oid]
        trsync.start(report_clock, report_ticks, expire_reason)
        return True

    def trsync_set_timeout(self, cmd, oid, clock):
        trsync = self._oid_map[oid]
        trsync.set_timeout(clock)
        return True

    def trsync_trigger(self, cmd, oid, reason):
        trsync = self._oid_map[oid]
        trsync.trigger(reason)
        trsync.report(0)
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
            block_seq = block[msgproto.MESSAGE_POS_SEQ] & msgproto.MESSAGE_SEQ_MASK
            if block_seq == self.next_sequence:
                self.next_sequence = (self.next_sequence + 1) & msgproto.MESSAGE_SEQ_MASK
                pos = msgproto.MESSAGE_HEADER_SIZE
                while 1:
                    msgid, param_pos = self.mp.msgid_parser.parse(block, pos)
                    mid = self.mp.messages_by_id.get(msgid, self.mp.unknown)
                    msg_params, pos = mid.parse(block, pos)
                    logging.debug(f"request: {mid.name} {msg_params}")
                    cmd = self.all_commands[mid.name]
                    if self._shutdown and \
                        proto.KlipperProtoFlags.HF_IN_SHUTDOWN not in cmd.flags:
                        self.is_shutdown(self._shutdown_reason)
                        break
                    if not hasattr(self, mid.name):
                        self.shutdown("Unsupported command")
                        break
                    handler = getattr(self, mid.name)
                    if not handler(cmd=cmd, **msg_params):
                        self.shutdown("Command failure")
                        break
                    if pos >= len(block) - msgproto.MESSAGE_TRAILER_SIZE:
                        break
            self.respond(proto.ResponseTypes.ACK)
            self.serial_data = self.serial_data[i:]

def create():
    return KlipperFrontend()
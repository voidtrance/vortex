# vortex - GCode machine emulator
# Copyright (C) 2024-2025 Mitko Haralanov
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
from threading import Lock
from vortex.core import ObjectTypes
from vortex.core.lib.logging import get_level, DEBUG
from vortex.frontends import BaseFrontend
from vortex.frontends.klipper.helpers import *
from vortex.lib.utils import Counter, parse_frequency, div_round_up
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
    "Command request",
    "Invalid count parameter",
    "Timer too close",
    "Stepper initialization failure",
    "Missed scheduling of next digital out event",
    "Scheduled digital out event will exceed max duration",
    "Failed to set PWM duty cycle",
    "PWM move exceeds max duration",
    "Missed scheduling of next PWM out event",
]

class MoveQueue:
    def __init__(self, size):
        self._size = size
        self._elems = 0
        self._queue = {}
        self._lock = Lock()
    def _get_move_locked(self, oid):
        if oid not in self._queue or not self._queue[oid]:
            return None
        return self._queue[oid][0]
    def put(self, oid, item):
        with self._lock:
            if oid not in self._queue:
                self._queue[oid] = []
            if self._elems < self._size:
                self._queue[oid].append(item)
                self._elems += 1
            return self._elems
    def get(self, oid):
        with self._lock:
            move = self._get_move_locked(oid)
            if move is not None:
                self._queue[oid].remove(move)
                self._elems -= 1
            return move
    def peek(self, oid):
        with self._lock:
            return self._get_move_locked(oid)
    def empty(self, oid=None):
        with self._lock:
            if oid is not None:
                return oid not in self._queue or not self._queue[oid]
            return self._elems == 0
    def clear(self, oid=None):
        with self._lock:
            if oid is not None:
                self._queue.clear()
                self._elems = 0
            else:
                if oid in self._queue:
                    self._elems -= len(self._queue[oid])
                    self._queue[oid].clear()
    def size(self):
        with self._lock:
            return self._elems
    def __len__(self):
        return self.size()

class KlipperFrontend(BaseFrontend):
    STATS_SUMSQ_BASE = 256
    def __init__(self):
        super().__init__(1024)
        self.next_sequence = 1
        self.serial_data = bytes()
        self.mp = msgproto.MessageParser()
        self.move_queue = MoveQueue(1024)
        # Skip first two values used by default messages
        self.counter = Counter(2)
        self.all_commands = {}
        self.identity = None
        self.stats_count = 0
        self.stats_sum = 0
        self.stats_sumsq = 0
        self.config_crc = 0
        self.oid_count = 0
        self._oid_map = {}
        self._string_map = {}
        self._shutdown = False
        self._shutdown_reason = None
        self._clock_high = 0
        self._stats_sent_time = 0
        self._object_pin_map = {}

    def _add_commands(self, cmd_set):
        for name, cmd in vars(cmd_set).items():
            self.all_commands[name] = cmd
            if cmd.command:
                self.identity["commands"][cmd.command] = self.counter.next()
            if cmd.response:
                self.identity["responses"][cmd.response] = self.counter.next()

    def _create_identity(self):
        self.identity = {x: {} for x in ["commands", "enumerations",
                                         "config", "responses"]}
        self.identity["version"] = proto.KLIPPER_PROTOCOL.version
        self.tag_to_cmd = {}

        # Setup enumerations
        base, pins = 0, {}
        for pin_set in self.query_hw("PINS"):
            pins[f"{pin_set.name}{pin_set.min}"] = \
                [base + pin_set.min, len(pin_set)]
            base += len(pin_set)
        self.identity["enumerations"]["pin"] = pins

        static_string_counter = Counter()
        for string in STATIC_STRINGS:
            self._string_map[string] = static_string_counter.next()
        self.identity["enumerations"]["static_string_id"] = self._string_map

        # Setup basic config variables
        self.identity["config"]["CLOCK_FREQ"] = self.query_hw("FREQUENCY")
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
        self.all_commands["reset"] = "reset"
        self.identity["commands"]["reset"] = self.counter.next()

        # Shutdown commands
        self._add_commands(proto.KLIPPER_PROTOCOL.sched)

        # Setup stepper commands
        if self.query_hw("STEPPER_COUNT"):
            self._add_commands(proto.KLIPPER_PROTOCOL.stepper)
            self._add_commands(proto.KLIPPER_PROTOCOL.trsync)

        # Setup endstop commands
        if self.query_hw("ENDSTOP_COUNT") or self.query_hw("DIGITAL_PIN_COUNT"):
            self._add_commands(proto.KLIPPER_PROTOCOL.gpiocmds)
            self._add_commands(proto.KLIPPER_PROTOCOL.endstop)

        # Setup thermistor commands
        if self.query_hw("THERMISTOR_COUNT"):
            self._add_commands(proto.KLIPPER_PROTOCOL.thermocouple)
            self._add_commands(proto.KLIPPER_PROTOCOL.adccmds)

        if self.query_hw("HEATER_COUNT") or self.query_hw("PWM_COUNT"):
            self._add_commands(proto.KLIPPER_PROTOCOL.pwmcmds)
            self.identity["config"]["ADC_MAX"] = self.query_hw("ADC_MAX")
            self.identity["config"]["PWM_MAX"] = self.query_hw("PWM_MAX")

        if len(self.query_hw("SPI")):
            self._add_commands(proto.KLIPPER_PROTOCOL.spicmds)
            self._add_commands(proto.KLIPPER_PROTOCOL.spi_software)

        if self.find_object(ObjectTypes.DISPLAY) is not None:
            self._add_commands(proto.KLIPPER_PROTOCOL.buttons)

        if self.query_hw("NEOPIXEL_COUNT"):
            self._add_commands(proto.KLIPPER_PROTOCOL.neopixel)

        self.identity_resp = json.dumps(self.identity).encode()
        # Create local command maps
        self.mp.process_identify(self.identity_resp, False)
        self.identity_resp = zlib.compress(self.identity_resp)

    def _create_object_pin_map(self):
        pmap = {}
        for klass in ObjectTypes:
            pmap[klass] = {}
            objects = self.get_object_id_set(klass)
            object_status = self.query_object(objects)
            for obj_id, status in object_status.items():
                for k, v in status.items():
                    if (k == "pin" or "_pin" in k or "pin_" in k) and \
                        "addr" not in k and "pins" not in k:
                        pmap[klass][v] = obj_id
        return pmap

    def klipper_stats(self, ticks):
        diff = ticks - self.start_tick
        self.stats_sum += diff
        self.stats_count += 1
        if diff <= 0xffff:
            nextsumq = self.stats_sumsq + div_round_up(diff * diff, self.STATS_SUMSQ_BASE)
        elif diff <= 0xfffff:
            nextsumq = self.stats_sumsq + div_round_up(diff, self.STATS_SUMSQ_BASE) * diff
        else:
            nextsumq = 0xffffffff
        if (nextsumq < self.stats_sumsq):
            nextsumq = 0xffffffff
        self.stats_sumsq = nextsumq
        stat_period = self.timers.from_us(5000000)
        if self.timers.is_before(ticks, self._stats_sent_time + stat_period):
            return ticks + self.timers.from_us(100000)
        self.respond(proto.ResponseTypes.RESPONSE,
                     proto.KLIPPER_PROTOCOL.basecmd.stats,
                     count=self.stats_count,
                     sum=self.stats_sum,
                     sumsq=self.stats_sumsq)
        if ticks < self._stats_sent_time:
            self._clock_high += 1
        self._stats_sent_time = ticks
        self.stats_count = 0
        self.stats_sum = 0
        self.stats_sumsq = 0
        return ticks + self.timers.from_us(100000)

    def run(self):
        if get_level() <= DEBUG:
            self.log.warning("Klipper host is very dependent on controller")
            self.log.warning("timing, High levels of debug output will affect")
            self.log.warning("controller timer performance and as a result,")
            self.log.warning("Klipper host may encounter timing errors.")
        if self.emulation_frequency < parse_frequency("1MHz"):
            self.log.warning("Using frequency of less than 1MHz may result")
            self.log.warning("in Klipper failures due to timing granularity.")
        self._create_identity()
        self._object_pin_map = self._create_object_pin_map()
        self.start_tick = self.get_controller_clock_ticks()
        self._stats_timer = self.timers.new()
        self._stats_timer.callback = self.klipper_stats
        self._stats_timer.timeout = self.start_tick + self.timers.from_us(100000)
        super().run()

    def stop(self):
        self._reset_objects()
        super().stop()

    def respond(self, type, cmd=None, **kwargs):
        if type == proto.ResponseTypes.RESPONSE:
            if not cmd:
                raise AttributeError("Command required for response")
            if not cmd.response:
                return
            msg = self.mp.lookup_command(cmd.response)
            self.log.verbose("response: %s", msg.format_params(kwargs))
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

    def find_object_from_pin(self, pin, *klasses):
        if not klasses:
            klasses = ObjectTypes
        for klass in klasses:
            if pin in self._object_pin_map[klass]:
                return self._object_pin_map[klass][pin], klass
        return None, None
    
    def find_existing_object(self, obj_id):
        for obj in self._oid_map.values():
            if not isinstance(obj, int):
                if obj.id == obj_id:
                    return obj
        return None

    def _reset_objects(self):
        for obj in self._oid_map.values():
            obj.shutdown()
        self._oid_map.clear()
        self.oid_count = 0

    def identify(self, cmd, offset, count):
        data = self.identity_resp[offset:offset+count]
        self.respond(proto.ResponseTypes.RESPONSE, cmd, offset=offset, data=data)
        return True

    def shutdown(self, reason):
        self._shutdown_reason = reason
        self._shutdown = True
        self._reset_objects()
        self.respond(proto.ResponseTypes.RESPONSE,
                     proto.KLIPPER_PROTOCOL.sched.shutdown,
                     clock=self.get_controller_clock_ticks(),
                     static_string_id=reason)

    def is_shutdown(self, reson):
        self.respond(proto.ResponseTypes.RESPONSE,
                     proto.KLIPPER_PROTOCOL.sched.is_shutdown,
                     static_string_id=self._shutdown_reason)

    def emergency_stop(self, cmd):
        self.shutdown("Command request")
        return True

    def reset(self, cmd=None):
        self._reset_objects()
        self.config_crc = 0
        self._shutdown = False
        return super().reset()

    def get_uptime(self, cmd):
        runtime = self.get_controller_clock_ticks()
        self.respond(proto.ResponseTypes.RESPONSE, cmd,
                     high=self._clock_high + int(runtime < self._stats_sent_time),
                     clock=runtime)
        return True

    def get_clock(self, cmd):
        now = self.get_controller_clock_ticks()
        self.respond(proto.ResponseTypes.RESPONSE, cmd, clock=now)
        return True

    def get_config(self, cmd):
        move_count = self._queue.max_size if self.config_crc else 0
        self.respond(proto.ResponseTypes.RESPONSE, cmd, is_config=int(move_count != 0),
                      crc=self.config_crc, is_shutdown=self._shutdown,
                      move_count=move_count)
        return True

    def allocate_oids(self, cmd, count):
        self._reset_objects()
        self.oid_count = count
        return True

    def finalize_config(self, cmd, crc):
        self.config_crc = crc
        for obj in self._oid_map.values():
            obj.finish_config()
        return True

    def config_analog_in(self, cmd, oid, pin):
        obj_id, klass = self.find_object_from_pin(pin, ObjectTypes.THERMISTOR)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        self._oid_map[oid] = AnalogPin(self, self.move_queue, oid, obj_id, klass, name)
        return True
    
    def query_analog_in(self, cmd, oid, clock, sample_ticks, sample_count,
                        rest_ticks, min_value, max_value, range_check_count):
        pin = self._oid_map[oid]
        pin.schedule_query(cmd, clock, sample_ticks, sample_count,
                           rest_ticks, min_value, max_value, range_check_count)
        return True

    def config_digital_out(self, cmd, oid, pin, value, default_value,
                           max_duration):
        obj_id, klass = self.find_object_from_pin(pin)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        if klass == ObjectTypes.HEATER:
            pin = HeaterPin(self, self.move_queue, oid, obj_id, klass, name)
        elif klass == ObjectTypes.STEPPER:
            stepper = self.find_existing_object(obj_id)
            if stepper is None or not stepper.owns_pin(pin):
                return False
            pin = stepper.configure_pin(oid, pin)
        elif klass == ObjectTypes.DISPLAY:
            display = self.find_existing_object(obj_id)
            if display is None or not display.owns_pin(pin):
                return False
            pin = display.configure_pin(oid, pin)
        else:
            pin = DigitalPin(self, self.move_queue, oid, obj_id, klass, name)
        if not isinstance(pin, DigitalPin):
            return False
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

    def update_digital_out(self, cmd, oid, value):
        pin = self._oid_map[oid]
        pin.update(value)
        return True

    def config_stepper(self, cmd, oid, step_pin, dir_pin, invert_step,
                       step_pulse_ticks):
        obj_id, klass = self.find_object_from_pin(step_pin, ObjectTypes.STEPPER)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        try:
            self._oid_map[oid] = Stepper(self, self.move_queue, oid, obj_id, klass, name)
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
        obj_id, klass = self.find_object_from_pin(pin, ObjectTypes.ENDSTOP,
                                          ObjectTypes.PROBE)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        self._oid_map[oid] = EndstopPin(self, self.move_queue, oid, obj_id, klass, name)
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
        self._oid_map[oid] = TRSync(self, self.move_queue, oid, -1, ObjectTypes.NONE)
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

    def config_spi(self, cmd, oid, pin, cs_active_high):
        obj_id, klass = self.find_object_from_pin(pin)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        self._oid_map[oid] = SPI(self, self.move_queue, oid, obj_id, klass, name,
                                 pin, cs_active_high)
        return True

    def spi_set_software_bus(self, cmd, oid, miso_pin, mosi_pin, sclk_pin, mode, rate):
        spi = self._oid_map[oid]
        return spi.set_sw_bus(miso_pin, mosi_pin,sclk_pin, mode, rate)

    def spi_send(self, cmd, oid, data):
        spi = self._oid_map[oid]
        result = spi.send(data)
        return result >= 0

    def spi_transfer(self, cmd, oid, data):
        spi = self._oid_map[oid]
        result = spi.send(data, True)
        if isinstance(result, bytes):
            self.respond(proto.ResponseTypes.RESPONSE, cmd, data=result)
            return True
        else:
            return result >= 0

    def config_buttons(self, cmd, oid, button_count):
        self._oid_map[oid] = Buttons(self, self.move_queue, oid, -1, ObjectTypes.NONE,
                                     "", button_count)
        return True

    def buttons_add(self, cmd, oid, pos, pin, pull_up):
        buttons = self._oid_map[oid]
        button, klass = self.find_object_from_pin(pin, ObjectTypes.DIGITAL_PIN,
                                          ObjectTypes.ENCODER)
        if button is None:
            return False
        name = self.get_object_name(klass, button)
        return buttons.add_button(pos, button, klass, pin, pull_up)

    def buttons_query(self, cmd, oid, clock, rest_ticks, retransmit_count, invert):
        buttons = self._oid_map[oid]
        buttons.query(cmd, clock, rest_ticks, retransmit_count, invert)
        return True

    def buttons_ack(self, cmd, oid, count):
        buttons = self._oid_map[oid]
        buttons.ack(count)
        return True

    def config_pwm_out(self, cmd, oid, pin, cycle_ticks, value, default_value, max_duration):
        obj_id, klass = self.find_object_from_pin(pin, ObjectTypes.PWM)
        pin_id, _ = self.find_object_from_pin(pin, ObjectTypes.DIGITAL_PIN)
        if obj_id is None or pin_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        pwm = PWM(self, self.move_queue, oid, obj_id, klass, name)
        if pwm.set_params(cycle_ticks, value, default_value, max_duration):
            return False
        self._oid_map[oid] = pwm
        return True

    def queue_pwm_out(self, cmd, oid, clock, value):
        pwm = self._oid_map[oid]
        if not pwm.queue(clock, value):
            return False
        return True

    def set_pwm_out(self, cmd, oid, pin, cycle_ticks, value):
        return self.config_pwm_out(cmd, oid, pin, cycle_ticks, value, 0, 0)

    def config_neopixel(self, cmd, oid, pin, data_size, bit_max_ticks, reset_min_ticks):
        obj_id, klass = self.find_object_from_pin(pin, ObjectTypes.NEOPIXEL)
        if obj_id is None:
            return False
        name = self.get_object_name(klass, obj_id)
        neopixel = Neopixel(self, self.move_queue, oid, obj_id, klass, name, data_size)
        self._oid_map[oid] = neopixel
        return True

    def neopixel_update(self, cmd, oid, pos, data):
        neopixel = self._oid_map[oid]
        if neopixel.update(pos, data):
            return False
        return True

    def neopixel_send(self, cmd, oid):
        neopixel = self._oid_map[oid]
        status = neopixel.send()
        self.respond(proto.ResponseTypes.RESPONSE, cmd, oid=oid, success=status)
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
                    self.log.verbose("request: %s %s", mid.name, msg_params)
                    cmd = self.all_commands[mid.name]
                    if not isinstance(cmd, str) and self._shutdown and \
                        proto.KlipperProtoFlags.HF_IN_SHUTDOWN not in cmd.flags:
                        self.is_shutdown(self._shutdown_reason)
                        break
                    if not hasattr(self, mid.name):
                        self.shutdown("Unsupported command")
                        break
                    handler = getattr(self, mid.name)
                    ret = handler(cmd=cmd, **msg_params)
                    if (type(ret) == int and ret != 0) or ret is False:
                        self.shutdown("Command failure")
                        break
                    if pos >= len(block) - msgproto.MESSAGE_TRAILER_SIZE:
                        break
            self.respond(proto.ResponseTypes.ACK)
            self.serial_data = self.serial_data[i:]

    def __del__(self):
        self._reset_objects()
        super().__del__()

def create():
    return KlipperFrontend()
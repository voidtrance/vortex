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
import enum
import ctypes
from collections import namedtuple
from vortex.controllers.types import ModuleTypes
from vortex.frontends.klipper.klipper_proto import ResponseTypes, KLIPPER_PROTOCOL

__all__ = ["AnalogPin", "DigitalPin", "HeaterPin", "EndstopPin",
           "Stepper", "TRSync"]

class AnalogPin:
    def __init__(self, frontend, oid, obj_id, klass, name):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.klass = klass
        self.name = name
        self.timer = None
    def schedule_query(self, cmd, clock, sample_ticks,
                       sample_count, rest_ticks, min_value, max_value,
                       range_check_count):
        self.cmd = cmd
        self.query_time = clock
        self.query_sleep_time = sample_ticks
        self.max_sample_count = sample_count
        self.sample_count = 0
        self.rest_ticks = rest_ticks
        self.value = 0
        self.min = min_value
        self.max = max_value
        self.invalid_count = 0
        self.range_check_count = range_check_count
        if not self.timer:
            self.timer = self.frontend.register_timer(self.handler,
                                                      self.query_time)
    def handler(self, ticks):
        status = self.frontend.query_object([self.id])[self.id]
        value = status["adc"]
        if self.sample_count >= self.max_sample_count:
            self.sample_count = 0
        else:
            value += self.value
        self.value = value
        self.sample_count += 1
        if self.sample_count < self.max_sample_count:
            return ticks + self.query_sleep_time
        if value >= self.min and value <= self.max:
            self.invalid_count = 0
        else:
            self.invalid_count += 1
            if self.invalid_count >= self.range_check_count:
                self.frontend.shutdown("ADC out of range")
                self.invalid_count = 0
        self.query_time = ticks + self.rest_ticks
        self.frontend.respond(ResponseTypes.RESPONSE, self.cmd, oid=self.oid,
                                   next_clock=self.query_time,
                                   value=value)
        return self.query_time
    def shutdown(self):
        if self.timer:
            self.frontend.unregister_timer(self.timer)
            self.timer = None
    def __del__(self):
        self.shutdown()

class Flags(enum.IntFlag):
    OFF = enum.auto()
    ON = enum.auto()
    TOGGLING = enum.auto()
    CHECK_END = enum.auto()
    DEFAULT_ON = enum.auto()

class DigitalPin:
    def __init__(self, frontend, oid, obj_id, name):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.name = name
        self.end_time = 0
        self.flags = Flags.OFF
        self.max_duration = 0
        self.handler = self.event
        self.timer = None
        self.cycle_ticks = 0
    def _set_pin(self, value):
        self.frontend.queue_command(ModuleTypes.DIGITAL_PIN,
                                    self.name, "set", {"state": int(value)})
    def set_initial_value(self, value, default):
        self.flags = (Flags.ON if value else Flags.OFF) | \
            (Flags.DEFAULT_ON if default else Flags.OFF)
        self._set_pin(self.flags & Flags.ON)
    def set_max_duration(self, duration):
        self.max_duration = duration
    def set_cycle_ticks(self, ticks):
        self.cycle_ticks = ticks
    def schedule_cycle(self, start, ticks_on):
        self.on_duration = ticks_on
        self.end_time = start
        self.flags |= Flags.CHECK_END
        self.handler = self.event
        if not self.timer:
            self.timer = self.frontend.register_timer(self.timer_handler,
                                                      start)
        else:
            self.frontend.reschedule_timer(self.timer, start)
    def timer_handler(self, ticks):
        return self.handler(ticks)
    def event(self, ticks):
        flags = Flags.ON if self.on_duration else Flags.OFF
        self._set_pin(flags)
        end_time = 0
        if flags == Flags.OFF or self.on_duration >= self.cycle_ticks:
            if (not int(flags)) != (not int(self.flags & Flags.DEFAULT_ON)) \
                and self.max_duration:
                end_time = ticks + self.max_duration
                flags |= Flags.CHECK_END
        else:
            self.flags |= Flags.TOGGLING
            if self.max_duration:
                end_time = ticks + self.max_duration
                flags |= Flags.CHECK_END
        # we are toggling
        self.end_time = end_time
        self.flags |= flags | (self.flags & Flags.DEFAULT_ON)
        if Flags.TOGGLING not in flags:
            if Flags.CHECK_END not in flags:
                return 0
            return end_time
        waketime = ticks + self.on_duration
        if Flags.CHECK_END in flags and waketime >= end_time:
            return end_time
        self.handler = self.toggling
        self.off_duration = self.cycle_ticks - self.on_duration
        return waketime
    def toggling(self, ticks):
        self.flags ^= Flags.ON
        self.flags ^= Flags.OFF
        self._set_pin(self.flags)
        waketime = ticks
        if Flags.ON in self.flags:
            waketime += self.on_duration
        else:
            waketime += self.off_duration
        if Flags.CHECK_END in self.flags and waketime >= self.end_time:
            self.handler = self.event
            waketime = self.end_time
        return waketime
    def shutdown(self):
        if self.timer:
            self.frontend.unregister_timer(self.timer)
            self.timer = None
    def __del__(self):
        self.shutdown()

class HeaterPin(DigitalPin):
    def __init__(self, frontend, oid, obj_id, name):
        super().__init__(frontend, oid, obj_id, name)
        status = frontend.query([obj_id])[obj_id]
        self.heater_max_temp = status["max_temp"]
    def _set_pin(self, value):
        temp = self.heater_max_temp if Flags.ON in value else 0
        self.frontend.queue_command(ModuleTypes.HEATER, self.name,
                                    "set_temperature",
                                    {"temperature" : temp})

class StepperPinShift(enum.IntFlag):
    ENABLE = 0
    DIR = 1
    STEP = 2

class StepperPins(enum.IntFlag):
    ENABLE = (1 << StepperPinShift.ENABLE)
    DIR = (1 << StepperPinShift.DIR)
    STEP = (1 << StepperPinShift.STEP)
    EN_DIR = (ENABLE | DIR)

class StepperEnablePin(DigitalPin):
    def __init__(self, frontend, oid, obj_id, name, word):
        super().__init__(frontend, oid, obj_id, name)
        self.word = word
    def _set_pin(self, value):
        if value:
            self.word.contents.value |= StepperPins.ENABLE
        else:
            self.word.contents.value &= ~StepperPins.ENABLE

StepperMove = namedtuple("StepperMove", ["interval", "count", "increment", "dir"])

class CurrentMove:
    def __init__(self, interval, count, increment, dir):
        self.interval, self.count, self.increment, self.dir = \
            interval, count, increment, dir
        self.next_step_time = 0

class Stepper:
    POSITION_BIAS = 0x40000000
    def __init__(self, frontend, oid, obj_id, name, invert_step, step_pulse):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.name = name
        self.invert = invert_step
        self.step_pulse = step_pulse
        status = self.frontend.query([obj_id])[obj_id]
        self.pins = {"enable": status.get("enable_pin"),
                     "dir": status.get("dir_pin"),
                     "step": status.get("step_pin")}
        self.oid_handlers = {}
        self.move_queue = []
        self.next_dir = 0
        self.timer = self.frontend.register_timer(self.send_step, 0)
        # Klipper keeps it's own position value calculated using
        # the step counts
        self._position = -self.POSITION_BIAS
        self.move = None
        self.clock_reset = 0
        cmd_id = self.frontend.queue_command(ModuleTypes.STEPPER,
                                             self.name, "use_pins",
                                             {"enable": True})
        result = self.frontend.wait_for_command(cmd_id)[0]
        if result < 0:
            raise ValueError
        else:
            self.pin_word = ctypes.cast(result, ctypes.POINTER(ctypes.c_uint8))
    def owns_pin(self, pin):
        return pin in self.pins.values()
    def configure_pin(self, oid, pin):
        for name, obj_pin in self.pins.items():
            if pin != obj_pin:
                continue
            if name == "enable":
                pin = StepperEnablePin(self.frontend, oid, self.id, self.name, self.pin_word)
        setattr(self, f"{name}_pin", pin)
        return pin
    @property
    def position(self):
        position = self._position
        if self.move:
            position -= int(self.move.count / 2)
        return (position * (-1 if position & 0x80000000 else 1)) - self.POSITION_BIAS
    def set_stop_on_trigger(self, trsync):
        trsync.add_signal(self.stop_moves)
    def set_next_move_dir(self, dir):
        self.next_dir =  dir
    def next_move(self):
        if self.move_queue:
            move = self.move_queue.pop()
            interval = move.interval + move.increment
            move_dir = self.move.dir if self.move else self.next_dir
            if move_dir != move.dir:
                self._position = -self._position + move.count
                self.pin_word.contents.value ^= StepperPins.DIR
            else:
                self._position += move.count
            next_step_time = self.move.next_step_time if self.move else 0
            self.move = CurrentMove(interval, move.count * 2,
                                    move.increment, move.dir)
            self.move.next_step_time = next_step_time + move.interval
            return self.move.next_step_time
        return 0
    def queue_move(self, interval, count, add):
        if not count:
            self.frontend.shutdown("Invalid count parameter")
            return
        move = StepperMove(interval, count, add, self.next_dir)
        self.move_queue.append(move)
        if not self.move:
            timeout = self.next_move()
            self.frontend.reschedule_timer(self.timer, timeout)
    def stop_moves(self, reason):
        self.move_queue.clear()
        self.move = None
        self.frontend.reschedule_timer(self.timer, 0)
        self._position -= self.position
    def calc_step_time(self):
        if self.clock_reset:
            wake = self.clock_reset
            self.clock_reset = 0
            return wake
        if not self.move:
            return 0
        ticks = self.frontend.get_controller_clock_ticks()
        self.move.count -= 1
        min_step = ticks + self.step_pulse
        if self.move.count & 1:
            return min_step
        if self.move.count:
            self.move.next_step_time += self.move.interval
            self.move.interval += self.move.increment
            if self.move.next_step_time < min_step:
                return min_step
            return self.move.next_step_time
        timeout = self.next_move()
        if not timeout or timeout > min_step:
            return timeout
        #if timeout - min_step < -(ticks)
        return min_step
    def send_step(self, ticks):
        self.pin_word.contents.value ^= StepperPins.STEP
        return self.calc_step_time()
    def reset_clock(self, clock):
        self.clock_reset = clock
    def shutdown(self):
        if self.timer:
            self.frontend.unregister_timer(self.timer)
    def __del__(self):
        self.shutdown()

# Ideally, we'd want to use the endstop's ENDSTOP_TRIGGER
# event. However, Klipper wants the endstop pin valus to
# match for a certain sample count before triggering.
class EndstopPin:
    def __init__(self, frontend, oid, obj_id, name):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.name = name
        self.timer = None
        self.sample_time = 0
        self.sample_count = 0
        self.rest_time = 0
        self.trigger_count = 0
        self.trigger_reason = 0
        self.nextwake = 0
        self.trsync = None
        self.is_homing = False
    def home(self, clock, sample_ticks, sample_count, rest_ticks,
             pin_value, trsync, trigger_reason):
        if not sample_count:
            if self.timer:
                self.frontend.reschedule_timer(self.timer, 0)
            self.is_homing = False
            return
        self.sample_time = sample_ticks
        self.sample_count = sample_count
        self.rest_time = rest_ticks
        self.trigger_count = self.sample_count
        self.trigger_reason = trigger_reason
        self.trsync = trsync
        if not self.timer:
            self.timer = self.frontend.register_timer(self.event, clock)
        else:
            self.frontend.reschedule_timer(self.timer, clock)
    def _get_status(self):
        status = self.frontend.query_object([self.id])[self.id]
        return status["triggered"]
    def event(self, ticks):
        triggered = self._get_status()
        if not triggered:
            self.nextwake = ticks + self.rest_time
            self.trigger_count = self.sample_count
            return ticks + self.rest_time
        count = self.trigger_count - 1
        if not count:
            self.trsync.trigger(self.trigger_reason)
            return 0
        self.trigger_count = count
        return ticks + self.sample_time
    def get_state(self):
        return {"homing": self.is_homing, "next_clock" : self.nextwake,
                "pin_value": self._get_status()}
    def shutdown(self):
        if self.timer:
            self.frontend.unregister_timer(self.timer)
            self.timer = None
    def __del__(self):
        self.shutdown()

class TRSyncFlags(enum.IntFlag):
    ZERO = 0
    CAN_TRIGGER = enum.auto()

class TRSync:
    def __init__(self, frontend, oid):
        self.frontend = frontend
        self.id = -1
        self.oid = oid
        self.report_timer = None
        self.expire_timer = None
        self.triger_reason = 0
        self.expire_reason = 0
        self.report_ticks = 0
        self.signals = []
        self.flags = TRSyncFlags.ZERO
        self.report_timer = self.frontend.register_timer(self.report_handler, 0)
        self.expire_timer = self.frontend.register_timer(self.trigger_handler, 0)
    def _clear(self):
        self.frontend.reschedule_timer(self.report_timer, 0)
        self.frontend.reschedule_timer(self.expire_timer, 0)
        self.signals.clear()
        self.flags = TRSyncFlags.ZERO
        self.trigger_reason = self.expire_reason = 0
    def start(self, report_clock, report_ticks, expire_reason):
        self._clear()
        self.flags = TRSyncFlags.CAN_TRIGGER
        self.report_ticks = report_ticks
        self.expire_reason = expire_reason
        if self.report_ticks:
            self.frontend.reschedule_timer(self.report_timer, report_clock)
    def set_timeout(self, timeout):
        if TRSyncFlags.CAN_TRIGGER in self.flags:
                self.frontend.reschedule_timer(self.expire_timer, timeout)
    def add_signal(self, handler):
        self.signals.append(handler)
    def do_report(self, ticks, reason=None):
        if reason is None:
            reason = self.trigger_reason
        self.frontend.respond(ResponseTypes.RESPONSE,
                              KLIPPER_PROTOCOL.trsync.trsync_state,
                              oid=self.oid,
                              can_trigger=(TRSyncFlags.CAN_TRIGGER in self.flags),
                              trigger_reason=reason, clock=ticks)
    def do_trigger(self, reason):
        if TRSyncFlags.CAN_TRIGGER in self.flags:
            self.flags &= ~TRSyncFlags.CAN_TRIGGER
            self.trigger_reason = reason
            for signal in self.signals:
                signal(reason)
            self.signals.clear()
    def trigger(self, reason):
        self.do_trigger(reason)
        self.frontend.reschedule_timer(self.report_timer, 0)
        self.frontend.reschedule_timer(self.expire_timer, 0)
        self.do_report(0)
    def report_handler(self, ticks):
        self.do_report(ticks)
        return ticks + self.report_ticks
    def trigger_handler(self, ticks):
        self.do_trigger(self.expire_reason)
        self.do_report(ticks, self.expire_reason)
        return 0
    def shutdown(self):
        self.frontend.unregister_timer(self.expire_timer)
        self.frontend.unregister_timer(self.report_timer)
        self.report_timer = self.expire_timer = None
    def __del__(self):
        self.shutdown()

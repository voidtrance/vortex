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
import enum
import ctypes
import vortex.lib.logging as logging
import vortex.core.lib.atomics as atomics
from collections import namedtuple
from vortex.controllers.types import ModuleTypes
from vortex.frontends.klipper.klipper_proto import ResponseTypes, KLIPPER_PROTOCOL

__all__ = ["AnalogPin", "DigitalPin", "HeaterPin", "EndstopPin",
           "Stepper", "TRSync"]

class Logger:
    def __init__(self, name, oid):
        self._name, self._oid = name, oid
    def __getattr__(self, name):
        if name not in ("debug", "info", "warning", "error",
                        "error", "critical"):
            return getattr(self, name)
        func = getattr(logging, name)
        prefix = f"{self._name}[{self._oid}] "
        #return lambda f, *a, **k: func(prefix + f, *a, **k)
        return lambda f, *a, **k: print(prefix + f.format(*a, **k))

class AnalogPin:
    def __init__(self, frontend, oid, obj_id, klass, name):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.klass = klass
        self.name = name
        self.timer = None
        self._log = Logger(name, oid)
        self.timer = self.frontend.timers.new()
        self.timer.callback = self.handler
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
        self.timer.timeout = self.query_time
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
        try:
            del self.timer
        except NameError:
            pass
    def __del__(self):
        self.shutdown()

class Flags(enum.IntFlag):
    ON = enum.auto()
    TOGGLING = enum.auto()
    CHECK_END = enum.auto()
    DEFAULT_ON = enum.auto()

class DigitalPin:
    class Cycle:
        def __init__(self, waketime, duration):
            self.waketime = waketime
            self.duration = duration
    def __init__(self, frontend, oid, obj_id, name):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.name = name
        self.end_time = 0
        self.flags = 0
        self.max_duration = 0
        self.handler = self.event
        self.timer = self.frontend.timers.new()
        self.timer.callback = self.timer_handler
        self.waketime = 0
        self.cycle_ticks = 0
        self._log = Logger(name, oid)
        self._cycles = []
    def _set_pin(self, value):
        self.frontend.queue_command(ModuleTypes.DIGITAL_PIN,
                                    self.name, "set", {"state": int(value)})
    def set_initial_value(self, value, default):
        #self._log.debug(f"value: {value}, default: {default}")
        self.flags = (Flags.ON if value else 0)
        if default:
            self.flags |= Flags.DEFAULT_ON
        self._log.debug(f"flags: {self.flags!r}")
        self._set_pin(self.flags & Flags.ON)
    def set_max_duration(self, duration):
        self.max_duration = duration
    def set_cycle_ticks(self, ticks):
        self.cycle_ticks = ticks
    def schedule_cycle(self, start, ticks_on):
        c = self.Cycle(start, ticks_on)
        self._cycles.append(c)
        self._log.debug(f"len: {len(self._cycles)}, start: {start}, on: {ticks_on}")
        if len(self._cycles) > 1:
            return
        self.end_time = start
        self.flags |= Flags.CHECK_END
        self._log.debug(f"flags: {self.flags!r}")
        if not (self.flags & Flags.TOGGLING and \
                self.frontend.timers.is_before(self.waketime, start)):
            self.handler = self.event
            self.waketime = start
            self.timer.timeout = start
    def update(self, value):
        self.timer.timeout = 0
        flags = Flags.ON if value else 0
        self._set_pin(flags)
        if (not int(flags)) != (not int(self.flags & Flags.DEFAULT_ON)) and self.max_duration:
            self.handler = self.event
            self.flags = (self.flags & Flags.DEFAULT_ON) | flags | Flags.CHECK_END
            self.timer.timeout = self.end_time = \
                self.frontend.get_controller_clock_ticks() + self.max_duration
        else:
            self.flags = (self.flags & Flags.DEFAULT_ON) | flags
    def timer_handler(self, ticks):
        return self.handler(ticks)
    def event(self, ticks):
        self._log.debug(f"[{ticks}] len: {len(self._cycles)}, flags: {self.flags!r}")
        if len(self._cycles) == 0:
            self.frontend.shutdown("Missed scheduling of next digital out event")
            return 0
        cycle = self._cycles.pop(0)
        flags = Flags.ON if cycle.duration else 0
        self._set_pin(flags)
        end_time = 0
        self._log.debug(f"flags: {flags!r}, duration: {cycle.duration}, cycle_ticks: {self.cycle_ticks}")
        if int(flags) == 0 or cycle.duration >= self.cycle_ticks:
            if (not int(flags)) != (not int(self.flags & Flags.DEFAULT_ON)) \
                and self.max_duration:
                end_time = self.waketime + self.max_duration
                flags |= Flags.CHECK_END
        else:
            flags |= Flags.TOGGLING
            if self.max_duration:
                end_time = self.waketime + self.max_duration
                flags |= Flags.CHECK_END
        self._log.debug(f"flags: {flags!r}")
        if len(self._cycles):
            _cycle = self._cycles[0]
            if Flags.CHECK_END in flags and self.frontend.timers.is_before(end_time, _cycle.waketime):
                self.frontend.shutdown("Scheduled digital out event will exceed max duration")
                return 0
            end_time = _cycle.waketime
            flags |= Flags.CHECK_END
        # we are toggling
        self.end_time = end_time = self.frontend.timers.to_time(end_time)
        self.flags = flags | (self.flags & Flags.DEFAULT_ON)
        self._log.debug(f"flags: {flags!r}, end_time: {end_time}")
        if not (Flags.TOGGLING & flags):
            if not (Flags.CHECK_END & flags):
                return 0
            self.waketime = self.end_time
            return self.end_time
        waketime = self.waketime + cycle.duration
        if Flags.CHECK_END & flags and self.frontend.timers.is_after(waketime, end_time):
            self.waketime = self.end_time
            return self.end_time
        self.handler = self.toggling
        self.waketime = self.frontend.timers.to_time(waketime)
        self.on_duration = cycle.duration
        self.off_duration = self.cycle_ticks - cycle.duration
        return self.waketime
    def toggling(self, ticks):
        self._log.debug(f"[{ticks}] flags: {self.flags!r}, waketime: {self.waketime}, end_time: {self.end_time}")
        self.flags ^= Flags.ON
        self._set_pin(self.flags)
        waketime = self.waketime
        if Flags.ON in self.flags:
            waketime += self.on_duration
        else:
            waketime += self.off_duration
        self._log.debug(f"waketime: {waketime}, end_time: {self.end_time}")
        if Flags.CHECK_END & self.flags and self.frontend.timers.is_after(waketime, self.end_time):
            self.handler = self.event
            waketime = self.end_time
        self.waketime = self.frontend.timers.to_time(waketime)
        return waketime
    def shutdown(self):
        try:
            del self.timer
        except NameError:
            pass
    def __del__(self):
        self.shutdown()


class HeaterPin(DigitalPin):
    def __init__(self, frontend, oid, obj_id, name):
        super().__init__(frontend, oid, obj_id, name)
        status = frontend.query([obj_id])[obj_id]
        self.heater_max_temp = status["max_temp"]
        cmd_id = self.frontend.queue_command(ModuleTypes.HEATER,
                                             self.name, "use_pins",
                                             {"enable": True})
        result = self.frontend.wait_for_command(cmd_id)[0]
        if result < 0:
            raise ValueError(f"Heater {self.name} pin enable error")
        status = self.frontend.query_object([self.id])[self.id]
        self.pin_word = ctypes.cast(status["pin_addr"], ctypes.POINTER(ctypes.c_uint8))
    def _set_pin(self, value):
        self.pin_word.contents.value = int(not (not (Flags.ON & value)))

class StepperPinShift(enum.IntEnum):
    STEPS = 16
    DIR = 30
    ENABLE = 31

class StepperPins(enum.IntFlag):
    ENABLE = (1 << StepperPinShift.ENABLE)
    DIR = (1 << StepperPinShift.DIR)

class StepperMasks(enum.IntEnum):
    STEPS = (1 << StepperPinShift.STEPS) - 1
    CONTROL = ~((1 << StepperPinShift.STEPS) - 1)
    EN_DIR = (StepperPins.ENABLE | StepperPins.DIR)

class StepperEnablePin(DigitalPin):
    def __init__(self, frontend, oid, obj_id, name, word):
        super().__init__(frontend, oid, obj_id, name)
        self.word = word
    def _set_pin(self, value):
        if value:
            self.word |= StepperPins.ENABLE
        else:
            self.word &= ~StepperPins.ENABLE

StepperMove = namedtuple("StepperMove", ["interval", "count", "increment", "dir"])

class CurrentMove:
    def __init__(self, interval, count, increment, dir):
        self.interval, self.count, self.increment, self.dir = \
            interval, count, increment, dir
        self.next_step_time = 0

class Stepper:
    def __init__(self, frontend, oid, obj_id, name, invert_step, step_pulse):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.name = name
        self._log = Logger(name, oid)
        self.invert = invert_step
        self.step_pulse = step_pulse
        status = self.frontend.query([obj_id])[obj_id]
        self.pins = {"enable": status.get("enable_pin"),
                     "dir": status.get("dir_pin"),
                     "step": status.get("step_pin")}
        self.oid_handlers = {}
        self.move_queue = []
        self.next_dir = 0
        self.timer = self.frontend.timers.new()
        self.timer.callback = self.send_step
        self._needs_reset = False
        self.move = CurrentMove(0, 0, 0, 0)
        self._step_sched = 0
        self._position = 0
        cmd_id = self.frontend.queue_command(ModuleTypes.STEPPER,
                                             self.name, "use_pins",
                                             {"enable": True})
        result = self.frontend.wait_for_command(cmd_id)[0]
        if result < 0:
            raise ValueError(f"Stepper {self.name} pin enable error")
        status = self.frontend.query_object([self.id])[self.id]
        self.pin_word = atomics.Atomic(32, var=status["pin_addr"])
    def owns_pin(self, pin):
        return pin in self.pins.values()
    def configure_pin(self, oid, pin):
        for name, obj_pin in self.pins.items():
            if pin != obj_pin:
                continue
            if name == "enable":
                pin = StepperEnablePin(self.frontend, oid, self.id, self.name,
                                       self.pin_word)
        setattr(self, f"{name}_pin", pin)
        return pin
    @property
    def position(self):
        status = self.frontend.query_object([self.id])[self.id]
        return status['steps']
    def set_stop_on_trigger(self, trsync):
        trsync.add_signal(self.stop_moves)
    def set_next_move_dir(self, dir):
        self.next_dir =  dir
    def queue_move(self, interval, count, add):
        if self._needs_reset:
            return
        if not count:
            self.frontend.shutdown("Invalid count parameter")
            return
        move = StepperMove(interval, count, add, self.next_dir)
        self.move_queue.append(move)
        if self.move.count == 0:
            timeout = self._next_move()
            self._step_sched = timeout
            self.timer.timeout = timeout
    def stop_moves(self, reason):
        self.timer.timeout = 0
        self.move.count = 0
        self.move_queue.clear()
        self.pin_word &= ~StepperPins.DIR
        self._needs_reset = True
    def _next_move(self):
        if self.move_queue:
            move = self.move_queue.pop(0)
            interval = move.interval + move.increment
            if self.move.dir != move.dir:
                self.pin_word ^= StepperPins.DIR ^ self.invert
            next_step_time = self.move.next_step_time
            self.move = CurrentMove(interval, move.count,
                                    move.increment, move.dir)
            self._position += self.move.count * (-1 + 2 * self.move.dir)
            self.move.next_step_time = \
                self.frontend.timers.to_time(next_step_time + move.interval)
            return self.move.next_step_time
        return 0
    def _calc_step_time(self, ticks):
        min_step = ticks + self.step_pulse
        if self.move.count:
            self.move.next_step_time = \
                self.frontend.timers.to_time(self.move.next_step_time + self.move.interval)
            self.move.interval += self.move.increment
            if self.frontend.timers.is_before(self.move.next_step_time, min_step):
                return min_step
            return self.move.next_step_time
        timeout = self._next_move()
        if not timeout or self.frontend.timers.is_after(timeout, min_step):
            return timeout
        #if timeout - min_step < -(ticks)
        return min_step
    def send_step(self, ticks):
        self.pin_word.inc()
        self.move.count -= 1
        next_step = self._calc_step_time(ticks)
        return next_step
    def reset_clock(self, clock):
        self.move.next_step_time = clock
        self._needs_reset = False
    def shutdown(self):
        try:
            del self.timer
        except NameError:
            pass
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
        status = frontend.query_object([self.id])[self.id]
        self.pin_word = ctypes.cast(status["pin_addr"], ctypes.POINTER(ctypes.c_uint8))
        self._log = Logger(name, oid)
        self.timer = self.frontend.timers.new()
        self.timer.callback = self._event
    def home(self, clock, sample_ticks, sample_count, rest_ticks,
             pin_value, trsync, trigger_reason):
        self.timer.timeout = 0
        self.sample_time = sample_ticks
        self.sample_count = sample_count
        if not sample_count:
            self.is_homing = False
            return
        self.rest_time = rest_ticks
        self.trigger_count = self.sample_count
        self.trigger_reason = trigger_reason
        self.trsync = trsync
        self.is_homing = True
        self.handler = self._event_sample
        self.timer.timeout = clock
    def _get_status(self):
        return self.pin_word.contents.value & 1
    def _event(self, ticks):
        return self.handler(ticks)
    def _event_sample(self, ticks):
        triggered = self._get_status()
        if not triggered:
            return ticks + self.rest_time
        self.nextwake = ticks + self.rest_time
        self.handler = self._event_oversample
        return self._event_oversample(ticks)
    def _event_oversample(self, ticks):
        triggered = self._get_status()
        if not triggered:
            self.handler = self._event_sample
            self.trigger_count = self.sample_count
            return self.nextwake
        count = self.trigger_count - 1
        if not count:
            self.trsync.do_trigger(self.trigger_reason)
            return 0
        self.trigger_count = count
        return ticks + self.sample_time
    def get_state(self):
        return {"homing": self.is_homing, "next_clock" : self.nextwake,
                "pin_value": self._get_status()}
    def shutdown(self):
        try:
            del self.timer
        except NameError:
            pass
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
        self.triger_reason = 0
        self.expire_reason = 0
        self.report_ticks = 0
        self.signals = []
        self.flags = TRSyncFlags.ZERO
        self._log = Logger("TRSync", oid)
        self.report_timer = self.frontend.timers.new()
        self.report_timer.callback = self.report_handler
        self.expire_timer = self.frontend.timers.new()
        self.expire_timer.callback = self.expire_handler
    def _clear(self):
        self.report_timer.timeout = 0
        self.expire_timer.timeout = 0
        self.signals.clear()
        self.flags = TRSyncFlags.ZERO
        self.trigger_reason = self.expire_reason = 0
    def start(self, report_clock, report_ticks, expire_reason):
        self._clear()
        self.flags = TRSyncFlags.CAN_TRIGGER
        self.report_ticks = report_ticks
        self.expire_reason = expire_reason
        if self.report_ticks:
            self.report_timer.timeout = report_clock
    def set_timeout(self, timeout):
        if TRSyncFlags.CAN_TRIGGER in self.flags:
                self.expire_timer.timeout = timeout
    def add_signal(self, handler):
        self.signals.append(handler)
    def report(self, ticks, reason=None):
        if reason is None:
            reason = self.trigger_reason
        self.frontend.respond(ResponseTypes.RESPONSE,
                              KLIPPER_PROTOCOL.trsync.trsync_state,
                              oid=self.oid,
                              can_trigger=int(TRSyncFlags.CAN_TRIGGER in self.flags),
                              trigger_reason=reason, clock=ticks)
    def do_trigger(self, reason):
        if TRSyncFlags.CAN_TRIGGER not in self.flags:
            return
        self.flags &= ~TRSyncFlags.CAN_TRIGGER
        self.trigger_reason = reason
        for signal in self.signals:
            signal(reason)
        self.signals.clear()
        self.report(self.frontend.get_controller_clock_ticks())
    def trigger(self, reason):
        self.do_trigger(reason)
        self.report_timer.timeout = 0
        self.expire_timer.timeout = 0
    def report_handler(self, ticks):
        self.report(ticks)
        return ticks + self.report_ticks
    def expire_handler(self, ticks):
        self.do_trigger(self.expire_reason)
        return 0
    def shutdown(self):
        try:
            del self.report_timer
            del self.expire_timer
        except NameError:
            pass
    def __del__(self):
        self.shutdown()
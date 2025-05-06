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
from threading import Lock
import vortex.lib.logging as logging
import vortex.core.lib.atomics as atomics
from collections import namedtuple
from vortex.core import ObjectTypes
from vortex.frontends.klipper.klipper_proto import ResponseTypes, KLIPPER_PROTOCOL

__all__ = ["AnalogPin", "DigitalPin", "HeaterPin", "EndstopPin",
           "Stepper", "TRSync", "Buttons"]

class MoveQueue:
    def __init__(self, size):
        self._size = size
        self._queue = []
        self._lock = Lock()
    def put(self, item):
        with self._lock:
            self._queue.append(item)
    def get(self):
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
            return None
    def clear(self):
        with self._lock:
            self._queue.clear()

class HelperBase:
    def __init__(self, frontend, oid, obj_id, klass, name=""):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.klass = klass
        self.name = name
    def shutdown(self):
        if hasattr(self, "timer"):
            self.timer.remove()
            del self.timer
    def __del__(self):
        self.shutdown()

class AnalogPin(HelperBase):
    def __init__(self, frontend, oid, obj_id, klass, name):
        super().__init__(frontend, oid, obj_id, klass, name)
        self.timer = None
        self._log = logging.getLogger(f"vortex.frontend.analog.{name}")
        self._log.add_prefix(f"[{oid}]")
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

class Flags(enum.IntFlag):
    ON = enum.auto()
    TOGGLING = enum.auto()
    CHECK_END = enum.auto()
    DEFAULT_ON = enum.auto()

class DigitalPin(HelperBase):
    class Cycle:
        def __init__(self, waketime, duration):
            self.waketime = waketime
            self.duration = duration
    def __init__(self, frontend, oid, obj_id, klass, name):
        super().__init__(frontend, oid, obj_id, klass, name)
        self.end_time = 0
        self.flags = 0
        self.max_duration = 0
        self.handler = self.event
        self.timer = self.frontend.timers.new()
        self.timer.callback = self.timer_handler
        self.waketime = 0
        self.cycle_ticks = 0
        self._log = logging.getLogger(f"vortex.frontend.digital.{name}")
        self._log.add_prefix(f"[{oid}]")
        self._cycles = []
    def _set_pin(self, value):
        self.frontend.queue_command(ObjectTypes.DIGITAL_PIN,
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
            if Flags.CHECK_END & flags and self.frontend.timers.is_before(end_time, _cycle.waketime):
                self.frontend.shutdown("Scheduled digital out event will exceed max duration")
                return 0
            end_time = _cycle.waketime
            flags |= Flags.CHECK_END
        # we are toggling
        self.end_time = end_time = end_time
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
        self.waketime = waketime
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
        self.waketime = waketime
        return waketime

class HeaterPin(DigitalPin):
    def __init__(self, frontend, oid, obj_id, klass, name):
        super().__init__(frontend, oid, obj_id, klass, name)
        status = frontend.query([obj_id])[obj_id]
        self.heater_max_temp = status["max_temp"]
        cmd_id = self.frontend.queue_command(ObjectTypes.HEATER,
                                             self.name, "use_pins",
                                             {"enable": True})
        result = self.frontend.wait_for_command(cmd_id)[0]
        if result < 0:
            raise ValueError(f"Heater {self.name} pin enable error")
        status = self.frontend.query_object([self.id])[self.id]
        self.pin_word = ctypes.cast(status["pin_addr"], ctypes.POINTER(ctypes.c_uint8))
    def _set_pin(self, value):
        self.pin_word.contents.value = int(not (not (Flags.ON & value)))
    def shutdown(self):
        self._set_pin(not (not int(Flags.DEFAULT_ON & self.flags)))
        super().shutdown()

class StepperPinShift(enum.IntEnum):
    STEPS = 16
    DEBUG = 29
    DIR = 30
    ENABLE = 31

class StepperPins(enum.IntFlag):
    ENABLE = (1 << StepperPinShift.ENABLE)
    DIR = (1 << StepperPinShift.DIR)
    DEBUG = (1 << StepperPinShift.DEBUG)

class StepperMasks(enum.IntEnum):
    STEPS = (1 << StepperPinShift.STEPS) - 1
    CONTROL = ~((1 << StepperPinShift.STEPS) - 1)
    EN_DIR = (StepperPins.ENABLE | StepperPins.DIR)

class StepperEnablePin(DigitalPin):
    def __init__(self, frontend, oid, obj_id, klass, name, word):
        super().__init__(frontend, oid, obj_id, klass, name)
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
        self.active = False
    def __repr__(self):
        return f"interval={self.interval}, count={self.count}, increment={self.increment}, dir={self.dir}"

class Stepper(HelperBase):
    def __init__(self, frontend, oid, obj_id, klass, name):
        super().__init__(frontend, oid, obj_id, klass, name)
        self._log = logging.getLogger(f"vortex.frontend.stepper.{name}")
        self._log.add_prefix(f"[{oid}]")
        status = self.frontend.query([obj_id])[obj_id]
        self.pins = {"enable": status.get("enable_pin"),
                     "dir": status.get("dir_pin"),
                     "step": status.get("step_pin")}
        self.oid_handlers = {}
        self.move_queue = MoveQueue(self.frontend._queue.max_size)
        self.next_dir = 0
        self.next_step_time = 0
        self.timer = self.frontend.timers.new()
        self.timer.callback = self.send_step
        self._needs_reset = False
        self.move = CurrentMove(0, 0, 0, 0)
        cmd_id = self.frontend.queue_command(ObjectTypes.STEPPER,
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
                pin = StepperEnablePin(self.frontend, oid, self.id, self.klass,
                                       self.name, self.pin_word)
                setattr(self, f"{name}_pin", pin)
                return pin
        return None
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
        self.move_queue.put(move)
        if not self.move.active:
            timeout = self._next_move(0)
            self.timer.timeout = timeout
    def stop_moves(self, time, reason):
        self._needs_reset = True
        self.next_step_time = 0
        self.timer.timeout = 0
        self.move.count = 0
        self.move.active = False
        self.move_queue.clear()
    def _change_direction(self, dir):
        # Only switch direction if the current set of
        # steps have been finished by the stepper.
        while self.pin_word.value & StepperMasks.STEPS:
            continue
        self.pin_word ^= StepperPins.DIR
        # Wait for the stepper to acknowledge the direction change
        while (self.pin_word.value >> StepperPinShift.DIR) & 0x1 != dir:
            continue
    def _next_move(self, ticks):
        move = self.move_queue.get()
        if not move:
            self.move.active = False
            return 0
        if self.move.dir != move.dir:
            self._change_direction(move.dir)
        self.move.active = True
        self.move.interval = move.interval + move.increment
        self.move.count = move.count
        self.move.increment = move.increment
        self.move.dir = move.dir
        self.next_step_time = self.frontend.timers.to_time(self.next_step_time + move.interval)
        self._log.debug(f"ticks={ticks}, move_next_step={self.next_step_time}, interval={move.interval}")
        return self.next_step_time
    def _calc_step_time(self, ticks):
        if self.move.count:
            self.next_step_time = self.frontend.timers.to_time(self.next_step_time + self.move.interval)
            self.move.interval += self.move.increment
            return self.next_step_time
        return self._next_move(ticks)
    def _do_step(self):
        self.move.count -= 1
        self.pin_word.inc()
    def send_step(self, ticks):
        self._do_step()
        next_step = self._calc_step_time(ticks)
        # A drift can occur in step timing due to the impresise
        # nature of the simulated controller clock.
        # The core of the issue is that controller clock ticks
        # are updated based on elapsed wall clock time.
        # For controllers running at high enough frequencies, this
        # results in the clock ticks jumping instead of incrementing
        # by 1.
        # Therefore, a timer callback can be called with a ticks
        # value that is past the timers wake up time. This "error"
        # accumulates slowly and results in step time error after
        # the clock has wrapped a sufficient number of times.
        # Furthermore, the next step cannot be calculated based of
        # the current tick value because that will throw off
        # Klipper's step calculation and Klipper will compute the
        # wrong axis position.
        while next_step != 0 and self.frontend.timers.is_before(next_step, ticks):
            self._do_step()
            next_step = self._calc_step_time(ticks)
        self._log.debug(f"ticks={ticks}, count={self.move.count}, next_step_time={self.next_step_time}, interval={self.move.interval}")
        return next_step
    def reset_clock(self, clock):
        self.next_step_time = clock
        self._needs_reset = False

# Ideally, we'd want to use the endstop's ENDSTOP_TRIGGER
# event. However, Klipper wants the endstop pin valus to
# match for a certain sample count before triggering.
class EndstopPin(HelperBase):
    def __init__(self, frontend, oid, obj_id, klass, name):
        super().__init__(frontend, oid, obj_id, klass, name)
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
        self.pin_word = atomics.Atomic(8, var=status["pin_addr"])
        self._log = logging.getLogger(f"vortex.frontend.endstop.{name}")
        self._log.add_prefix(f"[{oid}]")
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
        return self.pin_word.value & 1
    def _event(self, ticks):
        return self.handler(ticks)
    def _event_sample(self, ticks):
        if not self._get_status():
            return ticks + self.rest_time
        self.nextwake = ticks + self.rest_time
        self.handler = self._event_oversample
        return self._event_oversample(ticks)
    def _event_oversample(self, ticks):
        if not self._get_status():
            self.handler = self._event_sample
            self.trigger_count = self.sample_count
            return self.nextwake
        count = self.trigger_count - 1
        if not count:
            self.trsync.do_trigger(self.timer.timeout, self.trigger_reason)
            return 0
        self.trigger_count = count
        return ticks + self.sample_time
    def get_state(self):
        return {"homing": self.is_homing, "next_clock" : self.nextwake,
                "pin_value": self._get_status()}

class TRSyncFlags(enum.IntFlag):
    ZERO = 0
    CAN_TRIGGER = enum.auto()

class TRSync(HelperBase):
    def __init__(self, frontend, oid, obj_id, klass, name=""):
        super().__init__(frontend, oid, obj_id, klass, name)
        self.triger_reason = 0
        self.expire_reason = 0
        self.report_ticks = 0
        self.signals = []
        self.flags = TRSyncFlags.ZERO
        self._log = logging.getLogger(f"vortex.frontend.trsync.{oid}")
        self._log.add_prefix(f"[{oid}]")
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
        self._log.debug(f"{ticks}: reason={reason}, trigger_reason={self.triger_reason}")
        if reason is None:
            reason = self.trigger_reason
        self.frontend.respond(ResponseTypes.RESPONSE,
                              KLIPPER_PROTOCOL.trsync.trsync_state,
                              oid=self.oid,
                              can_trigger=int(TRSyncFlags.CAN_TRIGGER in self.flags),
                              trigger_reason=reason, clock=ticks)
    def do_trigger(self, ticks, reason):
        if TRSyncFlags.CAN_TRIGGER not in self.flags:
            return
        self.flags &= ~TRSyncFlags.CAN_TRIGGER
        self.trigger_reason = reason
        for signal in self.signals:
            signal(ticks, reason)
        self.signals.clear()
        self.report(ticks)
    def trigger(self, reason):
        self.report_timer.timeout = 0
        self.expire_timer.timeout = 0
        self.do_trigger(self.frontend.get_controller_clock_ticks(), reason)
    def report_handler(self, ticks):
        self.report(ticks)
        self._log.debug(f"next report: {ticks + self.report_ticks}")
        return ticks + self.report_ticks
    def expire_handler(self, ticks):
        self._log.debug(f"{ticks}: trsync expired")
        self.report_timer.timeout = 0
        self.do_trigger(ticks, self.expire_reason)
        return 0
    def shutdown(self):
        try:
            del self.report_timer
            del self.expire_timer
        except (NameError, AttributeError):
            pass

class ButtonsState(enum.IntEnum):
    NONE = 0
    NO_RETRANSMIT = 0x80
    PENDING = 0xff
    ACKED = 0xfe

class ButtonsTask:
    def __init__(self, respond):
        self.respond = respond
        self._button_sets = []
        self._cmd = None
    def register(self, buttons):
        if buttons not in self._button_sets:
            self._button_sets.append(buttons)
    def set_cmd(self, cmd):
        if self._cmd is None:
            self._cmd = cmd
    def report(self):
        for buttons in self._button_sets:
            if buttons._retransmit_state.value != ButtonsState.PENDING:
                continue
            buttons._retransmit_state.value = buttons._retransmit_count
            self.respond(ResponseTypes.RESPONSE, buttons._cmd,
                         oid=buttons.oid, ack_count=buttons._ack_count,
                         state=buttons._reports[:buttons._report_count])

buttons_task = None

class Buttons(HelperBase):
    def __init__(self, frontend, oid, obj_id, klass, name, count):
        global buttons_task
        super().__init__(frontend, oid, obj_id, klass, name)
        self._count = count
        self._buttons = [None] * self._count
        self._pressed = self._last_pressed = 0
        self._report_count = 0
        self._ack_count = 0
        self._reports = [0] * self._count
        self._retransmit_count = 0
        self._retransmit_state = ctypes.c_uint8(0)
        self._cmd = None
        self._state = ButtonsState.NONE
        self.timer = self.frontend.timers.new()
        self.timer.callback = self.event
        if buttons_task is None:
            buttons_task = ButtonsTask(self.frontend.respond)
            buttons_task.register(self)
    def add_button(self, position, button_id, klass, name, pull_up):
        if position >= self._count:
            self.frontend.shutdown("Set button past maximum button count")
            return False
        self._buttons[position] = button_id
        return True
    def query(self, cmd, clock, rest_ticks, retransmit_count, invert):
        self._cmd = cmd
        self._rest_ticks = rest_ticks
        self._retransmit_count = retransmit_count
        self._retransmit_state.value = int(ButtonsState.ACKED)
        self._invert = invert
        self.timer.timeout = clock
    def ack(self, count):
        self._ack_count += count
        if count >= self._report_count:
            self._report_count = 0
            self._retransmit_state.value = ButtonsState.ACKED
        else:
            self._reports[:count] = self._reports[count:]
            self._report_count -= count
    def event(self, ticks):
        states = self.frontend.query_object(self._buttons)
        status = 0
        for i, button in enumerate(self._buttons):
            if states[button]["state"]:
                status |= (1 << i)
        diff = status ^ self._pressed
        if diff:
            debounced = ~(status ^ self._last_pressed)
            if diff & debounced:
                self._pressed = (self._pressed & ~debounced) | (status & debounced)
                if self._report_count < self._count:
                    self._reports[self._report_count] = self._pressed
                    self._report_count += 1
                    self._retransmit_state.value = ButtonsState.PENDING
                    buttons_task.report()
        self._last_pressed = status
        if not (self._retransmit_state.value & ButtonsState.NO_RETRANSMIT):
            self._retransmit_state.value -= 1
            if self._retransmit_state.value & ButtonsState.NO_RETRANSMIT:
                buttons_task.report()
        return self.frontend.timers.to_time(ticks + self._rest_ticks)

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
from vortex.lib.ext_enum import ExtIntEnum, unique, auto
from vortex.controllers.types import ModuleTypes

class Flags(enum.IntFlag):
    OFF = auto()
    ON = auto()
    TOGGLING = auto()
    CHECK_END = auto()
    DEFAULT_ON = auto()

class DigitalPin:
    def __init__(self, frontend, oid, obj_id, klass, name):
        self.frontend = frontend
        self.oid = oid
        self.id = obj_id
        self.klass = klass
        self.name = name
        self.end_time = 0
        self.flags = Flags.OFF
        self.max_duration = 0
        self.handler = self.event
        self.timer = None
        if klass == ModuleTypes.HEATER:
            status = frontend.query([obj_id])[obj_id]
            self.heater_max_temp = status["max_temp"]
    def __set_pin(self, value):
        print(f"Setting {self.klass:s} {self.name} to {value!r}")
        if self.klass == ModuleTypes.HEATER:
            temp = self.heater_max_temp if Flags.ON in value else 0
            self.frontend.queue_command(self.klass, self.name,
                                     "set_temperature",
                                     {"temperature" : temp})
        else:
            self.frontend.queue_command(ModuleTypes.DIGITAL_PIN,
                                                 self.name, "set",
                                                 {"state": int(value)})
    def set_initial_value(self, value, default):
        self.flags = (Flags.ON if value else Flags.OFF) | \
            (Flags.DEFAULT_ON if default else Flags.OFF)
        self.__set_pin(self.flags & Flags.ON)
    def set_max_duration(self, duration):
        self.max_duration = duration
    def set_cycle_ticks(self, ticks):
        self.cycle_ticks = ticks
    def schedule_cycle(self, start, ticks_on):
        self.on_duration = ticks_on
        self.off_duration = self.cycle_ticks - ticks_on
        self.end_time = start
        self.flags |= Flags.CHECK_END
        self.handler = self.event
        if not self.timer:
            self.timer = self.frontend.register_timer(start,
                                                       self.timer_handler)
        else:
            self.frontend.reschedule_timer(self.timer, start)
    def timer_handler(self, ticks):
        return self.handler(ticks)
    def event(self, ticks):
        flags = Flags.ON if self.on_duration else Flags.OFF
        print(f"event: {ticks}, {self.flags!r}, {flags!r}")
        self.__set_pin(flags)
        end_time = 0
        if flags == Flags.OFF or self.on_duration >= self.cycle_ticks:
            print(f"{not int(flags)}, {not int(self.flags & Flags.DEFAULT_ON)}, {self.max_duration}")
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
        print(f"flags: {flags!r}")
        if Flags.TOGGLING not in flags:
            if Flags.CHECK_END not in flags:
                return 0
            return end_time
        waketime = ticks + self.on_duration
        print(waketime, end_time)
        if Flags.CHECK_END in flags and waketime >= end_time:
            return end_time
        self.handler = self.toggling
        return waketime
    def toggling(self, ticks):
        print(f"handling: {ticks}, {self.flags!r}")
        self.flags ^= Flags.ON
        self.flags ^= Flags.OFF
        self.__set_pin(self.flags)
        waketime = ticks
        if Flags.ON in self.flags:
            waketime += self.on_duration
        else:
            waketime += self.off_duration
        if Flags.CHECK_END in self.flags and waketime >= self.end_time:
            self.handler = self.event
            waketime = self.end_time
        return waketime
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
from vortex.frontends.klipper.klipper_proto import ResponseTypes

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
            self.timer = self.frontend.register_timer(self.query_time,
                                                 self.handler)
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
                #shutdown
                self.invalid_count = 0
        self.query_time = ticks + self.rest_ticks
        self.frontend.respond(ResponseTypes.RESPONSE, self.cmd, oid=self.oid,
                                   next_clock=self.query_time,
                                   value=value)
        return self.query_time
    
    def __del__(self):
        self.frontend.unregister_timer(self.timer)

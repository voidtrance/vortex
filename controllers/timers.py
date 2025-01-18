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

class Timer:
    def __init__(self, register, schedule, unregister, compare):
        self._callback = None
        self._timeout = 0
        self._register = register
        self._schedule = schedule
        self._unregister = unregister
        self._compare = compare
        self._handle = None

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self.schedule(value)

    @property
    def callback(self):
        return self._callback

    @callback.setter
    def callback(self, value):
        if not callable(value):
            raise TypeError("callback should be a callable object")
        self._callback = value

    def handler(self, time):
        self._timeout = self._callback(time)
        return self._timeout

    def schedule(self, timeout):
        self._timeout = timeout
        if self._callback is None:
            return
        if self._handle is None:
            self._handle = self._register(self.handler, self._timeout)
        else:
            self._schedule(self._handle, self._timeout)

    def is_before(self, other):
        return self < other

    def is_after(self, other):
        return self > other

    def __lt__(self, timer):
        if isinstance(timer, Timer):
            timer = timer.timeout
        return self._compare(self._timeout, timer) < 0

    def __gt__(self, timer):
        if isinstance(timer, Timer):
            timer = timer.timeout
        return self._compare(self._timeout, timer) > 0

    def __eq__(self, timer):
        if isinstance(timer, Timer):
            timer = timer.timeout
        return self._compare(self._timeout, timer) == 0

    def __ne__(self, timer):
        return not self == timer

    def __del__(self):
        if self._handle:
            self._unregister(self._handle)

class Factory:
    def __init__(self, controller):
        self._controller = controller
        self._controller_time_type = getattr(ctypes, f"c_uint{controller.ARCH}")

    def new(self):
        return Timer(self._controller.register_timer,
                     self._controller.reschedule_timer,
                     self._controller.unregister_timer,
                     self._controller.compare_timer)
    def to_time(self, value):
        c_value = self._controller_time_type(value)
        return c_value.value
    def is_before(self, t1, t2):
        tt1 = self.new()
        tt1.timeout = t1
        return tt1.is_before(t2)
    def is_after(self, t1, t2):
        tt1 = self.new()
        tt1.timeout = t1
        return tt1.is_after(t2)
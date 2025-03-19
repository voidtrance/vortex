# vortex - GCode machine emulator
# Copyright (C) 2024,2025  Mitko Haralanov
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
import vortex.core.lib.atomics._vortex_atomics as atomics

class Atomic:
    def __init__(self, size, value=0, var=None):
        self._ffi = atomics.ffi
        self._lib = atomics.lib
        if var is None:
            self._value = self._ffi.new(f"uint{size}_t *")
        else:
            self._value = self._ffi.cast(f"uint{size}_t *", var)
        self.__load = getattr(atomics.lib, f"atomic{size}_load")
        self.__store = getattr(atomics.lib, f"atomic{size}_store")
        self.__exchange = getattr(atomics.lib, f"atomic{size}_exchange")
        self.__cmpexg = getattr(atomics.lib, f"atomic{size}_compare_exchange")
        self.__add = getattr(atomics.lib, f"atomic{size}_add")
        self.__sub = getattr(atomics.lib, f"atomic{size}_sub")
        self.__inc = getattr(atomics.lib, f"atomic{size}_inc")
        self.__dec = getattr(atomics.lib, f"atomic{size}_dec")
        self.__and = getattr(atomics.lib, f"atomic{size}_and")
        self.__or = getattr(atomics.lib, f"atomic{size}_or")
        self.__xor = getattr(atomics.lib, f"atomic{size}_xor")
        self.__not = getattr(atomics.lib, f"atomic{size}_not")
        self.__store(self._value, value)
    @property
    def value(self):
        return self.__load(self._value)
    @value.setter
    def value(self, value):
        self.__store(self._value, value)
    def __call__(self):
        return self.value
    def __eq__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        return self.value == other
    def __iadd__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        self.__add(self._value, other)
        return self
    def __isub__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        self.__sub(self._value, other)
        return self
    def __ior__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        self.__or(self._value, other)
        return self
    def __iand__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        self.__and(self._value, other)
        return self
    def __ior__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        self.__or(self._value, other)
        return self
    def __ixor__(self, other):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        self.__xor(self._value, other)
        return self
    def __invert__(self):
        return self.__not(self._value)
    def inc(self):
        self.__inc(self._value)
    def dec(self):
        self.__dec(self._value)
    def exchange(self, value):
        if isinstance(other, Atomic):
            other = other.value
        if not isinstance(other, int):
            raise TypeError
        return self.__exchange(self._value, other)
    def cmpexg(self, expected, new):
        if isinstance(expected, Atomic):
            expected = expected.value
        if isinstance(new, Atomic):
            new = new.value
        if not isinstance(expected, int) or not isinstance(new, int):
            raise TypeError
        return self.__cmpexg(self._value, expected, new)
        

    



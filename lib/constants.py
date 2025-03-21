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
SEC2MSEC = 1000
SEC2USEC = SEC2MSEC * 1000
SEC2NSEC = SEC2USEC * 1000
KHZ2HZ = 1000
MHZ2HZ = KHZ2HZ * 1000
GHZ2HZ = MHZ2HZ * 1000
HZ2MSEC = 1000
HZ2USEC = HZ2MSEC * 1000
HZ2NSEC = HZ2USEC * 1000

def sec_to_msec(s):
    return s * SEC2MSEC

def sec_to_usec(s):
    return s * SEC2USEC

def sec_to_nsec(s):
    return s * SEC2NSEC

def hz_to_sec(hz):
    return 1 / hz

def hz_to_msec(hz):
    return SEC2MSEC / hz

def hz_to_usec(hz):
    return SEC2USEC / hz

def hz_to_nsec(hz):
    return SEC2NSEC / hz

def nsec_to_hz(ns):
    return 1 / (ns  / SEC2NSEC)
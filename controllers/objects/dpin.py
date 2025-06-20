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
import vortex.controllers.objects.vobj_base as vobj
from vortex.core import ObjectTypes, PIN_NAME_SIZE
import ctypes

class DigitalPinSetArgs(ctypes.Structure):
    _fields_ = [("state", ctypes.c_bool)]

class DigitalPinState(ctypes.Structure):
    _fields_ = [("state", ctypes.c_bool),
                ("pin", ctypes.c_char * PIN_NAME_SIZE)]

class DigitalPin(vobj.VirtualObjectBase):
    type = ObjectTypes.DIGITAL_PIN
    commands = [(0, "set", DigitalPinSetArgs, None, (0,))]
    state = DigitalPinState
    def __init__(self, *args):
        super().__init__(*args)
        self._state = False
    def exec_command(self, cmd_id, cmd, opts):
        ret = super().exec_command(cmd_id, cmd, opts)
        if ret:
            return ret
        self._state = bool(opts.get("state"))
        self.complete_command(cmd_id, 0)
    def get_status(self):
        return {"state" : self._state, "pin": self.config.pin}
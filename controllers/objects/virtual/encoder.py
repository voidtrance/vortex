# vortex - GCode machine emulator
# Copyright (C) 2025 Mitko Haralanov
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
import vortex.controllers.objects.virtual.base as vobj
from vortex.core import ObjectKlass, PIN_NAME_SIZE
import vortex.core.lib.logging as logging
import ctypes
import time

logger = logging.getLogger("vortex.core.objects.encoder")

class EncoderPulsesArgs(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32),
                ("direction", ctypes.c_uint8)]

class EncoderState(ctypes.Structure):
    _fields_ = [("pin_a", ctypes.c_char * PIN_NAME_SIZE),
                ("pin_b", ctypes.c_char * PIN_NAME_SIZE),
                ("state", ctypes.c_bool * 2)]

class Encoder(vobj.VirtualObjectBase):
    type = ObjectKlass.ENCODER
    commands = [(0, "pulses", EncoderPulsesArgs, None, (0,))]
    status = EncoderState
    def __init__(self, config, lookup, query, complete, submit):
        super().__init__(config, lookup, query, complete, submit)
        self.reset()
    def get_status(self):
        d = vars(self.config)
        d['state'] = self.state
        return d
    def exec_command(self, cmd_id, cmd, opts):
        rc = super().exec_command(cmd_id, cmd, opts)
        if rc:
            return rc
        for pulse in range(opts["count"] * 2):
            pin = list(self.state.keys())[(2 + opts["direction"] + pulse) % 2]
            self.state[pin] = not self.state[pin]
            # Simulate encoder pin phase offset.
            time.sleep(0.01)
        self._cmd_complete(cmd_id, 0)
    def reset(self):
        self.state = {self.config.pin_a: False, self.config.pin_b: False}
        return super().reset()

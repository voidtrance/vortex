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
import vortex.controllers.objects.virtual.base as vobj
from vortex.core import ObjectKlass
import vortex.core.lib.logging as logging
import ctypes

logger = logging.getLogger("vortex.core.objects.neopixel")

MAX_LED_COUNT = 1024

class NeopixelSetArgs(ctypes.Structure):
    _fields_ = [("index", ctypes.c_uint),
                ("color", ctypes.c_uint8 * 4)]

class NeopixelState(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint),
                ("type", ctypes.c_char * 4),
                ("colors", ctypes.c_uint8 * MAX_LED_COUNT)]
    
class Neopixel(vobj.VirtualObjectBase):
    type = ObjectKlass.NEOPIXEL
    commands = [(0, "set", NeopixelSetArgs, None, ([0,0,0,0],) * 4)]
    state = NeopixelState

    def __init__(self, *args):
        super().__init__(*args)
        if self.config.count > MAX_LED_COUNT:
            raise vobj.VirtualObjectError("LED count exceeds maximum supported")
        self.type = self.config.type
        self.color_data = [(0,) * len(self.type)] * self.config.count

    def get_status(self):
        status = super().get_status()
        status.update({"colors": self.color_data})
        return status
    
    def exec_command(self, cmd_id, cmd, opts):
        ret = super().exec_command(cmd_id, cmd, opts)
        if ret < 0:
            return ret
        self.color_data[opts["index"]] = opts["color"]
        logger.debug(f"Color data: {self.color_data}")
        self.complete_command(cmd_id, 0)
        return 0
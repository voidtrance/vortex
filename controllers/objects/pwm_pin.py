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
import vortex.controllers.objects.vobj_base as vobj
from vortex.controllers.types import ModuleTypes
from errno import *

class PWMPin(vobj.VirtualObjectBase):
    type = ModuleTypes.PWM_PIN
    commands = [(0, "set_cycle", ["cycle"], None)]
    def __init__(self, *args):
        super().__init__(*args)
        self._cycle = 0.0
    def exec_command(self, cmd_id, cmd, opts):
        ret = super().exec_command(cmd_id, cmd, opts)
        if ret:
            return ret
        cycle = float(opts.get("cycle"))
        if cycle <= 0. or cycle >= 100.:
            return -EINVAL
        self._cycle = cycle / 100
        self.complete_command(cmd_id, 0)
    def get_status(self):
        return {"cycle" : self._cycle}
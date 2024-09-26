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
from vortex.controllers.types import ModuleTypes, ModuleEvents
from vortex.emulator.kinematics import AxisType

class Toolhead(vobj.VirtualObjectBase):
    type = ModuleTypes.TOOLHEAD
    events = [ModuleEvents.TOOLHEAD_ORIGIN]
    def get_status(self):
        axes_ids = []
        axis_types = [AxisType[x.upper()] for x in self.config.axes]
        axes = self.lookup.object_by_klass(ModuleTypes.AXIS)
        status = self.query([x.id for x in axes])
        for axis in axes:
            if status[axis.id]["type"] in axis_types:
                axes_ids.append(axis.id)
        status = self.query(axes_ids)
        toolhead_status = dict.fromkeys([x.upper() for x in self.config.axes], None)
        for i, id in enumerate(axes_ids):
            toolhead_status[self.config.axes[i].upper()] = status[id]["position"]
        event_sent = getattr(self, "event_sent", False)
        if list(toolhead_status.values()) == [0.0] * len(toolhead_status.keys()):
            if not event_sent:
                self.event_submit(ModuleEvents.TOOLHEAD_ORIGIN,
                                  list(toolhead_status.values()))
                self.event_sent = True
        else:
            self.event_sent = False
        return toolhead_status

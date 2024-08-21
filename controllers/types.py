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
import vortex.lib.ext_enum
import vortex.core as cc

__core_objects = {n.upper(): (v, n) for v, n in cc.OBJECT_TYPE_NAMES.items()}
__virt_object_list = ["toolhead", "fan", "digital_pin"]
# Update the list of objects to include the virtual ones
__core_objects.update({n.upper(): (len(__core_objects) + i, n) \
                       for i, n in enumerate(__virt_object_list)})
ModuleTypes = vortex.lib.ext_enum.ExtIntEnum("ModuleTypes", __core_objects)
# Don't pollute the namespace
del __core_objects
del __virt_object_list

ModuleEvents = vortex.lib.ext_enum.ExtIntEnum(
    "ModuleEvents", {n.upper(): (v, n) for v, n in cc.OBJECT_EVENT_NAMES.items()})


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
import lib.ext_enum
import controllers.core as cc

ModuleTypes = lib.ext_enum.ExtIntEnum(
    "ModuleTypes", {n.upper(): (v, n) for v, n in cc.OBJECT_TYPE_NAMES.items()})

ModuleEvents = lib.ext_enum.ExtIntEnum(
    "ModuleEvents", {n.upper(): (v, n) for v, n in cc.OBJECT_EVENT_NAMES.items()})

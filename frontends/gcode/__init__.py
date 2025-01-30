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
import time
import vortex.lib.logging as logging
import vortex.frontends.lib
import vortex.frontends.gcode.gcmd as gcmd
import vortex.lib.constants as constants
import vortex.lib.ext_enum as enum
from vortex.frontends import BaseFrontend
from vortex.controllers.types import ModuleTypes, ModuleEvents
from vortex.emulator.kinematics import AxisType
from vortex.frontends.proto import CommandStatus, Completion

@enum.unique
class CoordinateType(enum.ExtIntEnum):
    ABSOLUTE = enum.auto()
    RELATIVE = enum.auto()

class GCodeFrontend(BaseFrontend):
    def __init__(self):
        super().__init__()
        self._command_id_queue = []
        self.current_feed_rate = 0.
        self.coordinates = CoordinateType.ABSOLUTE
        self.extruder_coordinates = CoordinateType.ABSOLUTE

    def _process_command(self, data):
        cmd = data.decode()
        cmd = gcmd.GCodeCommand(cmd)
        handler = getattr(self, cmd.command, None)
        logging.debug(f"Command {cmd} handler {handler}")
        if not handler:
            logging.error(f"No handler for command {cmd.command}")
            return
        status = handler(cmd)
        if not isinstance(status, CommandStatus):
            super().respond(CommandStatus.QUEUED, status)
        else:
            data = True if status == CommandStatus.SUCCESS else False
            super().respond(status, data)

    def complete_command(self, id, result):
        logging.debug(f"Command {id} complete: {result}")
        super().complete_command(id, result)
        super().respond(CommandStatus.COMPLETE, Completion(id, result))

    def event_handler(self, klass, event, owner, data):
        print("gcode handler:", klass, event, owner, data)
        if event == ModuleEvents.HEATER_TEMP_REACHED:
            print("gcode handler: ", data["temp"])

    def move_to_position(self, axis_id, position):
        status = self.query_object([axis_id])
        axis_distance = position - status[axis_id]["position"]
        motor_ids = [self.get_object_id(ModuleTypes.STEPPER, x) \
                      for x in status[axis_id]["motors"] if x]
        motor_status = self.query_object(motor_ids)
        current_positions = [motor_status[x]["steps"] for x in motor_ids]
        new_position = [axis_distance * motor_status[x]["steps_per_mm"] \
                        for x in motor_ids]
        movement = self.kinematics.get_move(current_positions, new_position)
        move_cmds = []
        for idx in range(len(movement)):
            distance = int(movement[idx])
            direction = 1 + int(distance < 0.)
            cmd_id = self.queue_command(ModuleTypes.STEPPER,
                                        status[axis_id]["motors"][idx],
                                        "move",
                                        f"steps={abs(distance)},direction={direction}")
            if cmd_id is False:
                logging.error("Failed to submit move command")
                continue
            move_cmds.append(cmd_id)
        return move_cmds
    # GCode command implementation
    def G0(self, cmd):
        axes_names = self.get_object_name_set(ModuleTypes.AXIS)
        axes = {x: self.get_object_id(ModuleTypes.AXIS, x) for x in axes_names}
        axes_status = self.query_object(axes.values())
        motor_set = []
        for axis in axes.values():
            motor_set += [self.get_object_id(ModuleTypes.STEPPER, x) \
                          for x in axes_status[axis]["motors"] if x]
        motor_status = self.query_object(motor_set)
        if cmd.has_param("F"):
            mm_per_min = cmd.get_param("F")
            speed = mm_per_min.value / 60
            for axis in axes.values():
                for motor in axes_status[axis]["motors"]:
                    if not motor:
                        continue
                    motor_id = self.get_object_id(ModuleTypes.STEPPER, motor)
                    steps_per_mm = motor_status[motor_id]["stepr_per_mm"]
                    self.queue_command(ModuleTypes.STEPPER, motor, "set_speed",
                                       f"steps_per_second={speed * steps_per_mm}")
        for axis in cmd.get_params(exclude=["F"]):
            if axis.name.lower() == "e":
                coordinates = self.extruder_coordinates
            else:
                coordinates = self.coordinates
            axis_type = AxisType(axes_status[axes[axis.name.lower()]]["type"].upper())
            axis_id = [x for x in axes_status if axes_status[x]["type"] == axis_type]
            if len(axis_id) == 0:
                logging.error(f"Did not find axis of type '{axis.name.upper()}")
                return CommandStatus.FAIL
            axis_id = axis_id[0]
            if coordinates == CoordinateType.RELATIVE:
                axis_position = axes_status[axis_id]["position"] + axis.value
            else:
                axis_position = axis.value
            cmds = self.move_to_position(axis_id, axis_position)
        self.wait_for_command(cmds)
        return CommandStatus.SUCCESS
    def G1(self, cmd):
        return self.G0(cmd)
    def G4(self, cmd):
        if not cmd.has_params():
            while self._command_completion:
                time.sleep(0.1)
        else:
            dwell = cmd.get_param("S") or cmd.get_param("P")
            time.sleep(dwell / constants.SEC2MSEC)
        return CommandStatus.SUCCESS
    def G28(self, cmd):
        klass = ModuleTypes.AXIS
        if not cmd.has_params():
            axes_types = [AxisType.X, AxisType.Y, AxisType.Z,
                          AxisType.A, AxisType.B, AxisType.C]
        else:
            axes_types = [AxisType[x.name.upper()] for x in cmd.iter_params()]
        axes_ids = self.get_object_id_set(ModuleTypes.AXIS)
        status = self.query_object(axes_ids)
        axes_ids = [x for x in axes_ids if status[x]["type"] in axes_types]
        axis_endstop_ids = {x: self.get_object_id(ModuleTypes.ENDSTOP,
                                               status[x]["endstop"]) \
                                                for x in axes_ids}
        endstop_status = self.query_object(axis_endstop_ids.values())
        for axis in axes_ids:
            logging.debug(f"Homing axis {AxisType(status[axis]["type"])}")
            motor_ids = {}
            for motor in [x for x in status[axis]["motors"] if x]:
                motor_ids[motor] = self.get_object_id(ModuleTypes.STEPPER, motor)
            motor_status = self.query_object(motor_ids.values())
            for motor in motor_ids:
                if not motor_status[motor_ids[motor]]["enabled"]:
                    cmd_id = self.queue_command(ModuleTypes.STEPPER, motor, "enable",
                                              "enable=1")
                    if cmd_id is False:
                        logging.error("Failed to enable motor")
                    self.wait_for_command(cmd_id)
            if endstop_status[axis_endstop_ids[axis]]["type"] == "max":
                cmds = self.move_to_position(axis, status[axis]["length"])
            else:
                cmds = self.move_to_position(axis, 0)
            self.wait_for_command(cmds)
        return CommandStatus.SUCCESS
    def G90(self, cmd):
        self.coordinates = CoordinateType.ABSOLUTE
        return CommandStatus.SUCCESS
    def G91(self, cmd):
        self.coordinates = CoordinateType.RELATIVE
        return CommandStatus.SUCCESS
    def M0(self, cmd):
        self.M400(None)
        wait_time = 0.
        if cmd.has_param("P"):
            wait_time = cmd.get_param("P").value / constants.SEC2MSEC
        elif cmd.has_param("S"):
            wait_time = cmd.get_param("S").value
        if wait_time:
            time.sleep(wait_time)
        self.reset()
        self.is_reset = True
        return CommandStatus.SUCCESS
    def M1(self, cmd):
        self.M400(None)
        reset_objects = []
        for object_id in self._obj_id_2_name[ModuleTypes.STEPPERS] + \
            self._obj_id_2_name[ModuleTypes.HEATER]:
            reset_objects.append(object_id)
        wait_time = 0.
        if cmd.has_param("P"):
            wait_time = cmd.get_param("P").value / constants.SEC2MSEC
        elif cmd.has_param("S"):
            wait_time = cmd.get_param("S").value
        if wait_time:
            time.sleep(wait_time)
        self.reset(reset_objects)
        return CommandStatus.SUCCESS
    def M82(self, cmd):
        self.extruder_coordinates = CoordinateType.ABSOLUTE
        return CommandStatus.SUCCESS
    def M83(self, cmd):
        self.extruder_coordinates = CoordinateType.RELATIVE
        return CommandStatus.SUCCESS
    def M104(self, cmd):
        object = self.find_object(ModuleTypes.HEATER, "extruder", "hotend")
        if object:
            temp = cmd.get_param("S")
            cmd_id = self.queue_command(ModuleTypes.HEATER, object,
                                        "set_temperature",
                                        f"temperature={temp.value}")
            if cmd_id is False:
                logging.error("Failed to queue command")
                return CommandStatus.FAIL
            if cmd.command_code == 109:
                self.wait_for_command(cmd_id)
                return CommandStatus.SUCCESS
            return cmd_id
        return CommandStatus.FAIL
    def M106(self, cmd):
        object = self.find_object(ModuleTypes.FAN, "fan1", "fan", "extruder", "hostend")
        if object:
            speed = cmd.get_param("S")
            if self.queue_command(ModuleTypes.FAN, object,
                                  "set_speed", f"speed={speed.value}") is False:
                logging.error("Failed to queue command")
                return CommandStatus.FAIL
            return CommandStatus.SUCCESS
        return CommandStatus.FAIL
    def M107(self, cmd):
        cmd = gcmd.GCodeCommand("M106 S0")
        return self.M106(cmd)
    def M109(self, cmd):
        return self.M104(cmd)
    def M112(self, cmd):
        self.reset()
        self.is_reset = True
        return CommandStatus.SUCCESS
    def M140(self, cmd):
        object = self.find_object(ModuleTypes.HEATER, "bed", "surface")
        if object:
            #index = cmd.get_param("I")
            temp = cmd.get_param("S")
            cmd_id = self.queue_command(ModuleTypes.HEATER, object,
                                        "set_temperature",
                                        f"temperature={temp.value}")
            if cmd_id is False:
                logging.error("Failed to queue command")
                return CommandStatus.FAIL
            if cmd.command_code == 190:
                self.wait_for_command(cmd_id)
                return CommandStatus.SUCCESS
            return cmd_id
        return CommandStatus.FAIL
    def M190(self, cmd):
        return self.M140(cmd)
    def M204(self, cmd):
        accel = cmd.get_param("S")
        axes = self.get_object_set(ModuleTypes.AXIS)
        if "e" in axes:
            axes.remove("e")
        axes_ids = [self.get_object_id(ModuleTypes.AXIS, x) for x in axes]
        status = self.query_object(axes_ids)
        cmds = []
        for axis in status:
            for motor in status[axis]["motors"]:
                if not motor:
                    continue
                cmd_id = self.queue_command(ModuleTypes.STEPPER, motor,
                                      "set_accel",
                                      f"accel={accel.value},decel=0")
                if cmd_id is False:
                    logging.error("Failed to queue command")
                    return CommandStatus.FAIL
                cmds.append(cmd_id)
        self.wait_for_commands(cmds)
        return CommandStatus.SUCCESS
    def M400(self, cmd):
        while self._command_completion:
            time.sleep(0.1)
        return CommandStatus.SUCCESS
    def M999(self, cmd):
        object = self._obj_name_2_id[ModuleTypes.TOOLHEAD]['tool1']
        print(self.query_object([object]))
        return CommandStatus.SUCCESS

def create():
    return GCodeFrontend()
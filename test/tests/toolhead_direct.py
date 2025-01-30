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
from vortex.emulator.kinematics import AxisType
from framework import TestStatus
from math import ceil
from argparse import Namespace

dependencies = ["axis_direct"]

def kinematics_cartesian(distance, motors, axis_type):
    return distance * motors[0].spm

def kinematics_corexy(distance, motors, axis_type):
    if axis_type == AxisType.Y:
        return -distance * motors[1].spm
    else:
        return distance * motors[0].spm

def move_axis(framework, toolhead, axis_type, distance):
    kinematics_func = eval(f"kinematics_{toolhead.kinematics}")
    motor_steps = abs(kinematics_func(distance, toolhead.axes[axis_type].motors, axis_type))
    motor_steps = ceil(motor_steps)
    move_cmds = []
    status = 0
    direction = 1 if distance > 0 else 2
    if toolhead.kinematics == "cartesian":
        for motor in toolhead.axes[axis_type].motors:
            cmd_id  = framework.run_command(f"stepper:{motor.name}:move:steps={motor_steps},direction={direction}")
            move_cmds.append(cmd_id)
    for cmd_id in move_cmds:
        status |= framework.wait_for_completion(cmd_id)
    return status

def compare_position(framework, actual, desired, spm):
    # It is possible that the axis cannot achieve the exact
    # desired position if the difference between the desired
    # and actual positions is less than one motor step.
    if not framework.assertLT((desired - actual) * spm,  1.0):
        return False
    return True

def create_toolhead(framework, name):
    toolhead = Namespace()
    toolhead_obj = None
    toolheads = framework.get_objects("toolhead")
    for t in toolheads:
        if t["name"] == name:
            toolhead_obj = t
            break
    if not framework.assertNE(toolhead_obj, None):
        return framework.failed()
    toolhead.id = toolhead_obj["id"]
    toolhead.name = toolhead_obj["name"]
    toolhead.kinematics = framework.get_machine_config().kinematics
    toolhead.klass = framework.get_object_klass("toolhead")
    toolhead.config = framework.get_config_section(toolhead.klass, toolhead.name)
    toolhead.axes = {AxisType[x.upper()]: Namespace() for x in toolhead.config.axes}
    axes = framework.get_objects("axis")
    for a in axes:
        axis_status = framework.get_status(a["id"])[a["id"]]
        if axis_status["type"] in toolhead.axes:
            toolhead.axes[axis_status["type"]].obj = a["id"]
            toolhead.axes[axis_status["type"]].name = a["name"]
            toolhead.axes[axis_status["type"]].length = axis_status["length"]
            toolhead.axes[axis_status["type"]].motors = []
            motors = framework.get_objects("stepper")
            for m in motors:
                if m["name"] not in axis_status["motors"]:
                    continue
                motor = Namespace()
                motor.id = m["id"]
                motor.name = m["name"]
                motor_status = framework.get_status(motor.id)[motor.id]
                motor.spm = motor_status["steps_per_mm"]
                toolhead.axes[axis_status["type"]].motors.append(motor)
    for axis in toolhead.axes:
        if not framework.assertNE(axis, None):
            return framework.failed()
    return toolhead

def test_toolhead(framework, toolhead):
    for axis in toolhead.axes:
        for motor in toolhead.axes[axis].motors:
            motor_status = framework.get_status(motor.id)[motor.id]
            if not motor_status["enabled"]:
                cmd_id = framework.run_command(f"stepper:{motor.name}:enable:enable=1")
                framework.wait_for_completion(cmd_id)
            # Increase motor speed to speed up the test
            cmd_id = framework.run_command(f"stepper:{motor.name}:set_speed:steps_per_second={50 * motor.spm}")
            framework.wait_for_completion(cmd_id)
    toolhead_status = framework.get_status(toolhead.id)[toolhead.id]
    for axis in toolhead.axes:
        travel_distance = 50
        if toolhead_status["position"][int(axis)] + \
            travel_distance > toolhead.axes[axis].length:
            travel_distance *= -1
        status = move_axis(framework, toolhead, axis, travel_distance)
        if not framework.assertEQ(status, 0):
            return framework.failed()
        axis_position = framework.get_status(toolhead.id)[toolhead.id]
        if not framework.assertEQ(axis_position["position"][int(axis)],
                                  toolhead_status["position"][int(axis)] +
                                  travel_distance):
            return framework.failed()
    return framework.passed()

def run_test(framework):
    if framework.frontend != "direct":
        framework.begin("toolhead_direct")
        return framework.waive()
    toolheads = framework.get_objects("toolhead")
    for t in toolheads:
        framework.begin(f"toolhead '{t['name']}'")
        toolhead = create_toolhead(framework, t["name"])
        if toolhead == TestStatus.FAIL:
            continue
        test_toolhead(framework, toolhead)

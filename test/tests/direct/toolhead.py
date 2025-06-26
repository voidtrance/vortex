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
import testutils
from vortex.core.kinematics import AxisType
from argparse import Namespace
from .axis import move_axis

def create_toolhead(framework, name):
    toolhead = Namespace()
    toolhead_obj = None
    toolheads = framework.get_objects("toolhead")
    for t in toolheads:
        if t["name"] == name:
            toolhead_obj = t
            break
    testutils.assertNE(toolhead_obj, None)
    toolhead.id = toolhead_obj["id"]
    toolhead.name = toolhead_obj["name"]
    toolhead.kinematics = framework.get_kinematics_config()
    toolhead.klass = framework.get_object_klass("toolhead")
    toolhead.config = framework.get_config_section(toolhead.klass, toolhead.name)
    toolhead.axes = {AxisType[x.upper()]: Namespace() for x in toolhead.config.axes}
    axes = framework.get_objects("axis")
    for a in axes:
        axis_status = framework.get_status(a["id"])[a["id"]]
        if axis_status["type"] in toolhead.axes:
            toolhead.axes[axis_status["type"]].obj = a["id"]
            toolhead.axes[axis_status["type"]].name = a["name"]
            toolhead.axes[axis_status["type"]].length = axis_status["max"] - axis_status["min"]
            toolhead.axes[axis_status["type"]].motors = dict()
            motors = framework.get_objects("stepper")
            for m in motors:
                if m["name"] not in axis_status["motors"]:
                    continue
                name = m["name"]
                motor = dict()
                motor["id"] = m["id"]
                motor_status = framework.get_status(motor["id"])[motor["id"]]
                motor["spm"] = motor_status["steps_per_mm"]
                motor["steps"] = motor_status["steps"]
                toolhead.axes[axis_status["type"]].motors[name] = motor
    for axis in toolhead.axes:
        testutils.assertNE(axis, None)
    return toolhead

@testutils.object_test("toolhead_test", "toolhead", ["axis"])
def test_toolhead(framework, name, toolhead_id):
    toolhead = create_toolhead(framework, name)
    if toolhead == testutils.TestStatus.FAIL:
        return toolhead
    for axis in toolhead.axes:
        for name, motor in toolhead.axes[axis].motors.items():
            motor_status = framework.get_status(motor["id"])[motor["id"]]
            if not motor_status["enabled"]:
                cmd_id = framework.run_command(f"stepper:{name}:enable:enable=1")
                framework.wait_for_completion(cmd_id)
            # Increase motor speed to speed up the test
            cmd_id = framework.run_command(f"stepper:{name}:set_speed:steps_per_second={50 * motor['spm']}")
            framework.wait_for_completion(cmd_id)
    toolhead_status = framework.get_status(toolhead.id)[toolhead.id]
    for axis in toolhead.axes:
        travel_distance = 50
        if toolhead_status["position"][int(axis)] + \
            travel_distance > toolhead.axes[axis].length:
            travel_distance *= -1
        status = move_axis(framework, axis, travel_distance, toolhead.kinematics,
                           toolhead.axes[axis].motors)
        testutils.assertEQ(status, 0)
        axis_position = framework.get_status(toolhead.id)[toolhead.id]
        testutils.assertEQ(axis_position["position"][int(axis)],
                           toolhead_status["position"][int(axis)] +
                           travel_distance)
    return testutils.TestStatus.PASS

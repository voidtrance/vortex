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
from .axis import move_axis

@testutils.object_test("endstop_test", "endstop", ["axis"])
def test_endstop(framework, name, obj_id):
    kinematics = framework.get_kinematics_config()
    endstop_status = framework.get_status(obj_id)[obj_id]
    endstop_axis_type = AxisType(endstop_status["axis"])
    axes = framework.get_objects("axis")
    axis = None
    for a in axes:
        axis_status = framework.get_status(a["id"])[a["id"]]
        if axis_status["type"] == endstop_axis_type:
            axis = a
            break
    testutils.assertNE(axis, None)
    status = framework.get_status(axis["id"])[axis["id"]]
    axis_length = status["max"] - status["min"]
    motors = framework.get_objects("stepper")
    motors = {x["name"]: x["id"] for x in motors}
    motors = {n: {"id": i} for n, i in motors.items() if n in axis_status["motors"]}
    for motor in motors:
        motor_status = framework.get_status(motors[motor]["id"])[motors[motor]["id"]]
        motors[motor]["spm"] = motor_status["steps_per_mm"]
        if not motor_status["enabled"]:
            cmd_id = framework.run_command(f"stepper:{motor}:enable:enable=1")
            framework.wait_for_completion(cmd_id)
        # Increase motor speed to speed up the test
        cmd_id = framework.run_command(f"stepper:{motor}:set_speed:steps_per_second={50 * motor_status['steps_per_mm']}")
        framework.wait_for_completion(cmd_id)
    axis_status = framework.get_status(axis["id"])[axis["id"]]
    axis_position = axis_status["position"]
    if (endstop_status["type"] == "min" and axis_position == 0) or \
        (endstop_status["type"] == "max" and
         axis_position == axis_length):
        initial_state = True
    else:
        initial_state = False
    testutils.assertEQ(endstop_status["triggered"], initial_state)
    if axis_length == -1:
        testutils.assertEQ(axis_status["homed"], True)
    if initial_state is False:
        if endstop_status["type"] == "min":
            travel_distance = -axis_status["position"]
        else:
            travel_distance = axis_length - axis_status["position"]
        status = move_axis(framework, endstop_axis_type, travel_distance, kinematics, motors)
        testutils.assertEQ(status, 0)
        endstop_status = framework.get_status(obj_id)[obj_id]
        testutils.assertEQ(endstop_status["triggered"], True)
    travel_distance = 5
    if axis_length != -1 and endstop_status["type"] != "min":
        travel_distance *= -1
    status = move_axis(framework, endstop_axis_type, travel_distance, kinematics, motors)
    testutils.assertEQ(status, 0)
    endstop_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(endstop_status["triggered"], False)
    status = move_axis(framework, endstop_axis_type, -travel_distance, kinematics, motors)
    testutils.assertEQ(status, 0)
    endstop_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(endstop_status["triggered"], True)
    # Test that moving to the other end of the axis does not trigger
    # the endstop:
    axis_status = framework.get_status(axis["id"])[axis["id"]]
    if endstop_status["type"] == "max":
        travel_distance = -axis_status["position"]
    else:
        travel_distance = axis_length - axis_status["position"]
    status = move_axis(framework, endstop_axis_type, travel_distance, kinematics, motors)
    testutils.assertEQ(status, 0)
    endstop_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(endstop_status["triggered"], False)
    return testutils.TestStatus.PASS

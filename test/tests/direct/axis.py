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
import logging
from vortex.emulator.kinematics import AxisType
from math import ceil, pow

def kinematics_cartesian(distance, motors, axis_type):
    return distance * motors[list(motors)[0]]["spm"]

def kinematics_corexy(distance, motors, axis_type):
    if axis_type == AxisType.Y:
        return -distance * motors[list(motors)[1]]["spm"]
    else:
        return distance * motors[list(motors)[0]]["spm"]

def move_axis(framework, axis_type, distance, kinematics, motors):
    kin_type = kinematics.type
    kinematics_func = eval(f"kinematics_{kin_type}")
    motor_steps = abs(kinematics_func(distance, motors, axis_type))
    motor_steps = ceil(motor_steps)
    move_cmds = []
    status = 0
    direction = 1 if distance > 0 else 0
    for motor in motors:
        cmd_id  = framework.run_command(f"stepper:{motor}:move:steps={motor_steps},direction={direction}")
        move_cmds.append(cmd_id)
    for cmd_id in move_cmds:
        status |= framework.wait_for_completion(cmd_id)
    return status

def compare_position(framework, actual, desired, spm):
    # It is possible that the axis cannot achieve the exact
    # desired position if the difference between the desired
    # and actual positions is less than one motor step.
    step_diff = int(abs(desired - actual) * spm * pow(10, 8)) / pow(10, 8)
    testutils.assertLT(step_diff,  1.0)
    return True

@testutils.object_test("axis", "axis", ["stepper"])
def test_axis(framework, name, obj_id):
    kinematics = framework.get_kinematics_config()
    if kinematics.type == "delta":
        return testutils.TestStatus.WAIVE("Delta kinematics not supported in this test")
    axis_status = framework.get_status(obj_id)[obj_id]
    axis_type = AxisType(axis_status["type"])
    axis_length = axis_status["max"] - axis_status["min"]
    if axis_length != -1:
        testutils.assertEQ(axis_status["homed"], False)
    axis_motors = [x for x in axis_status["motors"] if x]
    motors = framework.get_objects("stepper")
    motors = {x["name"]: x["id"] for x in motors}
    motors = {n: {"id": i} for n, i in motors.items() if n in axis_motors}
    for motor in motors:
        motor_status = framework.get_status(motors[motor]["id"])[motors[motor]["id"]]
        motors[motor]["spm"] = motor_status["steps_per_mm"]
        motors[motor]["steps"] = motor_status["steps"]
        if not motor_status["enabled"]:
            cmd_id = framework.run_command(f"stepper:{motor}:enable:enable=1")
            framework.wait_for_completion(cmd_id)
        # Increase motor speed to speed up the test
        cmd_id = framework.run_command(f"stepper:{motor}:set_speed:steps_per_second={50 * motors[motor]['spm']}")
        framework.wait_for_completion(cmd_id)
    # Axes positions are randomized so we have to figure out
    # how to travel
    initial_position = axis_status["position"]
    travel_distance = 50
    if axis_length - initial_position <= travel_distance and \
        initial_position > travel_distance:
        travel_distance *= -1
    else:
        if axis_length != -1:
            travel_distance = (axis_length - initial_position) / 2
    logging.debug(f"Moving axis {travel_distance}mm...")
    expected_position = initial_position + travel_distance
    status = move_axis(framework, axis_type, travel_distance, kinematics, motors)
    testutils.assertEQ(status, 0)
    axis_status = framework.get_status(obj_id)[obj_id]
    if not compare_position(framework, axis_status["position"],
                            expected_position,
                            motors[list(motors)[0]]["spm"]):
        return testutils.TestStatus.FAILED
    travel_distance = -(axis_status["position"] / 2)
    logging.debug(f"Moving axis {travel_distance}mm...")
    expected_position += travel_distance
    status = move_axis(framework, axis_type, travel_distance, kinematics, motors)
    testutils.assertEQ(status, 0)
    axis_status = framework.get_status(obj_id)[obj_id]
    if not compare_position(framework, axis_status["position"],
                            expected_position,
                            motors[list(motors)[0]]["spm"]):
        return testutils.TestStatus.FAILED
    # Infinite axes are auto-homed.
    if axis_length != -1:
        endstops = framework.get_objects("endstop")
        axis_endstop = None
        for endstop in endstops:
            endstop_status = framework.get_status(endstop["id"])[endstop["id"]]
            endstop_axis_type = AxisType(endstop_status["axis"])
            if endstop_axis_type == axis_type:
                axis_endstop = endstop
                break
        testutils.assertNE(axis_endstop, None)
        if endstop_status["type"] == "min":
            travel_distance = -axis_status["position"]
            home_position = 0
        else:
            travel_distance = axis_length - axis_status["position"]
            home_position = axis_length
        logging.debug("Homing axis...")
        status = move_axis(framework, axis_type, travel_distance, kinematics, motors)
        testutils.assertEQ(status, 0)
        axis_status = framework.get_status(obj_id)[obj_id]
        if not compare_position(framework, axis_status["position"],
                                home_position, motors[list(motors)[0]]["spm"]):
            return testutils.TestStatus.FAILED
    return testutils.TestStatus.PASS

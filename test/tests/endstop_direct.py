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
from vortex.emulator.kinematics import AxisType
from math import ceil

dependencies = ["axis_direct"]

def kinematics_cartesian(distance, motors, axis_type):
    return distance * motors[list(motors)[0]]["spm"]

def kinematics_corexy(distance, motors, axis_type):
    if axis_type == AxisType.Y:
        return -distance * motors[list(motors)[1]]["spm"]
    else:
        return distance * motors[list(motors)[0]]["spm"]

def move_axis(framework, axis_type, distance, kinematics, motors):
    kinematics_func = eval(f"kinematics_{kinematics}")
    motor_steps = abs(kinematics_func(distance, motors, axis_type))
    motor_steps = ceil(motor_steps)
    move_cmds = []
    status = 0
    direction = 1 if distance > 0 else 2
    if kinematics == "cartesian":
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
    if not framework.assertLT((desired - actual) * spm,  1.0):
        return False
    return True

def test_endstop(framework, name, obj_id):
    framework.begin(f"endstop_direct '{name}'")
    kinematics = framework.get_machine_config().kinematics
    endstop_status = framework.get_status(obj_id)[obj_id]
    endstop_axis_type = AxisType(endstop_status["axis"])
    axes = framework.get_objects("axis")
    axis = None
    for a in axes:
        axis_status = framework.get_status(a["id"])[a["id"]]
        if axis_status["type"] == endstop_axis_type:
            axis = a
            break
    if not framework.assertNE(axis, None):
        return framework.failed()
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
    print(f"{endstop_status}, {axis_status}")
    if (endstop_status["type"] == "min" and axis_position == 0) or \
        (endstop_status["type"] == "max" and 
         axis_position == axis_status["length"]):
        initial_state = True
    else:
        initial_state = False
    if not framework.assertEQ(endstop_status["triggered"], initial_state):
        return framework.failed()
    if axis_status["length"] == -1:
        if not framework.assertEQ(axis_status["homed"], True):
            return framework.failed()
    if initial_state is False:
        if endstop_status["type"] == "min":
            travel_distance = -axis_status["position"]
        else:
            travel_distance = axis_status["length"] - axis_status["position"]
        status = move_axis(framework, endstop_axis_type, travel_distance, kinematics, motors)
        if not framework.assertEQ(status, 0):
            return framework.failed()
        endstop_status = framework.get_status(obj_id)[obj_id]
        if not framework.assertEQ(endstop_status["triggered"], True):
            return framework.failed()
    travel_distance = 5
    if axis_status["length"] != -1 and endstop_status["type"] != "min":
        travel_distance *= -1
    status = move_axis(framework, endstop_axis_type, travel_distance, kinematics, motors)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    endstop_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(endstop_status["triggered"], False):
        return framework.failed()
    status = move_axis(framework, endstop_axis_type, -travel_distance, kinematics, motors)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    endstop_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(endstop_status["triggered"], True):
        return framework.failed()
    # Test that moving to the other end of the axis does not trigger
    # the endstop:
    axis_status = framework.get_status(axis["id"])[axis["id"]]
    if endstop_status["type"] == "max":
        travel_distance = -axis_status["position"]
    else:
        travel_distance = axis_status["length"] - axis_status["position"]
    status = move_axis(framework, endstop_axis_type, travel_distance, kinematics, motors)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    endstop_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(endstop_status["triggered"], False):
        return framework.failed()
    return framework.passed()

def run_test(framework):
    if framework.frontend != "direct":
        framework.begin("endstop_direct")
        return framework.waive()
    endstops = framework.get_objects("endstop")
    for endstop in endstops:
        test_endstop(framework, endstop["name"], endstop["id"])

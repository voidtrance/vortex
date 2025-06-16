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
import time

@testutils.object_test("stepper_test", "stepper")
def run_stepper_test(framework, stepper, obj_id):
    stepper_status = framework.get_status(obj_id)[obj_id]
    if stepper_status["enabled"] is False:
        # Check that the stepper will not move unless enabled
        cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=0,steps=5")
        result = framework.wait_for_completion(cmd_id)
        testutils.assertNE(result, 0)
        cmd_id = framework.run_command(f"stepper:{stepper}:enable:enable=1")
        framework.wait_for_completion(cmd_id)
        stepper_status = framework.get_status(obj_id)[obj_id]
        testutils.assertNE(stepper_status["enabled"], False)
    start_steps = stepper_status["steps"]
    cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=0,steps=200")
    framework.wait_for_completion(cmd_id)
    stepper_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(stepper_status["steps"], start_steps - 200)
    cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=1,steps=200")
    framework.wait_for_completion(cmd_id)
    stepper_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(stepper_status["steps"], start_steps)
    # Test stepper speed
    travel_distance = 50 # mm
    travel_steps = travel_distance * stepper_status["steps_per_mm"]
    speed = 25 # mm/s
    step_speed = speed * stepper_status["steps_per_mm"]
    travel_time = travel_distance / speed
    cmd_id = framework.run_command(f"stepper:{stepper}:set_speed:steps_per_second={step_speed}")
    status = framework.wait_for_completion(cmd_id)
    testutils.assertEQ(status, 0)
    start = time.time()
    cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=1,steps={travel_steps}")
    status = framework.wait_for_completion(cmd_id)
    end = time.time()
    testutils.assertEQ(status, 0)
    delta_time = end - start
    # Increase expected time to allow for completion latency
    factor = 1.5 if framework.logging_enabled else 1.3
    testutils.assertLT(round(delta_time, 2), travel_time * factor)
    return testutils.TestStatus.PASS

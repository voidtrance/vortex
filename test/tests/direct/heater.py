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

def wait_for_temp(framework, cmd_id, obj_id, start, target):
    temp = start
    while not framework.command_is_complete(cmd_id):
        # Wait an increasing amount of time before querying the
        # object to account for the slowdown in the ramp when
        # approaching target temperature. But use a minimum of
        # 0.1 seconds to allow for some change.
        min_wait = 0.5 if framework.logging_enabled() else 0.1
        wait = max(10 * (abs(temp - start) / abs(target - start)) or 1, min_wait)
        time.sleep(wait)
        heater_status = framework.get_status(obj_id)[obj_id]
        if heater_status["temperature"] == target:
            break
        if start < target:
            testutils.assertGT(heater_status["temperature"], temp)
        elif start > target:
            testutils.assertLT(heater_status["temperature"], temp)
        temp = heater_status["temperature"]
    # command_is_complete() does not remove the completion from the stack
    result = framework.wait_for_completion(cmd_id)
    return not bool(result)

@testutils.object_test("heater_test", "heater")
def run_heater_test(framework, heater, obj_id):
    heater_status = framework.get_status(obj_id)[obj_id]
    initial_temp = heater_status["temperature"]
    max_temp = heater_status["max_temp"]
    target_temp = initial_temp + 30
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, initial_temp, target_temp):
        return testutils.TestStatus.FAIL
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = heater_status["temperature"]
    testutils.assertEQ(temp, target_temp)
    target_temp = temp + 10
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, target_temp):
        return testutils.TestStatus.FAIL
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = heater_status["temperature"]
    testutils.assertEQ(temp, target_temp)
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={max_temp + 5}")
    result = framework.wait_for_completion(cmd_id)
    testutils.assertNE(result, 0)
    heater_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(heater_status["temperature"], temp)
    target_temp = temp - 15
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, target_temp):
        return testutils.TestStatus.FAIL
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = heater_status["temperature"]
    testutils.assertEQ(temp, target_temp)
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={initial_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, initial_temp):
        return testutils.TestStatus.FAIL
    heater_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(heater_status["temperature"], initial_temp)
    return testutils.TestStatus.PASS

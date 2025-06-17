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

temp_precision = 1
pwm_hold_time = 10 # seconds

def wait_for_temp(framework, cmd_id, obj_id, start, target):
    temp = start
    wait_pwm = False
    pwm_hold_start = 0
    framework.ignore_command_completion(cmd_id)
    while True:
        # Wait an increasing amount of time before querying the
        # object to account for the slowdown in the ramp when
        # approaching target temperature. But use a minimum of
        # 0.1 seconds to allow for some change.
        min_wait = 0.5 if framework.logging_enabled() else 0.1
        wait = max(10 * (abs(target - temp) / abs(target - start)), min_wait)
        time.sleep(wait)
        heater_status = framework.get_status(obj_id)[obj_id]
        if wait_pwm:
            if round(heater_status["temperature"], temp_precision) == target:
                if time.time() - pwm_hold_start > pwm_hold_time:
                    break
            else:
                pwm_hold_start = time.time()
            continue
        if start < target:
            testutils.assertGT(heater_status["temperature"], temp)
            if heater_status["temperature"] >= target:
                pwm_hold_start = time.time()
                wait_pwm = True
        elif start > target:
            testutils.assertLT(heater_status["temperature"], temp)
            if heater_status["temperature"] <= target:
                pwm_hold_start = time.time()
                wait_pwm = True
        temp = heater_status["temperature"]
    # We don't need to wait for the command to complete because the HW
    # object uses a much higher precision and will not complete until
    # it hits that precise value.
    return True

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
    temp = round(heater_status["temperature"], temp_precision)
    testutils.assertEQ(temp, target_temp)
    target_temp = temp + 10
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, target_temp):
        return testutils.TestStatus.FAIL
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = round(heater_status["temperature"], temp_precision)
    testutils.assertEQ(temp, target_temp)
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={max_temp + 5}")
    result = framework.wait_for_completion(cmd_id)
    testutils.assertNE(result, 0)
    heater_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(round(heater_status["temperature"], temp_precision), temp)
    target_temp = temp - 5
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, target_temp):
        return testutils.TestStatus.FAIL
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = round(heater_status["temperature"], temp_precision)
    testutils.assertEQ(temp, target_temp)
    start = time.time()
    while time.time() - start < 60:
        heater_status = framework.get_status(obj_id)[obj_id]
        temp = round(heater_status["temperature"], temp_precision)
        testutils.assertEQ(temp, target_temp)
        time.sleep(1)
    return testutils.TestStatus.PASS

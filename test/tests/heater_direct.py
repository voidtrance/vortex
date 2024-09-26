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
import time

dependencies = []

def wait_for_temp(framework, cmd_id, obj_id, start, target):
    temp = start
    while not framework.command_is_complete(cmd_id):
        wait = 10 * (abs(temp - start) / abs(target - start)) or 1
        time.sleep(wait)
        heater_status = framework.get_status(obj_id)[obj_id]
        if heater_status["temperature"] == target:
            break
        if (start < target and \
            not framework.assertGT(heater_status["temperature"], temp)) or \
            (start > target and \
             not framework.assertLT(heater_status["temperature"], temp)):
            return False
        temp = heater_status["temperature"]
    # command_is_complete() does not remove the completion from the stack
    result = framework.wait_for_completion(cmd_id)
    return not bool(result)

def run_heater_test(framework, heater, obj_id):
    heater_status = framework.get_status(obj_id)[obj_id]
    initial_temp = heater_status["temperature"]
    max_temp = heater_status["max_temp"]
    target_temp = initial_temp + 30
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, initial_temp, target_temp):
        return False
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = heater_status["temperature"]
    if not framework.assertEQ(temp, target_temp):
        return False
    target_temp = temp + 10
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, target_temp):
        return False
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = heater_status["temperature"]
    if not framework.assertEQ(temp, target_temp):
        return False
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={max_temp + 5}")
    result = framework.wait_for_completion(cmd_id)
    if not framework.assertNE(result, 0):
        return False
    heater_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(heater_status["temperature"], temp):
        return False
    target_temp = temp - 15
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={target_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, target_temp):
        return False
    heater_status = framework.get_status(obj_id)[obj_id]
    temp = heater_status["temperature"]
    if not framework.assertEQ(temp, target_temp):
        return False
    cmd_id = framework.run_command(f"heater:{heater}:set_temperature:temperature={initial_temp}")
    if not wait_for_temp(framework, cmd_id, obj_id, temp, initial_temp):
        return False
    heater_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(heater_status["temperature"], initial_temp):
        return False
    return True

def run_test(framework):
    if framework.frontend != "direct":
        framework.begin("heater_direct")
        return framework.waive()
    klasses = framework.get_object_klasses()
    klasses = {n:v for v, n in klasses.items()}
    heater_klass = klasses["heater"]
    heaters = framework.get_objects(heater_klass)
    for heater in heaters:
        framework.begin(f"heater_direct for {heater['name']}")
        if run_heater_test(framework, heater["name"], heater["id"]):
            framework.passed()

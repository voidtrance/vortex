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

dependencies = []

def run_stepper_test(framework, stepper, obj_id):
    stepper_status = framework.get_status(obj_id)[obj_id]
    if stepper_status["enabled"] is False:
        # Check that the stepper will not move unless enabled
        cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=2,steps=5")
        result = framework.wait_for_completion(cmd_id)
        if not framework.assertNE(result, 0):
            return framework.failed()
        cmd_id = framework.run_command(f"stepper:{stepper}:enable:enable=1")
        framework.wait_for_completion(cmd_id)
        stepper_status = framework.get_status(obj_id)[obj_id]
        if not framework.assertNE(stepper_status["enabled"], False):
            return framework.failed()
    start_steps = stepper_status["steps"]
    cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=2,steps=200")
    framework.wait_for_completion(cmd_id)
    stepper_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(stepper_status["steps"], start_steps - 200):
        return framework.failed()
    cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=1,steps=200")
    framework.wait_for_completion(cmd_id)
    stepper_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(stepper_status["steps"], start_steps):
        return framework.failed()
    # Test stepper speed
    travel_distance = 50 # mm
    travel_steps = travel_distance * stepper_status["steps_per_mm"]
    speed = 25 # mm/s
    step_speed = speed * stepper_status["steps_per_mm"]
    travel_time = travel_distance / speed
    cmd_id = framework.run_command(f"stepper:{stepper}:set_speed:steps_per_second={step_speed}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    start = time.time()
    cmd_id = framework.run_command(f"stepper:{stepper}:move:direction=1,steps={travel_steps}")
    status = framework.wait_for_completion(cmd_id)
    end = time.time()
    if not framework.assertEQ(status, 0):
        return framework.failed()
    delta_time = end - start
    # Increase expected time to allow for completion latency
    factor = 1.5 if framework.logging_enabled else 1.3
    if not framework.assertLT(round(delta_time, 2), travel_time * factor):
        return framework.failed()
    return framework.passed()

def run_test(framework):
    if framework.frontend != "direct":
        framework.begin("stepper_direct")
        return framework.waive()
    klasses = framework.get_object_klasses()
    klasses = {n:v for v, n in klasses.items()}
    stepper_klass = klasses["stepper"]
    steppers = framework.get_objects(stepper_klass)
    for stepper in steppers:
        framework.begin(f"stepper_direct for {stepper['name']}")
        run_stepper_test(framework, stepper["name"], stepper["id"])

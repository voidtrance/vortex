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

dependencies = []

def test_pin(framework, name, obj_id):
    pin_status = framework.get_status(obj_id)[obj_id]
    initial_cycle = pin_status["cycle"]
    if not framework.assertGE(initial_cycle, 0.0) or \
        not framework.assertLE(initial_cycle, 1.0):
        return framework.failed()
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle={initial_cycle + 30}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    pin_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(pin_status["cycle"], (initial_cycle + 30) / 100):
        return framework.failed()
    cycle = pin_status["cycle"] * 100 - 10
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle={cycle}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    pin_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(pin_status["cycle"], cycle / 100):
        return framework.failed()
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle=110")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertNE(status, 0):
        return framework.failed()
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle=-10")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertNE(status, 0):
        return framework.failed()
    return framework.passed()

def run_test(framework):
    framework.begin("pwm_direct")
    if framework.frontend != "direct":
        return framework.waive()
    pins = framework.get_objects("pwm_pin")
    for pin in pins:
        test_pin(framework, pin["name"], pin["id"])
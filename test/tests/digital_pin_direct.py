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
    initial_state = pin_status["state"]
    cmd_id = framework.run_command(f"digital_pin:{name}:set:state={not initial_state}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    pin_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(pin_status["state"], not initial_state):
        return framework.failed()
    cmd_id = framework.run_command(f"digital_pin:{name}:set:state={not pin_status['state']}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    pin_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(pin_status["state"], initial_state):
        return framework.failed()
    return framework.passed()

def run_test(framework):
    framework.begin("digital_pin_direct")
    if framework.frontend != "direct":
        return framework.waive()
    pins = framework.get_objects("digital_pin")
    for pin in pins:
        test_pin(framework, pin["name"], pin["id"])
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

dependencies = []

def test_fan(framework, name, obj_id):
    fan_status = framework.get_status(obj_id)[obj_id]
    initial_speed = fan_status["speed"]
    if not framework.assertGE(initial_speed, 0.0) or \
        not framework.assertLE(initial_speed, 1.0):
        return framework.failed()
    cmd_id = framework.run_command(f"fan:{name}:set_speed:speed={initial_speed + 30}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    fan_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(fan_status["speed"], (initial_speed + 30) / 100):
        return framework.failed()
    speed = fan_status["speed"] * 100 - 10
    cmd_id = framework.run_command(f"fan:{name}:set_speed:speed={speed}")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertEQ(status, 0):
        return framework.failed()
    fan_status = framework.get_status(obj_id)[obj_id]
    if not framework.assertEQ(fan_status["speed"], speed / 100):
        return framework.failed()
    cmd_id = framework.run_command(f"fan:{name}:set_speed:speed=110")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertNE(status, 0):
        return framework.failed()
    cmd_id = framework.run_command(f"fan:{name}:set_speed:speed=-10")
    status = framework.wait_for_completion(cmd_id)
    if not framework.assertNE(status, 0):
        return framework.failed()
    return framework.passed()

def run_test(framework):
    framework.begin("fan_direct")
    if framework.frontend != "direct":
        return framework.waive()
    fans = framework.get_objects("fan")
    for fan in fans:
        test_fan(framework, fan["name"], fan["id"])
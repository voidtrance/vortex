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

@testutils.object_test("pwm_test", "pwm")
def test_pin(framework, name, obj_id):
    pin_status = framework.get_status(obj_id)[obj_id]
    initial_cycle = pin_status["cycle"]
    testutils.assertGE(initial_cycle, 0.0)
    testutils.assertLE(initial_cycle, 1.0)
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle={initial_cycle + 30}")
    status = framework.wait_for_completion(cmd_id)
    testutils.assertEQ(status, 0)
    pin_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(pin_status["cycle"], (initial_cycle + 30) / 100)
    cycle = pin_status["cycle"] * 100 - 10
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle={cycle}")
    status = framework.wait_for_completion(cmd_id)
    testutils.assertEQ(status, 0)
    pin_status = framework.get_status(obj_id)[obj_id]
    testutils.assertEQ(pin_status["cycle"], cycle / 100)
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle=110")
    status = framework.wait_for_completion(cmd_id)
    testutils.assertNE(status, 0)
    cmd_id = framework.run_command(f"pwm_pin:{name}:set_cycle:cycle=-10")
    status = framework.wait_for_completion(cmd_id)
    testutils.assertNE(status, 0)
    return framework.passed()

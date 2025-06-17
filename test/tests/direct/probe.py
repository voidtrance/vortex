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
from vortex.emulator.kinematics import AxisType
from argparse import Namespace
from .toolhead import create_toolhead
from .axis import move_axis

def create_probe(framework, name, id):
    probe = Namespace()
    probe.name = name
    probe.id = id
    probe.klass = framework.get_object_klass("probe")
    probe_config = framework.get_config_section(probe.klass, probe.name)
    probe.range = probe_config.range
    probe.toolhead = create_toolhead(framework, probe_config.toolhead)
    if probe.toolhead == testutils.TestStatus.FAIL:
        return probe.toolhead
    return probe

@testutils.object_test("probe_test", "probe", ["toolhead"])
def test_probe(framework, name, obj_id):
    probe = create_probe(framework, name, obj_id)
    if probe == testutils.TestStatus.FAIL:
        return probe
    for axis in probe.toolhead.axes:
        for name, motor in probe.toolhead.axes[axis].motors.items():
            motor_status = framework.get_status(motor["id"])[motor["id"]]
            if not motor_status["enabled"]:
                cmd_id = framework.run_command(f"stepper:{name}:enable:enable=1")
                framework.wait_for_completion(cmd_id)
            # Increase motor speed to speed up the test
            cmd_id = framework.run_command(f"stepper:{name}:set_speed:steps_per_second={50 * motor["spm"]}")
            framework.wait_for_completion(cmd_id)
    probe_status = framework.get_status(probe.id)[probe.id]
    toolhead_status = framework.get_status(probe.toolhead.id)[probe.toolhead.id]
    should_be_triggered = True
    for i, p in enumerate(probe_status["position"]):
        should_be_triggered &= p <= probe_status["offsets"][i]
    testutils.assertEQ(probe_status["triggered"], should_be_triggered)
    axis_set = [AxisType(x) for x in toolhead_status["axes"] if x != len(AxisType)]
    for axis in axis_set:
        if should_be_triggered:
            # move out of trigger range
            distance = probe_status["position"][int(axis)] - \
                toolhead_status["position"][int(axis)] + 1
        else:
            distance = -toolhead_status["position"][int(axis)]
        status = move_axis(framework, axis, distance, probe.toolhead.kinematics,
                           probe.toolhead.axes[axis].motors)
        testutils.assertEQ(status, 0)
    probe_status = framework.get_status(probe.id)[probe.id]
    toolhead_status = framework.get_status(probe.toolhead.id)[probe.toolhead.id]
    testutils.assertEQ(probe_status["triggered"], not should_be_triggered)
    return testutils.TestStatus.PASS

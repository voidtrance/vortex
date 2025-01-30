#!/usr/bin/env python3
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
import argparse
import sys
import pathlib
import importlib
import framework

def generate_parser():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("-C", "--config", required=True,
                        help="""Vortex configuration file""")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="""Verbosity level""")
    parser.add_argument("-c", "--controller", default="stm32f4",
                        help="""HW controller to test.""")
    parser.add_argument("-f", "--frontend", default="direct")
    parser.add_argument("-S", "--skip-deps", action="store_true",
                        help="""Skip dependency resolution.""")
    parser.add_argument("-L", "--logfile", type=str, default=None,
                        help="""Save emulator log file to LOGFILE""")
    parser.add_argument("tests", nargs="*",
                        help="""Set of tests to execute""")
    return parser

def get_test(test_name):
    try:
        test_module = importlib.import_module(f"tests.{test_name}")
    except ImportError as e:
        return None, None
    runner = getattr(test_module, "run_test", None)
    if not callable(runner):
        return None, None
    deps = getattr(test_module, "dependencies", [])
    return runner, deps

def compute_dependencies(tests, test_order):
    test_names = list(tests.keys())
    order = []
    while test_names:
        for test in test_names:
            deps = [x for x in tests[test][1] if x not in order]
            if not deps:
                order.append(test)
            else:
                unknown = [x for x in deps if x not in tests.keys()]
                if unknown:
                    test_order += unknown[:]
                    return False
        test_names = [x for x in test_names if x not in order]
    test_order += order[:]
    return True

def load_tests(test_framework, test_list):
    tests = {}
    for test in test_list:
        runner, deps = get_test(test)
        if runner is not None:
            tests[test] = (runner, deps)
        else:
            test_framework.error("Cound not find test '%s'", test)
    return tests

def resolve_tests(test_framework, test_list):
    test_order = test_list[:]
    status = False
    tests = {}
    while status != True:
        tests.update(load_tests(test_framework, test_order))
        test_order.clear()
        status = compute_dependencies(tests, test_order)
    return tests, test_order

def main():
    parser = generate_parser()
    opts = parser.parse_args()

    test_framework = framework.TestFramework(opts.config,
                                             opts.frontend,
                                             opts.controller,
                                             opts.logfile)
    test_framework.set_log_level(opts.verbose)
    test_framework.initialize()

    if not opts.tests:
        ## find all available tests:
        path = pathlib.Path(__file__).parent / "tests"
        for test_file in path.iterdir():
            if test_file.is_dir():
                continue
            opts.tests.append(test_file.stem)

    if opts.skip_deps:
        tests = load_tests(test_framework, opts.tests)
        order = tests.keys()
    else:
        tests, order = resolve_tests(test_framework, opts.tests)

    try:
        for test in order:
            tests[test][0](test_framework)
            if opts.frontend == "direct":
                status = test_framework.run_command("reset")
                if not status:
                    framework.error("Failed to reset emulator")
    finally:
        test_framework.terminate()

    return 0

sys.exit(main())
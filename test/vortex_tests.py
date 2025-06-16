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

def main():
    sys.path.append(".")
    parser = generate_parser()
    opts = parser.parse_args()

    test_framework = framework.TestFramework(opts.config,
                                             opts.frontend,
                                             opts.controller,
                                             opts.logfile)
    test_framework.set_log_level(opts.verbose)
    if not test_framework.load_tests():
        return -1

    if not test_framework.initialize():
        return -1

    try:
        test_framework.run_tests(opts.tests, opts.skip_deps)
    except KeyboardInterrupt:
        pass
    finally:
        test_framework.terminate()

    return 0

sys.exit(main())
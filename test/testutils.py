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
import logging
import inspect

class TestStatus:
    class __base_test_status__:
        def __init__(self, msg=None):
            self.msg = msg
        def __eq__(self, other):
            return other == self.__class__
    class FAIL(__base_test_status__):
        pass
    class PASS(__base_test_status__):
        pass
    class WAIVE(__base_test_status__):
        pass

def _get_caller():
    stack = inspect.stack()
    return f"{stack[2].function}:{stack[2].lineno}"

def assertEQ(a, b, *args):
    if type(a) == type(b) and a == b:
        return True
    logging.error(f"[{args[0]}:{args[1]}] ASSERT: a == b failed, expected b={b}, got a={a}")
    return False

def assertNE(a, b, *args):
    if type(a) != type(b) or a != b:
        return True
    logging.error(f"[{_get_caller()}] ASSERT: a != b failed, expected b={b}, got a={a}")
    return False

def assertGT(a, b, *args):
    if type(a) == type(b) and a > b:
        return True
    logging.error(f"[{_get_caller()}] ASSERT: a > b failed, expected b={b}, got a={a}")
    return False

def assertGE(a, b, *args):
    if type(a) == type(b) and a >= b:
        return True
    logging.error(f"[{_get_caller()}] ASSERT: a >= b failed. expected b={b}, got a={a}")
    return False

def assertLT(a, b, *args):
    if type(a) == type(b) and a < b:
        return True
    logging.error(f"[{_get_caller()}] ASSERT: a < b failed, expected b={b}, got a={a}")
    return False

def assertLE(a, b, *args):
    if type(a) == type(b) and a <= b:
        return True
    logging.error(f"[{_get_caller()}] ASSERT: a <= b failed, expected b={b}, got a={a}")
    return False

def _in_place_modify(func):
    import os
    import ast
    import types
    import inspect
    class Replacer(ast.NodeTransformer):
        def __init__(self, file):
            self.file = file
        def visit_Call(self, node):
            call_name = ""
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            if isinstance(node.func, ast.Attribute) and \
                hasattr(node.func.value, "id") and \
                node.func.value.id == "testutils":
                call_name = node.func.attr
            if call_name in ("assertEQ", "assertNE", "assertGT",
                             "assertGE", "assertLT", "assertLE"):
                code = ast.unparse(node)
                new_code = f"if not {code[:-1]}, '{self.file}', {node.lineno}):" + \
                     " return testutils.TestStatus.FAIL"
                new_node = ast.parse(new_code)
                new_node = ast.copy_location(new_node.body[0], node)
                return new_node
            return node
    file = inspect.getsourcefile(func)
    source, lineno = inspect.getsourcelines(func)
    tree = ast.parse("".join(source))
    tree = ast.increment_lineno(tree, lineno - 1)
    new_tree = Replacer(os.path.basename(file)).visit(tree)
    code = compile(ast.unparse(new_tree), file, "exec")
    new_func = [m for m in code.co_consts if isinstance(m, types.CodeType)][0]
    new_func = types.FunctionType(new_func, globals(),
                                  func.__name__, func.__defaults__,
                                  func.__closure__)
    func.__code__ = new_func.__code__.replace(co_firstlineno=lineno)
    return func

def object_test(name, object, dependencies=[]):
    def test_decorator(test_func):
        test_func = _in_place_modify(test_func)
        test_func.__vtest__ = (name, object, dependencies)
        return test_func
    return test_decorator

def test(name, dependencies=[]):
    def test_decorator(test_func):
        test_func = _in_place_modify(test_func)
        test_func.__vtest__ = (name, None, dependencies)
        return test_func
    return test_decorator
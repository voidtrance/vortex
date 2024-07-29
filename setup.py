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
from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext
from distutils import sysconfig
import shutil
import sys
import re
import glob
import os.path
import pathlib
import regex

class BuildExtension(build_ext):
    #def __init__(self, *args, **kwargs):
    #    self.__subst = kwargs.pop("substitutions", [])
    #    super().__init__(*args, **kwargs)
    def move_files(self, filelist, dst_dir):
        dst_dir = pathlib.PosixPath(dst_dir)
        for file in [pathlib.PosixPath(x) for x in filelist]:
            base = file.name.split('.')[0]
            dst = dst_dir / f"{base}{file.suffix}"
            if dst.exists():
                 dst.unlink()
            shutil.move(file, dst)
    #def prep_sources(self):
    #    for ext in self.extensions:
    #        for source in ext.sources:
    #            with open(source, 'r') as fd:
    def run(self):
      #self.prep_sources()
      super().run()
      files = glob.glob(os.path.join(self.build_lib, "core.*.so"))
      self.move_files(files, "controllers")
      files = glob.glob(os.path.join(self.build_lib, "*.so"))
      self.move_files(files, "controllers/objects")

def find_all_objects():
    object_re = r'^__objects__\s*=\s*\[\s*(?:(?P<object>[^,]+),? ?)*\]$'
    object_reg = regex.compile(object_re, regex.MULTILINE)
    with open("controllers/objects/object_defs.py") as fd:
        content = fd.read()
    match = object_reg.search(content)
    if not match:
        return {}
    objects = [x.strip() for x in match.allcaptures()[1]]
    source_root = pathlib.PosixPath("src")
    build_objects = {}
    for object in objects:
        object = object.lower()
        build_objects[object] = \
            [(source_root / "controllers" / "objects" / f"{object}.c").as_posix()]
    return build_objects

def run_distutils(flags, debug=False, mem_leak_debug=False):
    object_extensions = []
    debug_sources = ["src/controllers/mem_debug.c"] if mem_leak_debug else []
    for object, sources in find_all_objects().items():
        e = Extension(name=object,
                      sources=sources + debug_sources + \
                      ["src/controllers/utils.c"],
                      include_dirs=["src/controllers"],
                      extra_compile_args=flags)
        object_extensions.append(e)

    core = Extension(name="core",
                     sources=["src/controllers/core.c",
                              "src/controllers/thread_control.c",
                              "src/controllers/utils.c"] + \
                              debug_sources,
                                libraries=["dl", "pthread"],
                                extra_compile_args=flags)
    setup(name="emulator", version="0.0.1",
          packages=find_packages("."),
          ext_modules=[core] + object_extensions,
          cmdclass={"build_py": BuildExtension})

def modify_flags(debug, mem_leak_debug):
    flags = []
    if sys.platform == 'linux' or sys.platform == 'darwin':
        if debug:
            flags.append("-DVORTEX_DEBUG")
        else:
            sysconfig.get_config_var(None)  # to fill up _config_vars
            d = sysconfig._config_vars
            for x in ['OPT', 'CFLAGS', 'PY_CFLAGS', 'PY_CORE_CFLAGS', 'CONFIGURE_CFLAGS', 'LDSHARED']:
                d[x] = re.sub(' -g ', ' ', d[x])
                d[x] = re.sub('^-g ', '',  d[x])
                d[x] = re.sub(' -g$', '',  d[x])
        if mem_leak_debug:
            flags.append("-DVORTEX_MEM_LEAK")
    return flags

is_debug = "--debug" in sys.argv
is_mem_leak_debug = False
if "--mem-leak-debug" in sys.argv:
    is_mem_leak_debug = True
    sys.argv.remove("--mem-leak-debug")
flags = modify_flags(is_debug, is_mem_leak_debug)
run_distutils(flags, is_debug, is_mem_leak_debug)



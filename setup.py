from setuptools import setup, Extension, find_packages
from setuptools.command.build_ext import build_ext
import shutil
import glob
import os.path
import pathlib

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
      print(files)
      self.move_files(files, "controllers/objects")

def find_all_objects():
    with open("controllers/objects/object_defs.py") as fd:
        for line in fd:
            if line.startswith("__objects__"):
                defs = line.strip()
                break
    objects = [x.strip() for x in defs[:-1].partition("[")[2].split(",")]
    print(objects)
    source_root = pathlib.PosixPath("src")
    build_objects = {}
    for object in objects:
        object = object.lower()
        build_objects[object] = \
            [(source_root / "controllers" / "objects" / f"{object}.c").as_posix()]
    return build_objects

object_extensions = []
for object, sources in find_all_objects().items():
     e = Extension(name=object,
                   sources=sources + ["src/controllers/utils.c"],
                   include_dirs=["src/controllers"])
     object_extensions.append(e)

setup(name="emulator", version="0.0.1",
      packages=find_packages("."),
      ext_modules=[Extension(name="core",
                            sources=["src/controllers/core.c",
                                     "src/controllers/thread_control.c"],
                            libraries=["dl", "pthread"])] + \
                   object_extensions,
      cmdclass={"build_py": BuildExtension})

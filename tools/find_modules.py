import regex
import sys
import os

def find_all_objects():
    object_re = r'^__objects__\s*=\s*\[\s*(?:(?P<object>[^,]+),? ?)*\]$'
    object_reg = regex.compile(object_re, regex.MULTILINE)
    with open(os.path.join(sys.argv[1], "controllers/objects/object_defs.py")) as fd:
        content = fd.read()
    match = object_reg.search(content)
    if not match:
        return {}
    objects = [x.strip().lower() for x in match.allcaptures()[1]]
    return objects

for object in find_all_objects():
    print(object)
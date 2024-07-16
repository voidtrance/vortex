import lib.ext_enum
import controllers.core as cc

ModuleTypes = lib.ext_enum.ExtIntEnum(
    "ModuleTypes", {n.upper(): (v, n) for v, n in cc.OBJECT_TYPE_NAMES.items()})

ModuleEvents = lib.ext_enum.ExtIntEnum(
    "ModuleEvents", {n.upper(): (v, n) for v, n in cc.OBJECT_EVENT_NAMES.items()})

import lib.ext_enum
import controllers.core as cc

@lib.ext_enum.unique
class ModuleTypes(lib.ext_enum.ExtIntEnum):
    NONE = (cc.OBJECT_TYPE_NONE, cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_NONE])
    STEPPER = (cc.OBJECT_TYPE_STEPPER,
               cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_STEPPER])
    DIGITAL_PIN = (cc.OBJECT_TYPE_DIGITAL_PIN,
                   cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_DIGITAL_PIN])
    PWM_PIN = (cc.OBJECT_TYPE_PWM_PIN,
               cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_PWM_PIN])
    ENDSTOP = (cc.OBJECT_TYPE_ENDSTOP,
               cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_ENDSTOP])
    FAN = (cc.OBJECT_TYPE_FAN, cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_FAN])
    HEATER = (cc.OBJECT_TYPE_HEATER,
              cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_HEATER])
    THERMISTOR = (cc.OBJECT_TYPE_THERMISTOR,
                  cc.OBJECT_TYPE_NAMES[cc.OBJECT_TYPE_THERMISTOR])

<style type="text/css" rel="stylesheet">
table > thead:has(> tr > th:empty):not(:has(> tr > th:not(:empty))) {
  display: none;
}
</style>

# Klipper Command Reference

## *identify*
```
identify offset=%u count=%c
identify_response offset=%u data=%.*s
```

| Command/Response | Argument | Description |
| - | - | - |
| *identify* | offset | The offset from the beginning of the identity data to be sent back |
| | count | The number of bytes to send in the *identify_response* |
| *identify_reponse* | offset | The offset from the beginning of the that is being sent back. |
|  | data | The portion of the identiy data requested |

The identity data is `zlib` compressed JSON dictionary with the following content:

| Key | Value Type | Description |
| - | - | - |
| version | string | MCU firmware version. This is used to compare the MCU firmware with the host version to ensure that the two match sufficiently |
| commands | dictionary | A dictionary containing all supported commands by the MCU, where the keys are the command (see below) and the values are the assigned command IDs |
| responses | dictionary | A dictionary containing all supported responses by the MCU, where the keys are the responses and the values are the assigned IDs |
| enumerations | dictionary | |
| config | dictionary | |
| build_version | string | MCU firmware build information |

## *get_clock*
```
get_clock
clock clock=%u
```

| Command/Response | Argument | Description |
|-|-|-| 
| `get_clock` | | Requests current controller clock value |
| `clock clock=%u` | clock | Current controller tick value as a 32bit integer |

## *get_uptime*
```
get_uptime
uptime high=%u clock=%u
```

| Command/Response | Argument | Description |
|-|-|-|
| `get_uptime` | | Request controller uptime |
| `uptime high=%u clock=%u` | high | Higher 32 bits of the controller uptime counter |
| | clock | Lower 32 bits of the controller uptime counter |

## *finalize_config*

The *finalize_config* command is sent to the controller after all OIDs
have been allocated and configured.

```
finalize_config crc=%u
```

| Command/Response | Argument | Description |
|-|-|-|
| *finalize_config* | crc | The configuration's CRC value. This value shold be saved and returned by the `get_config` response |

## *get_config*
```
get_config
config is_config=%c crc=%u is_shutdown=%c move_count=%hu
```

| Command/Response | Argument | Description |
|-|-|-|
| *get_config* | | Request controller configuration state |
| *config* | is_config | Is the controller still configuring. Normall, this indicates whether the controller has allocated its move queue |
| | crc | The configuration CRC set by the *finalize_config* command |
| | is_shutdown | Is the controller in the "shutdown" state |
| | move_count | The size of the move queue |

## *shutdown*

The *shutdown* response is sent by the controller when it enters the
"shutdown" state due to an error. This is an asynchronous response that can be sent by the controller at any time.

```
shutdown clock=%u static_string_id=%hu
```

| Command/Response | Argument | Description |
|-|-|-|
| *shutdown* | clock | The lower 32 bits of the current controller clock tick value |
| | static_string_id | The ID of the error string as defined by the *identiry_response* data |

## *is_shutdown*

The *is_shutdown* response is sent by the controller for any command
that is received after the controller has entered the "shutdown" state.

```
is_shutdown static_string_id=%hu
```

| Command/Response | Argument | Description |
|-|-|-|
| *is_shutdown* | static_string_id | The ID of the error that caused the shutdown as defined by the *identify_response* data |

## *clear_shutdown*
```
clear_shutdown
```

| Command/Response | Argument | Description |
|-|-|-|
| *clear_shutdown* | | Reset the controller |

## *allocate_oids*

OIDs are a way for Klipper to address individual components of the
controller. An OID is allocated for each entity link pins or
synchronization trackers.

```
allocate_oids count=%c
```

| Command/Response | Argument | Description |
|-|-|-|
| *allocate_oids* | count | The number of OIDs to allocate |

## *config_analog_in*
```
config_analog_in oid=%c pin=%u
```

| Command/Response | Argument | Description |
|-|-|-|
| *config_analog_in* | oid | Configure OID as an analog input pin |
| | pin | The pin that is associated with the OID |

## *query_analog_in*

The *query_analog_in* command sets up a analog input sample cycle. The
controller is required to respond at intervals specified by the command with the sum of all sampled values.

```
query_analog_in oid=%c clock=%u sample_ticks=%u sample_count=%c rest_ticks=%u min_value=%hu max_value=%hu range_check_count=%c
analog_in_state oid=%c next_clock=%u value=%hu
```

| Command/Response | Argument | Description |
|-|-|-|
| *query_analog_in* | oid | The OID which is being queried |
| | clock | On which controller clock tick the sampleing should start |
| | sample_ticks | Duration (in clock ticks) between sampling |
| | sample_count | The number of sample to perform before sending the response |
| | rest_ticks | Duration (in clock ticks) between restarting the sampling cycle after the response has been sent |
| | min_value | The minimum value allowed for the sampled value |
| | max_value | The maximum value allowed for the sampled value |
| | range_check_count | The number of consequitive samples outside of the (min_value,max_value) range |
| *analog_in_state* | oid | The OID generating the response |
| | next_clock | The clock time when sampleing will restart |
| | value | The sum of all samples |

## *config_digital_out*
```
config_digital_out oid=%c pin=%u value=%c default_value=%c max_duration=%u
```

| Command/Response | Argument | Description |
|-|-|-|
| *config_digital_out* | oid | Configure OID as a digital output pin |
| | pin | The pin that is associated with the OID |
| | value | The initail value of the pin |
| | default_value | The default value of the pin |
| | max_duration | |

## *set_digital_out_pwm_cycle*
```
set_digital_out_pwm_cycle oid=%c cycle_ticks=%u
```

| Command/Response | Argument | Description |
|-|-|-|
| *set_digital_out_pwm_cycle* | oid | The OID for which the PWM cycle time is being setup |
| | cycle_ticks | The clock tick count specifying the duration of one PWM cycle (ON duration + OFF duration) |

## *queue_digital_out*
```
queue_digital_out oid=%c clock=%u on_ticks=%u
```

|
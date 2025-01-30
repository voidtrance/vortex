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
import enum
from argparse import Namespace
from vortex.lib.ext_enum import ExtIntEnum, auto, unique

@unique
class ResponseTypes(ExtIntEnum):
    ACK = auto()
    NACK = auto()
    RESPONSE = auto()

class KlipperProtoFlags(enum.Flag):
    HF_NONE = 0
    HF_IN_SHUTDOWN = auto()

KLIPPER_PROTOCOL = Namespace(adccmds=Namespace(), basecmd=Namespace(), shutdown=Namespace(), buttons=Namespace(),
            debugcmds=Namespace(), endstop=Namespace(), gpiocmds=Namespace(), lcd_hd44780=Namespace(),
            lcd_st7920=Namespace(),	neopixel=Namespace(), pulse_counter=Namespace(), pwmcmds=Namespace(),
            spi_software=Namespace(), stepper=Namespace(), thermocouple=Namespace(), tmcuart=Namespace(),
            trsync=Namespace(),	sdiocmds=Namespace(), i2c_software=Namespace(), spicmds=Namespace(),
            sensor_adxl345=Namespace(),	sensor_angle=Namespace(), sensor_lis2dw=Namespace(),
            sensor_mpu9250=Namespace(), sensor_ads1220=Namespace(),	sensor_hx71x=Namespace(),
            sensor_ldc1612=Namespace(), i2ccmds=Namespace(), tasks=Namespace())

# adccmds commands
KLIPPER_PROTOCOL.adccmds.config_analog_in = Namespace(command="config_analog_in oid=%c pin=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.adccmds.query_analog_in = Namespace(command="query_analog_in oid=%c clock=%u sample_ticks=%u sample_count=%c rest_ticks=%u min_value=%hu max_value=%hu range_check_count=%c", flags=KlipperProtoFlags.HF_NONE, response="analog_in_state oid=%c next_clock=%u value=%hu")

# basecmd commands
KLIPPER_PROTOCOL.basecmd.allocate_oids = Namespace(command="allocate_oids count=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.basecmd.get_config = Namespace(command="get_config", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response="config is_config=%c crc=%u is_shutdown=%c move_count=%hu")
KLIPPER_PROTOCOL.basecmd.finalize_config = Namespace(command="finalize_config crc=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.basecmd.get_clock = Namespace(command="get_clock", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response="clock clock=%u")
KLIPPER_PROTOCOL.basecmd.get_uptime = Namespace(command="get_uptime", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response="uptime high=%u clock=%u")
KLIPPER_PROTOCOL.basecmd.emergency_stop = Namespace(command="emergency_stop", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response=None)
KLIPPER_PROTOCOL.basecmd.clear_shutdown = Namespace(command="clear_shutdown", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response=None)
KLIPPER_PROTOCOL.basecmd.identify = Namespace(command="identify offset=%u count=%c", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response="identify_response offset=%u data=%.*s")

# shutdown commands
KLIPPER_PROTOCOL.shutdown.shutdown = Namespace(command=None, flags=KlipperProtoFlags.HF_NONE, response="shutdown clock=%u static_string_id=%hu")
KLIPPER_PROTOCOL.shutdown.is_shutdown = Namespace(command=None, flags=KlipperProtoFlags.HF_NONE, response="is_shutdown static_string_id=%hu")
# basecmd tasts
KLIPPER_PROTOCOL.tasks.stats = Namespace(command=None, flags=KlipperProtoFlags.HF_NONE, interval="5000000", response="stats count=%u sum=%u sumsq=%u")

# buttons commands
KLIPPER_PROTOCOL.buttons.config_buttons = Namespace(command="config_buttons oid=%c button_count=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.buttons.buttons_add = Namespace(command="buttons_add oid=%c pos=%c pin=%u pull_up=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.buttons.buttons_query = Namespace(command="buttons_query oid=%c clock=%u rest_ticks=%u retransmit_count=%c invert=%c", flags=KlipperProtoFlags.HF_NONE, response="buttons_state oid=%c ack_count=%c state=%*s")
KLIPPER_PROTOCOL.buttons.buttons_ack = Namespace(command="buttons_ack oid=%c count=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# debugcmds commands
KLIPPER_PROTOCOL.debugcmds.debug_read = Namespace(command="debug_read order=%c addr=%u", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response="debug_result val=%u")
KLIPPER_PROTOCOL.debugcmds.debug_write = Namespace(command="debug_write order=%c addr=%u val=%u", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response=None)
KLIPPER_PROTOCOL.debugcmds.debug_ping = Namespace(command="debug_ping data=%*s", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response="pong data=%*s")
KLIPPER_PROTOCOL.debugcmds.debug_nop = Namespace(command="debug_nop", flags=KlipperProtoFlags.HF_IN_SHUTDOWN, response=None)

# endstop commands
KLIPPER_PROTOCOL.endstop.config_endstop = Namespace(command="config_endstop oid=%c pin=%c pull_up=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.endstop.endstop_home = Namespace(command="endstop_home oid=%c clock=%u sample_ticks=%u sample_count=%c rest_ticks=%u pin_value=%c trsync_oid=%c trigger_reason=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.endstop.endstop_query_state = Namespace(command="endstop_query_state oid=%c", flags=KlipperProtoFlags.HF_NONE, response="endstop_state oid=%c homing=%c next_clock=%u pin_value=%c")

# gpiocmds commands
KLIPPER_PROTOCOL.gpiocmds.config_digital_out = Namespace(command="config_digital_out oid=%c pin=%u value=%c default_value=%c max_duration=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.gpiocmds.set_digital_out_pwm_cycle = Namespace(command="set_digital_out_pwm_cycle oid=%c cycle_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.gpiocmds.queue_digital_out = Namespace(command="queue_digital_out oid=%c clock=%u on_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.gpiocmds.update_digital_out = Namespace(command="update_digital_out oid=%c value=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.gpiocmds.set_digital_out = Namespace(command="set_digital_out pin=%u value=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# lcd_hd44780 commands
KLIPPER_PROTOCOL.lcd_hd44780.config_hd44780 = Namespace(command="config_hd44780 oid=%c rs_pin=%u e_pin=%u d4_pin=%u d5_pin=%u d6_pin=%u d7_pin=%u delay_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.lcd_hd44780.hd44780_send_cmds = Namespace(command="hd44780_send_cmds oid=%c cmds=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.lcd_hd44780.hd44780_send_data = Namespace(command="hd44780_send_data oid=%c data=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)

# lcd_st7920 commands
KLIPPER_PROTOCOL.lcd_st7920.config_st7920 = Namespace(command="config_st7920 oid=%c cs_pin=%u sclk_pin=%u sid_pin=%u sync_delay_ticks=%u cmd_delay_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.lcd_st7920.st7920_send_cmds = Namespace(command="st7920_send_cmds oid=%c cmds=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.lcd_st7920.st7920_send_data = Namespace(command="st7920_send_data oid=%c data=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)

# neopixel commands
KLIPPER_PROTOCOL.neopixel.config_neopixel = Namespace(command="config_neopixel oid=%c pin=%u data_size=%hu bit_max_ticks=%u reset_min_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.neopixel.neopixel_update = Namespace(command="neopixel_update oid=%c pos=%hu data=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.neopixel.neopixel_send = Namespace(command="neopixel_send oid=%c", flags=KlipperProtoFlags.HF_NONE, response="neopixel_result oid=%c success=%c")

# pulse_counter commands
KLIPPER_PROTOCOL.pulse_counter.config_counter = Namespace(command="config_counter oid=%c pin=%u pull_up=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.pulse_counter.query_counter = Namespace(command="query_counter oid=%c clock=%u poll_ticks=%u sample_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response="counter_state oid=%c next_clock=%u count=%u count_clock=%u")

# pwmcmds commands
KLIPPER_PROTOCOL.pwmcmds.config_pwm_out = Namespace(command="config_pwm_out oid=%c pin=%u cycle_ticks=%u value=%hu default_value=%hu max_duration=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.pwmcmds.queue_pwm_out = Namespace(command="queue_pwm_out oid=%c clock=%u value=%hu", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.pwmcmds.set_pwm_out = Namespace(command="set_pwm_out pin=%u cycle_ticks=%u value=%hu", flags=KlipperProtoFlags.HF_NONE, response=None)

# spi_software commands
KLIPPER_PROTOCOL.spi_software.spi_set_software_bus = Namespace(command="spi_set_software_bus oid=%c miso_pin=%u mosi_pin=%u sclk_pin=%u mode=%u rate=%u", flags=KlipperProtoFlags.HF_NONE, response=None)

# stepper commands
KLIPPER_PROTOCOL.stepper.config_stepper = Namespace(command="config_stepper oid=%c step_pin=%c dir_pin=%c invert_step=%c step_pulse_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.stepper.queue_step = Namespace(command="queue_step oid=%c interval=%u count=%hu add=%hi", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.stepper.set_next_step_dir = Namespace(command="set_next_step_dir oid=%c dir=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.stepper.reset_step_clock = Namespace(command="reset_step_clock oid=%c clock=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.stepper.stepper_get_position = Namespace(command="stepper_get_position oid=%c", flags=KlipperProtoFlags.HF_NONE, response="stepper_position oid=%c pos=%i")
KLIPPER_PROTOCOL.stepper.stepper_stop_on_trigger = Namespace(command="stepper_stop_on_trigger oid=%c trsync_oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# thermocouple commands
KLIPPER_PROTOCOL.thermocouple.config_thermocouple = Namespace(command="config_thermocouple oid=%c spi_oid=%c thermocouple_type=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.thermocouple.query_thermocouple = Namespace(command="query_thermocouple oid=%c clock=%u rest_ticks=%u min_value=%u max_value=%u max_invalid_count=%c", flags=KlipperProtoFlags.HF_NONE, response="thermocouple_result oid=%c next_clock=%u value=%u fault=%c")

# tmcuart commands
KLIPPER_PROTOCOL.tmcuart.config_tmcuart = Namespace(command="config_tmcuart oid=%c rx_pin=%u pull_up=%c tx_pin=%u bit_time=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.tmcuart.tmcuart_send = Namespace(command="tmcuart_send oid=%c write=%*s read=%c", flags=KlipperProtoFlags.HF_NONE, response="tmcuart_response oid=%c read=%*s")

# trsync commands
KLIPPER_PROTOCOL.trsync.config_trsync = Namespace(command="config_trsync oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.trsync.trsync_start = Namespace(command="trsync_start oid=%c report_clock=%u report_ticks=%u expire_reason=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.trsync.trsync_set_timeout = Namespace(command="trsync_set_timeout oid=%c clock=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.trsync.trsync_trigger = Namespace(command="trsync_trigger oid=%c reason=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.trsync.trsync_state = Namespace(command=None, flags=KlipperProtoFlags.HF_NONE, interval=0, response="trsync_state oid=%c can_trigger=%c trigger_reason=%c clock=%u")

# sdiocmds commands
KLIPPER_PROTOCOL.sdiocmds.config_sdio = Namespace(command="config_sdio oid=%c blocksize=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sdiocmds.sdio_set_bus = Namespace(command="sdio_set_bus oid=%c sdio_bus=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sdiocmds.sdio_set_speed = Namespace(command="sdio_set_speed oid=%c speed=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sdiocmds.sdio_send_command = Namespace(command="sdio_send_command oid=%c cmd=%c argument=%u wait=%c", flags=KlipperProtoFlags.HF_NONE, response="sdio_send_command_response oid=%c error=%c response=%*s")
KLIPPER_PROTOCOL.sdiocmds.sdio_read_data = Namespace(command="sdio_read_data oid=%c cmd=%c argument=%u", flags=KlipperProtoFlags.HF_NONE, response="sdio_read_data_response oid=%c error=%c read=%u")
KLIPPER_PROTOCOL.sdiocmds.sdio_write_data = Namespace(command="sdio_write_data oid=%c cmd=%c argument=%u", flags=KlipperProtoFlags.HF_NONE, response="sdio_write_data_response oid=%c error=%c write=%u")
KLIPPER_PROTOCOL.sdiocmds.sdio_read_data_buffer = Namespace(command="sdio_read_data_buffer oid=%c offset=%u len=%c", flags=KlipperProtoFlags.HF_NONE, response="sdio_read_data_buffer_response oid=%c data=%*s")
KLIPPER_PROTOCOL.sdiocmds.sdio_write_data_buffer = Namespace(command="sdio_write_data_buffer oid=%c offset=%u data=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)

# i2c_software commands
KLIPPER_PROTOCOL.i2c_software.i2c_set_software_bus = Namespace(command="i2c_set_software_bus oid=%c scl_pin=%u sda_pin=%u rate=%u address=%u", flags=KlipperProtoFlags.HF_NONE, response=None)

# spicmds commands
KLIPPER_PROTOCOL.spicmds.config_spi = Namespace(command="config_spi oid=%c pin=%u cs_active_high=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.spicmds.config_spi_without_cs = Namespace(command="config_spi_without_cs oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.spicmds.spi_set_bus = Namespace(command="spi_set_bus oid=%c spi_bus=%u mode=%u rate=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.spicmds.spi_transfer = Namespace(command="spi_transfer oid=%c data=%*s", flags=KlipperProtoFlags.HF_NONE, response="spi_transfer_response oid=%c response=%*s")
KLIPPER_PROTOCOL.spicmds.spi_send = Namespace(command="spi_send oid=%c data=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.spicmds.config_spi_shutdown = Namespace(command="config_spi_shutdown oid=%c spi_oid=%c shutdown_msg=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)

# sensor_adxl345 commands
KLIPPER_PROTOCOL.sensor_adxl345.config_adxl345 = Namespace(command="config_adxl345 oid=%c spi_oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_adxl345.query_adxl345 = Namespace(command="query_adxl345 oid=%c rest_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_adxl345.query_adxl345_status = Namespace(command="query_adxl345_status oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# sensor_angle commands
KLIPPER_PROTOCOL.sensor_angle.config_spi_angle = Namespace(command="config_spi_angle oid=%c spi_oid=%c spi_angle_type=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_angle.query_spi_angle = Namespace(command="query_spi_angle oid=%c clock=%u rest_ticks=%u time_shift=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_angle.spi_angle_transfer = Namespace(command="spi_angle_transfer oid=%c data=%*s", flags=KlipperProtoFlags.HF_NONE, response="spi_angle_transfer_response oid=%c clock=%u response=%*s")

# sensor_lis2dw commands
KLIPPER_PROTOCOL.sensor_lis2dw.config_lis2dw = Namespace(command="config_lis2dw oid=%c spi_oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_lis2dw.query_lis2dw = Namespace(command="query_lis2dw oid=%c rest_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_lis2dw.query_lis2dw_status = Namespace(command="query_lis2dw_status oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# sensor_mpu9250 commands
KLIPPER_PROTOCOL.sensor_mpu9250.config_mpu9250 = Namespace(command="config_mpu9250 oid=%c i2c_oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_mpu9250.query_mpu9250 = Namespace(command="query_mpu9250 oid=%c rest_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_mpu9250.query_mpu9250_status = Namespace(command="query_mpu9250_status oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# sensor_ads1220 commands
KLIPPER_PROTOCOL.sensor_ads1220.config_ads1220 = Namespace(command="config_ads1220 oid=%c spi_oid=%c data_ready_pin=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_ads1220.query_ads1220 = Namespace(command="query_ads1220 oid=%c rest_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_ads1220.query_ads1220_status = Namespace(command="query_ads1220_status oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# sensor_hx71x commands
KLIPPER_PROTOCOL.sensor_hx71x.config_hx71x = Namespace(command="config_hx71x oid=%c gain_channel=%c dout_pin=%u sclk_pin=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_hx71x.query_hx71x = Namespace(command="query_hx71x oid=%c rest_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_hx71x.query_hx71x_status = Namespace(command="query_hx71x_status oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# sensor_ldc1612 commands
KLIPPER_PROTOCOL.sensor_ldc1612.config_ldc1612 = Namespace(command="config_ldc1612 oid=%c i2c_oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_ldc1612.config_ldc1612_with_intb = Namespace(command="config_ldc1612_with_intb oid=%c i2c_oid=%c intb_pin=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_ldc1612.ldc1612_setup_home = Namespace(command="ldc1612_setup_home oid=%c clock=%u threshold=%u trsync_oid=%c trigger_reason=%c error_reason=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_ldc1612.query_ldc1612_home_state = Namespace(command="query_ldc1612_home_state oid=%c", flags=KlipperProtoFlags.HF_NONE, response="ldc1612_home_state oid=%c homing=%c trigger_clock=%u")
KLIPPER_PROTOCOL.sensor_ldc1612.query_ldc1612 = Namespace(command="query_ldc1612 oid=%c rest_ticks=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.sensor_ldc1612.query_status_ldc1612 = Namespace(command="query_status_ldc1612 oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)

# i2ccmds commands
KLIPPER_PROTOCOL.i2ccmds.config_i2c = Namespace(command="config_i2c oid=%c", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.i2ccmds.i2c_set_bus = Namespace(command="i2c_set_bus oid=%c i2c_bus=%u rate=%u address=%u", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.i2ccmds.i2c_write = Namespace(command="i2c_write oid=%c data=%*s", flags=KlipperProtoFlags.HF_NONE, response=None)
KLIPPER_PROTOCOL.i2ccmds.i2c_read = Namespace(command="i2c_read oid=%c reg=%*s read_len=%u", flags=KlipperProtoFlags.HF_NONE, response="i2c_read_response oid=%c response=%*s")


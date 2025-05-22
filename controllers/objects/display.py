# vortex - GCode machine emulator
# Copyright (C) 2025 Mitko Haralanov
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
import vortex.controllers.objects.vobj_base as vobj
from vortex.core import ObjectTypes, PIN_NAME_SIZE
import vortex.lib.logging as logging
import ctypes

logger = logging.getLogger("vortex.core.objects.display")

class DisplayReadArgs(ctypes.Structure):
    _fields_ = [("len", ctypes.c_uint16)]

class DisplayWriteArgs(ctypes.Structure):
    _fields_ = [("is_data", ctypes.c_bool),
                ("len", ctypes.c_uint),
                ("data", ctypes.c_uint8 * 256)]

class DisplayResetArgs(ctypes.Structure):
    _fields_ = []

class DisplayState(ctypes.Structure):
    _fields_ = [("type", ctypes.c_char * 16),
                ("cs_pin", ctypes.c_char * PIN_NAME_SIZE),
                ("reset_pin",  ctypes.c_char * PIN_NAME_SIZE),
                ("data_pin", ctypes.c_char * PIN_NAME_SIZE),
                ("spi_miso_pin", ctypes.c_char * PIN_NAME_SIZE),
                ("spi_mosi_pin", ctypes.c_char * PIN_NAME_SIZE),
                ("spi_sclk_pin", ctypes.c_char * PIN_NAME_SIZE),
                ("width", ctypes.c_uint16),
                ("height", ctypes.c_uint16),
                ("data", ctypes.c_uint8 * 1024)]

class Display(vobj.VirtualObjectBase):
    type = ObjectTypes.DISPLAY
    commands = [(0, "read", DisplayReadArgs, None),
                (1, "write", DisplayWriteArgs, None),
                (2, "reset", DisplayResetArgs, None)]
    state  = DisplayState
    def get_status(self):
        return vars(self.config)
    def exec_command(self, cmd_id, cmd, opts):
        ret = super().exec_command(cmd_id, cmd, opts)
        if ret < 0:
            return ret
        # unknown command        
        return 1
    
class UC1701(Display):
    WIDTH = 132
    HEIGHT = 65
    REGS = {"SL": 6, "CA": 8, "PA": 4, "BR": 1, "PM": 6, "PC": 6, "CR": 8,
            "AC3": 1, "DC": 3, "LC": 2, "APC0": 8, "APC1": 8, "BZ": 1,
             "MX": 1, "DE": 1, "RST": 1}
    DEFAULT_CONFIG = { "SL": 0, "CA": 0, "PA": 0, "BR": 0, "PM": 0x20,
                       "PC": 0x20, "CR": 0, "AC3": 0, "DC": 0, "LC": 0,
                       "APC0": 0x90, "APC1": 0, "BZ": 0, "MX": 0,
                       "DE": 0, "RST": 0 }
    CMD_TABLE = {
        0x0: "set_column_address_lsb",
        0x1: "set_column_address_msb",
        0x2: ["set_resistor_ratio", "set_power_control"],
        #0x4: "set_scroll_line",
        0xB: "set_page_address",
        0x81: "set_volume",
        0xA0: "set_seg_direction_normal",
        0xA1: "set_seg_direction_reverse",
        0xA2: "set_lcd_bias",
        0xA4: "disable_pixels",
        0xA5: "enable_pixels",
        0xA6: "invert_display",
        0xAC: "set_static_indicater_off",
        0xAD: "set_static_indicater_on",
        0xAE: "display_off",
        0xAF: "display_on",
        0xC: "set_com_direction",
        0xE0: "set_cursor_update_mode",
        0xE2: "display_reset",
        0xE3: "noop",
        0xEE: "reset_cursor_update_mode",
        0xF8: "set_boost_ratio",
        0xFA: "set_adv_program_control_0",
        0xFB: "set_adv_program_control_1"
    }
    def __init__(self, *args):
        super().__init__(*args)
        self.display_reset(0)
    def _command(self, byte):
        return (byte >> 4) & 0xf
    def exec_command(self, cmd_id, cmd, opts):
        logger.debug(f"Display.exec_command({cmd_id}, {cmd}, {opts})")
        ret = super().exec_command(cmd_id, cmd, opts)
        if ret != 1:
            return ret
        if cmd == 0:
            self._cmd_complete(cmd_id, 0)
        elif cmd == 1:
            data = opts.get("data")
            len = opts.get("len")
            if opts.get("is_data", False):
                self.process_data(data[:len])
            else:
                self.process_commands(data[:len])
            self._cmd_complete(cmd_id, 0)
        elif cmd == 2:
            self.reset()
            self._cmd_complete(cmd_id, 0)
        else:
            raise ValueError(f"Unknown command {cmd} for {self.type}")
        return 0
    def process_commands(self, data):
        i = 0
        while i < len(data):
            byte = data[i]
            cmd = self.CMD_TABLE.get(byte >> 4, self.CMD_TABLE.get(byte, None))
            logger.debug("process_command(0x%02x): cmd = %s" % (byte, cmd))
            if cmd is None:
                if byte >> 6 == 0x1:
                    handler = self.set_scroll_line
            elif isinstance(cmd, list):
                handler = getattr(self, cmd[(byte >> 3) & 0x1], None)
            else:
                handler = getattr(self, cmd, None)
            if handler is None:
                logger.error("process_command(0x%02x): Unknown command" % byte)
                return
            if cmd in ("set_status_indicator_on", "set_boost_ratio", 
                       "set_volume", "set_test_control",
                       "set_adv_program_control_0", "set_adv_program_control_1"):
                i += 1
                handler(byte, data[i])
            else:
                handler(byte)
            i += 1
        self.update_state()
    def process_data(self, data):
        pa = self._get_bits("PA", 0, 3)
        ca = self._get_bits("CA")
        for byte in data:
            logger.debug("process_data @ [%d:%d] = 0x%02x" % (pa, ca, byte))
            self.display[ca][pa] = byte
            ca += 1
            if ca >= self.WIDTH:
                ca = 0
                pa = (pa + 1) % int((self.HEIGHT + 7) / 8)
    def get_status(self):
        status = super().get_status()
        status.update({"width": self.WIDTH,
                       "height": self.HEIGHT,
                       "data": self.display})
        return status
    def _set_bits(self, reg, lsb, msb, value):
        mask = ((1 << (msb - lsb + 1)) - 1) << lsb
        self.state[reg] = (self.state[reg] & ~mask) | (value << lsb) & mask
    def _get_bits(self, reg, lsb=None, msb=None):
        lsb = 0 if lsb is None else lsb
        msb = self.REGS[reg] if msb is None else msb
        return (self.state[reg] >> lsb) & ((1 << (msb - lsb + 1)) - 1)
    def set_column_address_lsb(self, byte):
        self._set_bits("CA", 0, 3, byte)
    def set_column_address_msb(self, byte):
        self._set_bits("CA", 4, 7, byte)
    def set_resistor_ratio(self, byte):
        self._set_bits("PC", 3, 5, byte)
    def set_power_control(self, byte):
        self._set_bits("PC", 0, 2, byte)
    def set_scroll_line(self, byte):
        self._set_bits("SL", 0, 5, byte)
    def set_page_address(self, byte):
        self._set_bits("PA", 0, 3, byte)
    def set_volume(self, byte, data_byte):
        self._set_bits("PM", 0, 5, data_byte)
    def set_seg_direction_normal(self, byte):
        self._set_bits("LC", 0, 0, byte)
    def set_seg_direction_reverse(self, byte):
        self._set_bits("LC", 1, 1, byte)
    def set_lcd_bias(self, byte):
        self._set_bits("BR", 0, 0, byte)
    def disable_pixels(self, byte):
        self._set_bits("DC", 1, 1, 0)
    def enable_pixels(self, byte):
        self._set_bits("DC", 1, 1, 1)
    def invert_display(self, byte):
        self._set_bits("DC", 0, 0, byte)
    def set_static_indicater_off(self, byte):
        return
    def set_static_indicater_on(self, byte):
        return
    def display_off(self, byte):
        self._set_bits("DC", 2, 2, 0)
    def display_on(self, byte):
        self._set_bits("DC", 2, 2, 1)
    def set_com_direction(self, byte):
        self._set_bits("LC", 1, 1, (byte & 0xf) >> 3)
    def set_cursor_update_mode(self, byte):
        self.state["AC3"] = 1
        self.state["CR"] = self.state["CA"]
    def display_reset(self, byte):
        self.display = [[0] * int((self.HEIGHT + 7) / 8) for _ in range(self.WIDTH)]
        self.state = self.DEFAULT_CONFIG.copy()
    def noop(self, byte):
        return
    def reset_cursor_update_mode(self, byte):
        self.state["AC3"] = 0
        self.state["CA"] = self.state["CR"]
    def set_boost_ratio(self, byte, data_byte):
        return
    def set_adv_program_control_0(self, byte, data_byte):
        return
    def set_adv_program_control_1(self, byte, data_byte):
        return
    def reset(self):
        self.display_reset(0xE2)
        return
    def update_state(self):
        return

def DisplayFactory(config, obj_lookup, obj_query, cmd_complete, event_submit):
    if config.type is None:
        raise ValueError("DisplayProxy: type is not set")
    if config.type == "uc1701":
        return UC1701(config, obj_lookup, obj_query, cmd_complete, event_submit)
    raise ValueError(f"DisplayProxy: Unknown type {config.type}")
#!/usr/bin/env python3
# vortex - GCode machine emulator
# Copyright (C) 2024-2025  Mitko Haralanov
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
import gi
import sys
import time
import socket
import pickle
import threading
import vortex.emulator.remote.api as api
from argparse import Namespace
from vortex.core import ObjectKlass
from vortex.core.kinematics import AxisType
from vortex.core.lib.logging import LOG_LEVELS
gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
gi.require_version("Vte", "3.91")
from gi.repository import Gtk, GLib, GObject, GdkPixbuf, Gdk, Gio, Adw
from gi.repository import Vte

style = """
button#reset-button { background-image: none; background-color: red; color: white;}
frame > label { font-size: 14pt;}
toastoverlay > toast { background-color: gray; border-radius: 20px; }
toastoverlay > toast > widget { margin: 10px; }
banner { background-color: #22346e; }
"""

class ConnectionTermiated(Exception):
    pass

class Communicator:
    SOCKET = "/tmp/vortex-remote"
    def __init__(self):
        self.connected = False

    def connect(self):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.socket.connect(self.SOCKET)
            self.connected = True
        except (FileNotFoundError, ConnectionRefusedError):
            return False
        return True

    def disconnect(self):
        self.socket.close()
        self.socket = None
        self.connected = False

    def send(self, request):
        if self.connected:
            self.socket.sendall(pickle.dumps(request))
        else:
            raise ConnectionTermiated

    def receive(self):
        data = b""
        incoming = self.socket.recv(1024)
        while incoming:
            data += incoming
            try:
                incoming = self.socket.recv(1024, socket.MSG_DONTWAIT)
            except BlockingIOError:
                break
        return pickle.loads(data)

    def send_with_response(self, request):
        try:
            self.send(request)
            response = self.receive()
        except (BrokenPipeError, ConnectionResetError, pickle.UnpicklingError):
            self.disconnect()
            raise ConnectionTermiated()
        except OSError:
            response = api.Response(request.type)
            response.status = -1
            response.data = None
        return response

    def get_time(self):
        request = api.Request(api.RequestType.EMULATION_GET_TIME)
        response = self.send_with_response(request)
        if response.status == -1:
            return 0, 0
        return response.data

    def get_status(self, data):
        request = api.Request(api.RequestType.OBJECT_STATUS)
        request.objects = data
        response = self.send_with_response(request)
        if response.status == -1:
            return None
        return response.data

class Buffer:
    def __init__(self):
        self._buffer = ""
        self.lock = threading.Lock()
    def append(self, data):
        with self.lock:
            self._buffer += data
    def consume(self):
        with self.lock:
            content = self._buffer
            self._buffer = ""
        return content

class LogReader(threading.Thread):
    def __init__(self, buffer, path):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(path)
        self.do_run = threading.Event()
        self.buffer = buffer
        super().__init__(None, None, f"monitor-log-thread-{self.socket.fileno()}")

    def run(self):
        while not self.do_run.is_set():
            try:
                data = self.socket.recv(8192)
            except ConnectionResetError:
                break
            if not data:
                break
            self.buffer.append(data.decode())

    def stop(self):
        self.do_run.set()
        self.socket.close()

class KlassCommandOption:
    def __init__(self, klass, name, type):
        self.klass = klass
        self.name = name
        self.type = type
        self.widget = None
    def get_label(self):
        label = Gtk.Label(label=self.name)
        label.set_xalign(0.)
        return label
    def get_widget(self):
        if self.type == bool:
            self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
            label = Gtk.Label(label=self.name)
            self.widget.append(label)
            self.radio_buttons = []
            r1 = Gtk.CheckButton(label="On")
            r1.value = 1
            self.widget.append(r1)
            self.radio_buttons.append(r1)
            r2 = Gtk.CheckButton(label="Off", group=r1)
            r2.value = 0
            self.widget.append(r2)
            self.radio_buttons.append(r2)
            if self.klass == ObjectKlass.DIGITAL_PIN:
                r3 = Gtk.CheckButton(label="Toggle", group=r1)
                r3.value = -1
                self.widget.append(r3)
                self.radio_buttons.append(r2)
        else:
            self.widget = Gtk.Entry()
        return self.widget
    def get_value(self):
        if self.type == bool:
            for r in self.radio_buttons:
                if r.get_active():
                    return r.value
            return False
        return self.type(self.widget.get_text())

def set_widget_margin(widget, top, bottom=None, left=None, right=None):
    widget.set_margin_top(top)
    widget.set_margin_bottom(bottom if bottom is not None else top)
    widget.set_margin_start(left if left is not None else top)
    widget.set_margin_end(right if right is not None else top)

class ListObject(GObject.Object):
    __gtype_name__ = "list_object"
    def __init__(self, id, name):
        super().__init__()
        self._id = id
        self._name = name
    @GObject.Property(type=int)
    def object_id(self):
        return self._id
    @GObject.Property(type=str)
    def name(self):
        return self._name

class KlassCommands(Gtk.Grid):
    def __init__(self, klass, objects, callback):
        super().__init__()
        self.set_column_homogeneous(False)
        self.set_column_spacing(10)
        self.set_row_spacing(3)
        self.set_hexpand(True)
        self.klass = klass
        self.callback = callback
        self._object_store = Gio.ListStore.new(item_type=ListObject)
        for o in objects:
            self._object_store.append(ListObject(*o))
        self.item_factory = Gtk.SignalListItemFactory()
        self.item_factory.connect("setup", self._object_item_setup)
        self.item_factory.connect("bind", self._object_item_bind)
        self.n_cmds = 0
    def _object_item_setup(self, factory, list_item):
        label = Gtk.Label()
        list_item.set_child(label)
    def _object_item_bind(self, factory, list_item):
        label = list_item.get_child()
        object = list_item.get_item()
        object.bind_property("name", label, "label", GObject.BindingFlags.SYNC_CREATE)
    def add_command(self, cmd_id, name, opts):
        button = Gtk.Button(label="Execute")
        self.attach(button, 0, self.n_cmds, 1, 1)
        label = Gtk.Label(label=name)
        label.set_xalign(0.)
        label.hexpand = True
        label.hexpand_set = True
        self.attach(label, 1, self.n_cmds, 1, 1)
        obj_box = Gtk.DropDown(model=self._object_store, factory=self.item_factory)
        obj_box.set_expression(Gtk.ClosureExpression.new(str, lambda x: x.get_property("name"), None))
        obj_box.set_enable_search(True)
        self.attach(obj_box, 2, self.n_cmds, 1, 1)
        cmd_opts = []
        for i, opt in enumerate(opts):
            ko = KlassCommandOption(self.klass, *opt)
            self.attach(ko.get_label(), 3 + i * 2, self.n_cmds, 1, 1)
            self.attach(ko.get_widget(), 3 + i * 2 + 1, self.n_cmds, 1, 1)
            cmd_opts.append(ko)
        button.connect("clicked", self.exec_cmd, cmd_id, obj_box, cmd_opts)
        self.n_cmds += 1
    def exec_cmd(self, button, cmd_id, combo, cmd_opts):
        item = combo.get_selected_item()
        object_id = item.get_property("object_id")
        opts = {}
        for opt in cmd_opts:
            opts[opt.name] = opt.get_value()
        # The toggle option is only available for digital pin objects
        if self.klass is ObjectKlass.DIGITAL_PIN:
            if opts["state"] == -1:
                opts[opt.name] = True
                self.callback(self.klass, object_id, cmd_id, opts)
                time.sleep(0.01)
                opts[opt.name] = False
                self.callback(self.klass, object_id, cmd_id, opts)
                return
            else:
                opts[opt.name] = bool(opts[opt.name])
        self.callback(self.klass, object_id, cmd_id, opts)
    def clear(self):
        self._object_store.clear()
        for child in self.get_children():
            self.remove(child)
            child.destroy()

class KlassObject:
    def __init__(self, name):
        label = Gtk.Label(label='')
        label.set_markup(f'<b>{name}</b>')
        label.hexpand = True
        label.hexpand_set = True
        label.set_xalign(0.)
        self.name = label
        self.properties = {}
        self.precision = -1
    def _get_value(self, value):
        if isinstance(value, float) and self.precision != -1 and \
            value and round(value, self.precision):
            value = round(value, self.precision)
        elif isinstance(value, list):
            rounded = []
            for v in value:
                # isinstance() is not sufficient because a lot of
                # non-[integer|float|string] value masquarade is
                # those types. type() is much more reliable.
                if type(v) in (int, float, str) and not v:
                    continue
                if isinstance(v, float) and self.precision != -1:
                    rounded.append(round(v, self.precision))
                else:
                    rounded.append(v)
            return rounded
        elif isinstance(value, dict):
            return ", ".join([f"{key}={value}" for key, value in value.items()])
        return value
    def add_property(self, prop):
        label = Gtk.Label(label=prop)
        label.set_xalign(0.)
        self.properties[prop] = (label, Gtk.Entry())
        self.properties[prop][1].set_width_chars(8)
        self.properties[prop][1].set_property("editable", False)
        self.properties[prop][1].set_property("can_focus", False)
    def set_value(self, prop, value):
        value = self._get_value(value)
        if isinstance(value, list):
            value = ", ".join([str(x) for x in value])
        self.properties[prop][1].set_text(str(value))
    def update(self, data):
        for property, value in data.items():
            self.set_value(property, value)
    def __len__(self):
        return len(self.properties)
    def __iter__(self):
        for prop, entry in self.properties.values():
            yield prop, entry

class DisplayObject(KlassObject):
    type = ObjectKlass.DISPLAY
    SCALE_FACTOR = 2
    def __init__(self, name):
        super().__init__(name)
        self.image = Gtk.Picture()
        self.image.set_halign(Gtk.Align.START)
        self.width = 0
        self.height = 0
        self.pixels = []
    def set_size(self, width, height):
        self.width = width
        self.height = height
        self.pixels = [0] * self.width * self.height * 4
        self.image.set_size_request(self.width * self.SCALE_FACTOR,
                                    self.height * self.SCALE_FACTOR)
    def update(self, data):
        super().update(data)
        if not self.width and not self.height:
            self.set_size(data["width"], data["height"])
        image_data = data["data"]
        for byte in range(8):
            for bit in range(8):
                for column in range(self.width):
                    pixel_color = 255 * bool((image_data[column][byte] & (1 << bit)))
                    self._put_pixel(column, byte * 8 + bit, pixel_color, pixel_color,
                                    pixel_color)
        self.update_image()
    def update_image(self):
        b = GLib.Bytes.new(self.pixels)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(b, GdkPixbuf.Colorspace.RGB, True, 8,
                                                  self.width, self.height,
                                                  self.width * 4)
        pixbuf = pixbuf.scale_simple(self.width * self.SCALE_FACTOR,
                                     self.height * self.SCALE_FACTOR,
                                     GdkPixbuf.InterpType.BILINEAR)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self.image.set_paintable(texture)
    def _put_pixel(self, x, y, r, g, b, a=255):
        offset = y * self.width * 4 + x * 4
        self.pixels[offset + 0] = r
        self.pixels[offset + 1] = g
        self.pixels[offset + 2] = b
        self.pixels[offset + 3] = a

class TooheadObject(KlassObject):
    type = ObjectKlass.TOOLHEAD
    def __init__(self, name):
        super().__init__(name)
    def add_property(self, prop):
        if prop != "position":
            super().add_property(prop)
    def update(self, data):
        valid_axes = []
        for property, value in data.items():
            if property == "position":
                continue
            if property == "axes":
                axes = []
                for axis in value:
                    if axis in AxisType:
                        axes.append(AxisType[axis])
                        valid_axes.append(AxisType[axis])
                self.set_value(property, axes)
        position = data["position"]
        for axis in valid_axes:
            if axis not in self.properties:
                label = Gtk.Label(label=str(axis))
                label.set_xalign(0.)
                self.properties[axis] = (label, Gtk.Entry())
                self.properties[axis][1].set_width_chars(8)
                self.properties[axis][1].set_property("editable", False)
                self.properties[axis][1].set_property("can_focus", False)
            self.set_value(axis, position[axis])

class NeopixelObject(DisplayObject):
    type = ObjectKlass.NEOPIXEL
    SCALE_FACTOR = 2
    LED_PIXEL_WIDTH = 10
    LED_PIXEL_HEIGHT = 10
    LED_SPACING = 10
    def __init__(self, name):
        super().__init__(name)
        self.count = 0
        self.R = self.G = self.B = 0
    def set_color_indexes(self, type):
        self.R = type.lower().index('r')
        self.B = type.lower().index('b')
        self.G = type.lower().index('g')
        self.W = type.lower().index('w')
    def set_led_count(self, count):
        self.count = count
        width = (count * 2 - 1) * self.LED_PIXEL_WIDTH
        height = self.LED_PIXEL_HEIGHT
        super().set_size(width, height)
    def _compute_white(self, colors):
        if not colors[3]:
            return colors
        white_factor = colors[3] / 256
        for i in range(3):
            colors[i] = min(colors[3] + int(colors[i] * white_factor), 255)
        return colors
    def update(self, data):
        super(DisplayObject, self).update(data)
        if not self.count:
            self.set_led_count(data["count"])
            self.set_color_indexes(data["type"])
        for x in range(self.width):
            index = x // self.LED_PIXEL_WIDTH
            if index % 2 == 0:
                colors = list(data["colors"][index // 2]) + [255]
            else:
                colors = [0] * len(data["type"]) + [0]
            colors = self._compute_white(colors)
            for y in range(self.LED_PIXEL_HEIGHT):
                self._put_pixel(x, y, colors[self.R], colors[self.G],
                                colors[self.B], colors[4])
        self.update_image()

KLASS_CLASS_MAP = {
    ObjectKlass.DISPLAY: DisplayObject,
    ObjectKlass.TOOLHEAD: TooheadObject,
    ObjectKlass.NEOPIXEL: NeopixelObject,
}

class KlassFrame(Gtk.Frame):
    def __init__(self, klass, label):
        super().__init__(label=label)
        self.set_label_align(0.)
        self.events = None
        self.commands = None
        self._objects = {}
        # Hack around the fact the we don't know what klass this
        # frame represents.
        self.klass = klass
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        scroll = Gtk.ScrolledWindow.new()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.box.append(scroll)
        self.table = Gtk.Grid.new()
        self.table.set_column_spacing(3)
        self.table.set_row_spacing(3)
        set_widget_margin(self.table, 0, 0, 20)
        scroll.set_child(self.table)
        self.set_child(self.box)

    def add_object(self, obj_id, name, obj):
        top_attach = len(self._objects)
        obj.name.set_margin_end(10)
        obj.name.set_hexpand(True)
        if self.klass in (ObjectKlass.DISPLAY, ObjectKlass.NEOPIXEL):
            self.table.attach(obj.name, 0, top_attach, 1, 2)
        else:
            self.table.attach(obj.name, 0, top_attach, 1, 1)
        for j, (prop, entry) in enumerate(obj):
            prop.set_margin_start(10)
            prop.set_margin_end(3)
            self.table.attach(prop, j * 2 + 1, top_attach, 1, 1)
            entry.set_margin_end(3)
            self.table.attach(entry, j * 2 + 2, top_attach, 1, 1)
        if self.klass in (ObjectKlass.DISPLAY, ObjectKlass.NEOPIXEL):
            obj.image.set_margin_start(10)
            self.table.attach(obj.image, 1, top_attach + 1, len(obj) * 2, 1)
        self._objects[obj_id] = obj

    def add_commands(self, cmds):
        if not self.commands:
            self.commands = Gtk.Expander(label="Commands")
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            self.commands.set_child(scroll)
            self.box.append(self.commands)
        self.commands.get_child().set_child(cmds)

    def add_events(self, events):
        if not self.events:
            self.events = Gtk.Expander(label="Events")
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            scroll.set_child(events)
            self.box.append(self.events)
        self.events.get_child().set_child(events)

    def get_object(self, obj_id):
        return self._objects.get(obj_id, None)

    def clear(self):
        for i in range(len(self._objects)):
            self.table.remove_row(0)
        # Display objects have an image, so we need to remove it
        if self.klass in (ObjectKlass.DISPLAY, ObjectKlass.NEOPIXEL):
            self.table.remove_row(0)
        if self.commands:
            self.box.remove(self.commands)
            self.commands = None
        self._objects.clear()

    def __iter__(self):
        for obj_id, obj in self._objects.items():
            yield obj

class DebugLevelObject(GObject.Object):
    __gtype_name__ = "debug_level_object"
    def __init__(self, level, name):
        super().__init__()
        self._level = level
        self._name = name
    @GObject.Property(type=int)
    def level(self):
        return self._level
    @GObject.Property(type=str)
    def name(self):
        return self._name

class MonitorWindow(Gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_default_size(1024, 800)
        self.klass_frames = {}
        self.log_thread = None
        self.log_thread_id = 0
        self.debug_buffer = Buffer()

        # The toast overlay will be used to display notifications
        self.toasts = Adw.ToastOverlay()
        self.set_child(self.toasts)

        # Create the main horizontal box. This will contain
        # the emulation data box and the button box
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        set_widget_margin(main_box, 5)
        self.toasts.set_child(main_box)

        # Create the box for all of the high level emulation
        # data.
        self.monitor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.append(self.monitor_box)

        self.banner = Adw.Banner.new("Emulation paused")
        self.banner.set_button_label("Resume")
        self.banner.set_action_name("app.emulation-resume")
        self.monitor_box.append(self.banner)


        # Runtime/tick frame
        frame = Gtk.Frame.new()
        frame.set_label_align(0.01)
        self.monitor_box.append(frame)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        set_widget_margin(box, 5)
        frame.set_child(box)
        for l in (("runtime", "Runtime"), ("ticks", "Controller clock")):
            label = Gtk.Label(label=l[1])
            entry = Gtk.Entry()
            entry.set_property("editable", False)
            entry.set_property("can_focus", False)
            box.append(label)
            box.append(entry)
            setattr(self, f"{l[0]}_entry", entry)

        # Now, the main object box - selectors and klass frames
        object_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.monitor_box.append(object_box)

        selector_frame = Gtk.Frame()
        object_box.append(selector_frame)
        selector_frame.set_label_align(0.01)

        selector_button_grid = Gtk.Grid()
        selector_button_grid.set_column_spacing(10)
        set_widget_margin(selector_button_grid, 5)
        selector_frame.set_child(selector_button_grid)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        object_frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        scroll.set_child(object_frame_box)

        for i, klass in enumerate(ObjectKlass):
            if klass is ObjectKlass.NONE:
                continue
            label = str(klass).replace('_', " ") + " Objects"
            self.klass_frames[klass] = KlassFrame(klass, label=label.title())
            self.klass_frames[klass].set_visible(False)
            object_frame_box.append(self.klass_frames[klass])
            
            name = str(klass).replace("_", " ").capitalize()
            label = Gtk.Label(label=name)
            label.set_xalign(0.0)
            selector_button_grid.attach(label, 0, i, 1, 1)
            switch = Gtk.Switch()
            switch.set_active(False)
            switch.connect("notify::active", self.object_frame_toggle, klass)
            selector_button_grid.attach(switch, 1, i, 1, 1)
            setattr(self, f"{klass}_selector_switch", switch)
        object_box.append(scroll)

        # Below is the code to setup the log window:
        # frame:
        #   vbox:
        #     hbox:
        #       label
        #       dropdown
        #       button
        #       label
        #       scrollback spinbutton
        #     scrolledwindow
        #       VTE terminal
        log_frame = Gtk.Frame.new()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        level_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.append(level_box)
        label = Gtk.Label.new("Debug Level")
        level_box.append(label)
        set_widget_margin(box, 5)
        log_frame.set_child(box)
        self.debug_level_store = Gio.ListStore.new(item_type=DebugLevelObject)
        def _object_item_setup(factory, list_item):
            list_item.set_child(Gtk.Label())
        def _object_item_bind(factory, list_item):
            label = list_item.get_child()
            object = list_item.get_item()
            object.bind_property("name", label, "label", GObject.BindingFlags.SYNC_CREATE)
        for level, name in LOG_LEVELS.items():
            self.debug_level_store.append(DebugLevelObject(level, name))
        item_factory = Gtk.SignalListItemFactory()
        item_factory.connect("setup", _object_item_setup)
        item_factory.connect("bind", _object_item_bind)
        drop_down = Gtk.DropDown(model=self.debug_level_store, factory=item_factory)
        drop_down.set_expression(Gtk.ClosureExpression.new(str, lambda x: x.get_property("name"), None))
        drop_down.set_enable_search(True)
        level_box.append(drop_down)
        start_log_button = Gtk.ToggleButton(label="Start")
        start_log_button.connect("toggled", self.start_stop_log, drop_down)
        level_box.append(start_log_button)
        label = Gtk.Label.new("Scrollback lines")
        level_box.append(label)
        scrollback_spin = Gtk.SpinButton.new_with_range(-1, 10000, 1)
        level_box.append(scrollback_spin)
        scrollback_spin.connect("value-changed", self.change_vte_scrollback)
        scroll = Gtk.ScrolledWindow()
        box.append(scroll)
        self.vte = Vte.Terminal.new()
        self.vte.set_vexpand(True)
        scrollback_spin.set_value(self.vte.get_scrollback_lines())
        scroll.set_child(self.vte)

        button_boxes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.append(button_boxes)

        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        control_box.set_vexpand(True)
        button_boxes.append(control_box)

        #control_box.set_layout(Gtk.ButtonBoxStyle.START)
        self.precision_spin = Gtk.SpinButton.new_with_range(0, 15, 1)
        self.precision_spin.set_value(4)
        self.precision_spin.set_tooltip_text("Set the precision of displayed data")
        self.precision_spin.connect("value-changed", self.set_object_value_precision)
        control_box.append(self.precision_spin)

        pause_button = Gtk.Button(label="Pause")
        pause_button.set_action_name("app.emulation-pause")
        pause_button.set_tooltip_text("Pause the emulation.")
        control_box.append(pause_button)

        capture_button = Gtk.Button(label="Capture State")
        capture_button.set_action_name("app.emulation-capture")
        capture_button.set_tooltip_text("Capture emulation state. "
                                        "The emulation will be paused during capture.")
        control_box.append(capture_button)

        self.log_button = Gtk.ToggleButton(label="Show Log")
        self.log_button.connect("toggled", self.open_log, start_log_button, log_frame)
        self.log_button.set_tooltip_text("Open emulation log output window.")
        control_box.append(self.log_button)

        reset_button = Gtk.Button(label="Reset", name="reset-button")
        reset_button.set_action_name("app.emulation-reset")
        reset_button.set_tooltip_text("Reset the emulation.")
        control_box.append(reset_button)

        quit_button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        button_boxes.append(quit_button_box)
        quit_button = Gtk.Button.new_with_label("Quit")
        quit_button.set_action_name("app.quit")
        quit_button_box.append(quit_button)
        
    def object_frame_toggle(self, switch, gparam, klass):
        if switch.get_active():
            self.klass_frames[klass].set_visible(True)
        else:
            self.klass_frames[klass].set_visible(False)

    def open_log(self, button, start_stop_button, log_frame):
        if button.get_active():
            self.monitor_box.append(log_frame)
            button.set_label("Hide Log")
        else:
            start_stop_button.set_active(False)
            self.monitor_box.remove(log_frame)
            button.set_label("Show Log")

    def start_stop_log(self, button, drop_down):
        if button.get_active():
            item = drop_down.get_selected_item()
            level = item.get_property("level")
            request = api.Request(api.RequestType.OPEN_LOG_STREAM)
            request.data = level
            try:
                response = self.get_application().connection.send_with_response(request)
            except ConnectionTermiated:
                button.set_active(False)
                return
            self.notify(repr(response))
            if response.status == 0:
                self.log_thread_id = response.data["id"]
                self.log_thread = LogReader(self.debug_buffer, response.data["path"])
                self.log_thread.start()
                button.set_label("Stop")
            else:
                button.set_active(False)
        else:
            if self.log_thread_id:
                request = api.Request(api.RequestType.CLOSE_LOG_STREAM)
                request.data = self.log_thread_id
                try:
                    response = self.get_application().connection.send_with_response(request)
                    self.notify(repr(response))
                except ConnectionTermiated:
                    return
                if self.log_thread:
                    self.log_thread.stop()
                    button.set_label("Start")

    def insert_and_scroll(self, content):
        content = content.replace("\n", "\n\r")
        self.vte.feed(content.encode("utf-8"))

    def change_vte_scrollback(self, spinbutton):
        count = spinbutton.get_value_as_int()
        self.vte.set_scrollback_lines(count)

    def set_emulation_time(self, runtime, ticks):
        self.runtime_entry.set_text(str(runtime))
        self.ticks_entry.set_text(str(ticks))

    def populate_objects(self, objects, data):
        for klass in objects.objects:
            obj_set = []
            set_widget_margin(self.klass_frames[klass].get_child(), 5)
            if objects.objects[klass]:
                switch = getattr(self, f"{klass}_selector_switch")
                switch.set_active(True)
            for i, obj in enumerate(objects.objects[klass]):
                obj_set.append((obj["id"], obj["name"]))
                kclass = KLASS_CLASS_MAP.get(klass, KlassObject)
                kobj = kclass(obj["name"])
                kobj.precision = self.precision_spin.get_value_as_int()
                props = list(data[obj["id"]].keys())
                for prop in props:
                    kobj.add_property(prop)
                kobj.update(data[obj["id"]])
                self.klass_frames[klass].add_object(obj["id"], obj["name"], kobj)
            app = self.get_application()
            if objects.commands[klass]:
                kcmds = KlassCommands(klass, obj_set, app.exec_cmd)
                for i, cmd in enumerate(objects.commands[klass]):
                    kcmds.add_command(cmd[0], cmd[1], cmd[2])
                self.klass_frames[klass].add_commands(kcmds)

    def update_objects(self, objects, status):
        for klass, objts in objects.objects.items():
            for obj in objts:
                obj_id = obj["id"]
                kobj = self.klass_frames[klass].get_object(obj_id)
                kobj.update(status[obj_id])
        if self.log_thread and self.log_thread.is_alive():
            content = self.debug_buffer.consume()
            self.insert_and_scroll(content)

    def set_object_value_precision(self, spinbutton):
        precision = spinbutton.get_value_as_int()
        for frame in self.klass_frames.values():
            for obj in frame:
                obj.precision = precision

    def set_paused_state(self, paused):
        self.banner.set_revealed(paused)

    def notify(self, msg, action=None):
        msg = msg.replace("<", "&lt;").replace(">", "&gt;")
        toast = Adw.Toast.new(msg)
        toast.set_timeout(3)
        self.toasts.add_toast(toast)

    def clear(self):
        for klass, frame in self.klass_frames.items():
            frame.clear()
            switch = getattr(self, f"{klass}_selector_switch")
            switch.set_active(False)
        request = api.Request(api.RequestType.CLOSE_LOG_STREAM)
        request.data = self.log_thread_id
        try:
            self.get_application().connection.send_with_response(request)
        except ConnectionTermiated:
            pass
        if self.log_thread:
            self.log_thread.stop()
            self.log_thread.join()
        self.log_button.set_active(False)
        self.banner.set_revealed(False)

class MonitorApplication(Adw.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id="com.github.voidtrance.VortexMonitor",
                         **kwargs)
        self.main_window = None
        self.have_data = False
        self.object_data = None
        self.connection = Communicator()
        self.css = Gtk.CssProvider.new()
        self.css.load_from_string(style)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.css,
                                                   Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_startup(self, *args):
        Gtk.Application.do_startup(self)

        pause_action = Gio.SimpleAction.new("emulation-pause", None)
        pause_action.connect("activate", self.pause_emulation)
        self.add_action(pause_action)

        resume_action = Gio.SimpleAction.new("emulation-resume", None)
        resume_action.connect("activate", self.resume_emulation)
        self.add_action(resume_action)

        reset_action = Gio.SimpleAction.new("emulation-reset", None)
        reset_action.connect("activate", self.reset_emulation)
        self.add_action(reset_action)

        capture_action = Gio.SimpleAction.new("emulation-capture", None)
        capture_action.connect("activate", self.show_capture_status_dalog)
        self.add_action(capture_action)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.on_quit)
        self.add_action(quit_action)

    def do_activate(self):
        if not self.main_window:
            self.main_window = MonitorWindow(application=self, title="Vortex Monitor")

        self.main_window.present()
        self.connection.connect()
        self.timeout = GLib.timeout_add(100, self.update)

    def get_object_data(self):
        self.object_data = Namespace()
        request = api.Request(api.RequestType.KLASS_LIST)
        response = self.connection.send_with_response(request)
        if response.status != 0:
            return False
        self.object_data.klasses = response.data
        request = api.Request(api.RequestType.OBJECT_LIST)
        response = self.connection.send_with_response(request)
        if response.status != 0:
            return False
        self.object_data.objects = response.data
        self.object_data.commands = {}
        self.object_data.events = {}
        for klass in self.object_data.klasses:
            request = api.Request(api.RequestType.OBJECT_COMMANDS)
            request.klass = klass
            response = self.connection.send_with_response(request)
            if response.status != 0:
                return False
            self.object_data.commands = response.data
            request.type = api.RequestType.OBJECT_EVENTS
            response = self.connection.send_with_response(request)
            if response.status != 0:
                return False
            self.object_data.events = response.data
        self.query_ids = [o["id"] for k in self.object_data.klasses \
                     for o in self.object_data.objects.get(k, [])]
        return True

    def update(self):
        if not self.connection.connected:
            if not self.connection.connect():
                return True

        need_populate = not self.object_data
        if not self.object_data:
            if not self.get_object_data():
                return True

        try:
            runtime, ticks = self.connection.get_time()
            self.main_window.set_emulation_time(runtime, ticks)
            status = self.connection.get_status(self.query_ids)
        except ConnectionTermiated:
            self.main_window.clear()
            self.query_ids = None
            self.object_data = None
            return True
        except Exception as e:
            self.notify(f"STATUS UPDATE ERROR: {e}, {type(e)}")
            status = None

        if status is None:
            return True

        if need_populate:
            self.main_window.populate_objects(self.object_data, status)

        self.main_window.update_objects(self.object_data, status)
        return True

    def pause_emulation(self, action, param):
        request = api.Request(api.RequestType.EMULATION_PAUSE)
        response = self.connection.send_with_response(request)
        self.main_window.set_paused_state(True)
        return response.data

    def resume_emulation(self, action, param):
        self.main_window.set_paused_state(False)
        request = api.Request(api.RequestType.EMULATION_RESUME)
        response = self.connection.send_with_response(request)
        return response.data

    def reset_emulation(self, action, param):
        request = api.Request(api.RequestType.EMULATION_RESET)
        response = self.connection.send_with_response(request)
        self.main_window.notify("Emulation reset")
        self.main_window.notify(repr(response))
        return response.data

    def save_state(self, dialog, task, user_data):
        import json
        file = dialog.save_finish(task)
        stream = file.replace(None, False, Gio.FileCreateFlags.REPLACE_DESTINATION, None)
        try:
            self.pause_emulation(None, None)
            status = self.connection.get_status(self.query_ids)
            self.resume_emulation(None, None)
        except Exception as e:
            print(e)
            return
        stream.write_bytes(GObject.Bytes(bytes(json.dumps(status), "ascii")))

    def show_capture_status_dalog(self, action, param):
        dialog = Gtk.FileDialog()
        dialog.set_modal(True)
        dialog.set_initial_name("vortext_state.json")
        dialog.save(parent=self.main_window, cancellable=None, callback=self.save_state,
                     user_data=self)

    def exec_cmd(self, klass, obj, cmd, opts):
        self.main_window.notify(f"Executiong cmd: {cmd} ({opts}) for obj {klass}:{obj}")
        request = api.Request(api.RequestType.EXECUTE_COMMAND)
        request.klass = klass
        request.object = obj
        request.command = cmd
        request.opts = opts
        response = self.connection.send_with_response(request)
        self.main_window.notify(repr(response))
        return response.data

    def on_quit(self, action, param):
        GLib.source_remove(self.timeout)
        self.main_window.clear()
        self.quit()


def main():
    app = MonitorApplication()
    try:
        ret = app.run()
    except KeyboardInterrupt:
        ret = app.quit()
    return ret

sys.exit(main())
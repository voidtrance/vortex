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
import sys
import socket
import pickle
import time
import gi
from vortex.core import ObjectTypes
import vortex.emulator.remote.api as api
gi.require_version("Gtk", "3.0")
gi.require_version('GLib', '2.0')
from gi.repository import Gtk, GLib, GObject, GdkPixbuf, Gdk
from argparse import Namespace

socket_path = "/tmp/vortex-remote"

class KlassObject:
    def __init__(self, name):
        label = Gtk.Label(label='')
        label.set_markup(f'<b>{name}</b>')
        label.hexpand = True
        label.hexpand_set = True
        label.set_xalign(0.)
        self.name = label
        self.properties = {}
    def add_property(self, prop):
        label = Gtk.Label(label=prop)
        label.set_xalign(0.)
        self.properties[prop] = (label, Gtk.Entry())
        self.properties[prop][1].set_property("editable", False)
        self.properties[prop][1].set_property("can_focus", False)
    def set_value(self, prop, value):
        self.properties[prop][1].set_text(str(value))
    def __len__(self):
        return len(self.properties)
    def __iter__(self):
        for prop, entry in self.properties.values():
            yield prop, entry

class DisplayKlassObject(KlassObject):
    def __init__(self, name):
        super().__init__(name)
        self.image = Gtk.Image()
        self.image.set_halign(Gtk.Align.START)
        self.width = 0
        self.height = 0
    def set_size(self, width, height):
        self.width = width
        self.height = height
    def update(self, data):
        pixels = [0] * self.width * self.height * 3
        for byte in range(8):
            for bit in range(8):
                for column in range(self.width):
                    if data[column][byte] & (1 << bit):
                        self._put_pixel(pixels, column, byte * 8 + bit, 255, 255, 255)
                    else:
                        self._put_pixel(pixels, column, byte * 8 + bit, 0, 0, 0)
        b = GLib.Bytes.new(pixels)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(b, GdkPixbuf.Colorspace.RGB, False, 8,
                                                  self.width, self.height,
                                                  self.width * 3)
        pixbuf = pixbuf.scale_simple(int(self.width * 1.75), int(self.height * 1.75),
                            GdkPixbuf.InterpType.BILINEAR)
        self.image.set_from_pixbuf(pixbuf)
    def _put_pixel(self, pixels, x, y, r, g, b):
        offset = y * self.width + x
        pixels[offset * 3 + 0] = r
        pixels[offset * 3 + 1] = g
        pixels[offset * 3 + 2] = b

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
            self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            label = Gtk.Label(label=self.name)
            self.widget.pack_start(label, False, False, 3)
            self.r1 = Gtk.RadioButton.new()
            l = Gtk.Label(label="On")
            self.r1.add(l)
            self.r1.value = 1
            self.widget.pack_start(self.r1, False, False, 3)
            r2 = Gtk.RadioButton.new_with_label_from_widget(self.r1, "Off")
            r2.value = 0
            self.widget.pack_start(r2, False, False, 3)
            if self.klass == ObjectTypes.DIGITAL_PIN:
                r3 = Gtk.RadioButton.new_with_label_from_widget(self.r1, "Toggle")
                r3.value = -1
                self.widget.pack_start(r3, False, False, 3)
        else:
            self.widget = Gtk.Entry()
        return self.widget
    def get_value(self):
        if self.type == bool:
            for r in self.r1.get_group():
                if r.get_active():
                    return r.value
            return False
        return self.type(self.widget.get_text())

class KlassCommands(Gtk.Grid):
    def __init__(self, klass, objects, callback):
        super().__init__()
        self.set_column_homogeneous(False)
        self.set_column_spacing(10)
        self.set_row_spacing(3)
        self.klass = klass
        self.callback = callback
        self._object_store = Gtk.ListStore(GObject.TYPE_UINT64, str)
        for o in objects:
            self._object_store.append(o)
        self._object_store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        self.n_cmds = 0
    def add_command(self, cmd_id, name, opts):
        button = Gtk.Button(label="Execute")
        self.attach(button, 0, self.n_cmds, 1, 1)
        label = Gtk.Label(label=name)
        label.set_xalign(0.)
        label.hexpand = True
        label.hexpand_set = True
        self.attach(label, 1, self.n_cmds, 1, 1)
        obj_box = Gtk.ComboBox.new_with_model_and_entry(self._object_store)
        obj_box.set_entry_text_column(1)
        obj_box.set_id_column(0)
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
        iter = combo.get_active_iter()
        model = combo.get_model()
        opts = {}
        for opt in cmd_opts:
            opts[opt.name] = opt.get_value()
        # The toggle option is only available for digital pin objects
        if self.klass is ObjectTypes.DIGITAL_PIN:
            if opts["state"] == -1:
                opts[opt.name] = True
                self.callback(self.klass, model[iter][0], cmd_id, opts)
                time.sleep(0.01)
                opts[opt.name] = False
                self.callback(self.klass, model[iter][0], cmd_id, opts)
                return
            else:
                opts[opt.name] = bool(opts[opt.name])
        self.callback(self.klass, model[iter][0], cmd_id, opts)
    def clear(self):
        self._object_store.clear()
        for child in self.get_children():
            self.remove(child)
            child.destroy()

class KlassFrame(Gtk.Frame):
    def __init__(self, label):
        super().__init__(label=label)
        self.set_label_align(0.01, 0.6)
        self.events = None
        self.commands = None
        self._objects = {}
        # Hack around the fact the we don't know what klass this
        # frame represents.
        self.is_display = label == "Display"
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll = Gtk.ScrolledWindow.new()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.box.pack_start(scroll, False, False, 3)
        self.table = Gtk.Grid.new()
        self.table.set_column_spacing(3)
        self.table.set_row_spacing(3)
        scroll.add(self.table)
        self.add(self.box)
    def add_object(self, obj_id, name, obj):
        top_attach = len(self._objects)
        obj.name.set_margin_end(10)
        obj.name.set_hexpand(True)
        if self.is_display:
            self.table.attach(obj.name, 0, top_attach, 1, 2)
        else:
            self.table.attach(obj.name, 0, top_attach, 1, 1)
        for j, (prop, entry) in enumerate(obj):
            prop.set_margin_start(10)
            prop.set_margin_end(3)
            self.table.attach(prop, j * 2 + 1, top_attach, 1, 1)
            entry.set_margin_end(3)
            self.table.attach(entry, j * 2 + 2, top_attach, 1, 1)
        if self.is_display:
            obj.image.set_margin_start(10)
            self.table.attach(obj.image, 1, top_attach + 1, len(obj) * 2, 1)
        self._objects[obj_id] = obj
    def add_commands(self, cmds):
        if not self.commands:
            self.commands = Gtk.Expander(label="Commands")
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            self.commands.add(scroll)
            self.box.pack_end(self.commands, False, False, 3)
        self.commands.get_child().add(cmds)
    def add_events(self, events):
        if not self.events:
            self.events = Gtk.Expander(label="Events")
            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            scroll.add(events)
            self.box.pack_end(self.events, False, False, 3)
        self.events.get_child().add(events)
    def get_object(self, obj_id):
        return self._objects.get(obj_id, None)
    def clear(self):
        for i in range(len(self._objects)):
            self.table.remove_row(0)
        # Display objects have an image, so we need to remove it
        if self.is_display:
            self.table.remove_row(0)
        if self.commands:
            self.commands.destroy()
            self.commands = None
        self._objects.clear()
    def __iter__(self):
        for obj_id, obj in self._objects.items():
            yield obj

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Vortex Monitor")
        self.set_default_size(1024, 800)
        self.connect("destroy", Gtk.main_quit)
        self.connection = None
        self.emulation_data = Namespace()
        self._have_data = False
        self.klass_frames = {}
        self.run_update = True

        # The main window box containing the entire UI.
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        main_box.set_spacing(10)
        self.set_widget_margin(main_box, 5)

        # The monitor box all of the emulation data - the emulator
        # runtime/ticks frame and a horizontal box for the object
        # selectors and state scrolled window.
        monitor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        monitor_box.set_spacing(10)

        frame = Gtk.Frame.new("Emulation")
        frame.set_label_align(0.01, 0.6)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        for l in (("runtime", "Runtime"), ("ticks", "Controller clock")):
            label = Gtk.Label(label=l[1])
            entry = Gtk.Entry()
            entry.set_property("editable", False)
            entry.set_property("can_focus", False)
            box.pack_start(label, False, False, 3)
            box.pack_start(entry, False, False, 3)
            setattr(self, f"{l[0]}_entry", entry)
        frame.add(box)
        self.set_widget_margin(box, 3)
        monitor_box.pack_start(frame, False, False, 0)

        # This is the box holding all of the object widgets (klass
        # selectors and the object state scrolled window).
        objects_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        objects_box.set_spacing(10)
        object_frame = Gtk.Frame.new(label="Object Types")
        object_frame.set_label_align(0.01, 0.6)
        object_checkbutton_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        object_frame.add(object_checkbutton_box)
        objects_box.pack_start(object_frame, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        object_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        object_box.set_spacing(5)
        scroll.add(object_box)
        for klass in ObjectTypes:
            if klass is ObjectTypes.NONE:
                continue
            label = str(klass).replace('_', " ")
            self.klass_frames[klass] = KlassFrame(label=label.title())
            object_box.pack_start(self.klass_frames[klass], False, False, 0)
        objects_box.pack_start(scroll, True, True, 0)

        for i, klass in enumerate(ObjectTypes):
            if klass is ObjectTypes.NONE:
                continue
            label = str(klass).replace("_", " ")
            checkbox = Gtk.CheckButton.new_with_label(label.title())
            checkbox.set_active(True)
            checkbox.connect("toggled", self.object_frame_toggle, object_box, i - 1, klass)
            object_checkbutton_box.pack_start(checkbox, False, False, 3)

        monitor_box.pack_start(objects_box, True, True, 3)
        main_box.pack_start(monitor_box, True, True, 3)

        # Box that holds the two ButtonBox's. We want a box because there
        # are two button boxes, one for the control buttons and one
        # for the exit button, which are packed differently.
        button_boxes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        control_box = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        control_box.set_layout(Gtk.ButtonBoxStyle.START)
        control_box.set_spacing(5)

        self.precision_spin = Gtk.SpinButton.new_with_range(-1, 15, 1)
        self.precision_spin.set_value(8)
        control_box.pack_start(self.precision_spin, False, True, 3)

        pause_button = Gtk.Button(label="Pause")
        pause_button.connect("clicked", self.pause_emulation)
        control_box.pack_start(pause_button, False, True, 3)

        resume_button = Gtk.Button(label="Resume")
        resume_button.connect("clicked", self.resume_emulation)
        control_box.pack_start(resume_button, False, True, 3)

        reset_button = Gtk.Button(label="Reset", name="reset-button")
        reset_button.connect("clicked", self.reset_emulation)
        control_box.pack_start(reset_button, False, True, 3)

        button_boxes.pack_start(control_box, True, True, 3)

        button_box = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        button_box.set_layout(Gtk.ButtonBoxStyle.EXPAND)
        exit_button = Gtk.Button(label="Exit")
        exit_button.connect("clicked", self.destroy)
        button_box.pack_end(exit_button, True, True, 0)
        button_boxes.pack_end(button_box, False, True, 3)

        main_box.pack_end(button_boxes, False, True, 3)
        self.add(main_box)
        self.show_all()
        self.timer = GLib.timeout_add(100, self.update)

    def object_frame_toggle(self, button, box, index, klass):
        if button.get_active():
            box.pack_start(self.klass_frames[klass], False, False, 0)
            box.reorder_child(self.klass_frames[klass], index)
        else:
            box.remove(self.klass_frames[klass])

    def connect_to_server(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(socket_path)
        except (FileNotFoundError, ConnectionRefusedError):
            return
        self.connection = sock

    def send_request(self, request):
        self.connection.sendall(pickle.dumps(request))

    def get_response(self):
        data = b""
        incoming = self.connection.recv(1024)
        while incoming:
            data += incoming
            try:
                incoming = self.connection.recv(1024, socket.MSG_DONTWAIT)
            except BlockingIOError:
                break
        return pickle.loads(data)

    def get_data_value(self, value):
        precision = self.precision_spin.get_value_as_int()
        if isinstance(value, float) and precision != -1 and \
            value and round(value, precision):
            value = round(value, precision)
        elif isinstance(value, list):
            rounded = []
            for v in value:
                if isinstance(v, float) and precision != -1:
                    rounded.append(round(v, precision))
                else:
                    rounded.append(v)
            value = ", ".join([str(x) for x in rounded if not isinstance(x,str) or x])
        return str(value)
    
    def populate_grids(self, data):
        for klass in self.emulation_data.objects:
            obj_set = []
            self.set_widget_margin(self.klass_frames[klass].get_child(), 5)
            for i, obj in enumerate(self.emulation_data.objects[klass]):
                obj_set.append((obj["id"], obj["name"]))
                if klass is ObjectTypes.DISPLAY:
                    kobj = DisplayKlassObject(obj["name"])
                else:
                    kobj = KlassObject(obj["name"])
                props = list(data[obj["id"]].keys())
                for j, prop in enumerate(props):
                    if klass is ObjectTypes.DISPLAY and prop == "data":
                        kobj.set_size(data[obj["id"]]["width"],
                                      data[obj["id"]]["height"])
                        kobj.update(data[obj["id"]][prop])
                    else:
                        kobj.add_property(prop)
                        kobj.set_value(prop, data[obj["id"]][prop])
                self.klass_frames[klass].add_object(obj["id"], obj["name"], kobj)
            if self.emulation_data.commands[klass]:
                kcmds = KlassCommands(klass, obj_set, self.exec_cmd)
                for i, cmd in enumerate(self.emulation_data.commands[klass]):
                    kcmds.add_command(cmd[0], cmd[1], cmd[2])
                self.klass_frames[klass].add_commands(kcmds)
        self.show_all()

    def set_widget_margin(self, widget, top, bottom=None, left=None, right=None):
        widget.set_margin_top(top)
        widget.set_margin_bottom(bottom if bottom is not None else top)
        widget.set_margin_start(left if left is not None else top)
        widget.set_margin_end(right if right is not None else top)

    def pause_emulation(self, button):
        request = api.Request(api.RequestType.EMULATION_PAUSE)
        self.send_request(request)
        return self.get_response().data
    
    def resume_emulation(self, button):
        request = api.Request(api.RequestType.EMULATION_RESUME)
        self.send_request(request)
        return self.get_response().data
    
    def reset_emulation(self, button):
        request = api.Request(api.RequestType.EMULATION_RESET)
        self.send_request(request)
        return self.get_response().data

    def exec_cmd(self, klass, obj, cmd, opts):
        print(klass, obj, cmd, opts)
        request = api.Request(api.RequestType.EXECUTE_COMMAND)
        request.klass = klass
        request.object = obj
        request.command = cmd
        request.opts = opts
        self.send_request(request)
        response = self.get_response()
        print(response)
        return
    
    def get_time(self):
        try:
            request = api.Request(api.RequestType.EMULATION_GET_TIME)
            self.send_request(request)
            return self.get_response().data
        except (BrokenPipeError, EOFError):
            return 0, 0

    def get_status(self, klass=None):
        obj_ids = []
        klass_set = [klass] if klass is not None else [x for x in ObjectTypes]
        for klass in klass_set:
            if klass not in self.emulation_data.objects:
                continue                
            for obj in self.emulation_data.objects[klass]:
                obj_ids.append(obj["id"])
        try:
            request = api.Request(api.RequestType.OBJECT_STATUS)
            request.objects = obj_ids
            self.send_request(request)
            return self.get_response().data
        except (BrokenPipeError, EOFError):
            self.connection = None
            try:
                for klass in self.emulation_data.objects:
                    if klass in self.klass_frames:
                        self.klass_frames[klass].clear()
                delattr(self, "emulation_data")
                self.emulation_data = Namespace()
            except Exception as e:
                print(e)
            self._have_data = False
            return None

    def populate_data(self):
        request = api.Request(api.RequestType.KLASS_LIST)
        self.send_request(request)
        response = self.get_response()
        if response.status != 0:
            return
        self.emulation_data.klasses = response.data
        request = api.Request(api.RequestType.OBJECT_LIST)
        self.send_request(request)
        response = self.get_response()
        if response.status != 0:
            return
        self.emulation_data.objects = response.data
        self.emulation_data.commands = {}
        self.emulation_data.events = {}
        for klass in self.emulation_data.klasses:
            request = api.Request(api.RequestType.OBJECT_COMMANDS)
            request.klass = klass
            self.send_request(request)
            response = self.get_response()
            if response.status != 0:
                return
            self.emulation_data.commands = response.data
            request.type = api.RequestType.OBJECT_EVENTS
            self.send_request(request)
            response = self.get_response()
            if response.status != 0:
                return
            self.emulation_data.events = response.data
        self._have_data = True

    def update(self):
        if self.connection is None:
            self.connect_to_server()
            if self.connection is None:
                return self.run_update
        need_populate = not self._have_data
        if not self._have_data:
            self.populate_data()
        try:
            runtime, ticks = self.get_time()
            self.runtime_entry.set_text(str(runtime))
            self.ticks_entry.set_text(str(ticks))
            status = self.get_status()
        except:
            status = None
        if status is None:
            return self.run_update
        if need_populate:
            self.populate_grids(status)
        for klass, objects in self.emulation_data.objects.items():
            for obj in objects:
                obj_id = obj["id"]
                kobj = self.klass_frames[klass].get_object(obj_id)
                for prop in status[obj_id]:
                    if klass is ObjectTypes.DISPLAY and prop == "data":
                        kobj.update(status[obj_id][prop])
                    else:
                        value = self.get_data_value(status[obj_id][prop])
                        kobj.set_value(prop, value)
        return self.run_update
    
    def destroy(self, button):
        self.run_update = False
        super().destroy()

style = b"""
button#reset-button { background-image: none; background-color: red; color: white;}
"""

def main():
    css = Gtk.CssProvider.new()
    css.load_from_data(style)
    screen = Gdk.Screen.get_default()
    styleContext = Gtk.StyleContext()
    styleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    app = MainWindow()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    return 0

sys.exit(main())
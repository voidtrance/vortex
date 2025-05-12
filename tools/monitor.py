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
from gi.repository import Gtk, GLib, GObject, GdkPixbuf
from argparse import Namespace

socket_path = "/tmp/vortex-remote"

class KlassObject(Gtk.Box):
    def __init__(self, name):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label(label='')
        label.set_markup(f'<b>{name}</b>')
        label.hexpand = True
        label.hexpand_set = True
        label.set_xalign(0.)
        self.pack_start(label, False, False, 3)
        self.properties = {}
    def add_property(self, prop):
        label = Gtk.Label(label=prop)
        label.set_xalign(0.)
        self.properties[prop] = Gtk.Entry()
        self.properties[prop].editable = False
        self.properties[prop].can_focus = False
        self.pack_end(self.properties[prop], False, False, 3)
        self.pack_end(label, False, False, 3)
    def set_value(self, prop, value):
        self.properties[prop].set_text(str(value))
    
class DisplayKlassObject(KlassObject):
    def __init__(self, name):
        super().__init__(name)
        self.top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.prop_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.image = Gtk.Image()
        self.image.set_hexpand(True)
        self.image.set_vexpand(True)
        self.image.set_halign(Gtk.Align.START)
        self.top_box.pack_start(self.prop_box, True, True, 3)
        self.top_box.pack_start(self.image, True, True, 3)
        self.pack_end(self.top_box, True, True, 3)
        self.width = 0
        self.height = 0
    def add_property(self, prop):
        label = Gtk.Label(label=prop)
        label.set_xalign(0.)
        self.properties[prop] = Gtk.Entry()
        self.properties[prop].editable = False
        self.properties[prop].can_focus = False
        self.prop_box.pack_end(self.properties[prop], False, False, 3)
        self.prop_box.pack_end(label, False, False, 3)
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
        pixbuf = pixbuf.scale_simple(int(self.width * 1.5), int(self.height * 1.5),
                            GdkPixbuf.InterpType.BILINEAR)
        self.image.set_from_pixbuf(pixbuf)
    def _put_pixel(self, pixels, x, y, r, g, b):
        offset = y * self.width + x
        pixels[offset * 3 + 0] = r
        pixels[offset * 3 + 1] = g
        pixels[offset * 3 + 2] = b

class KlassCommandOption:
    def __init__(self, name, type):
        self.name = name
        self.type = type
        self.widget = None
    def get_widget(self):
        if self.type == bool:
            self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.r1 = Gtk.RadioButton.new()
            l = Gtk.Label(label="On")
            self.r1.add(l)
            self.widget.pack_start(self.r1, False, False, 3)
            r2 = Gtk.RadioButton.new_with_label_from_widget(self.r1, "Off")
            self.widget.pack_start(r2, False, False, 3)
            r3 = Gtk.RadioButton.new_with_label_from_widget(self.r1, "Toggle")
            self.widget.pack_start(r3, False, False, 3)
            widget = self.widget
        else:
            widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            label = Gtk.Label(label=self.name)
            self.widget = Gtk.Entry()
            widget.pack_start(label, False, False, 3)
            widget.pack_start(self.widget, True, True, 3)
        return widget
    def get_value(self):
        if self.type == bool:
            for i, r in enumerate(self.r1.get_group()):
                if r.get_active():
                    return 2 - i
            return False
        return self.type(self.widget.get_text())

class KlassCommands(Gtk.Box):
    def __init__(self, klass, objects, callback):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.klass = klass
        self.callback = callback
        self._object_store = Gtk.ListStore(GObject.TYPE_UINT64, str)
        for o in objects:
            self._object_store.append(o)
        self._object_store.set_sort_column_id(0, Gtk.SortType.ASCENDING)
    def add_command(self, cmd_id, name, opts):
        cmd_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        label = Gtk.Label(label=name)
        label.set_xalign(0.)
        label.hexpand = True
        label.hexpand_set = True
        cmd_box.pack_start(label, False, False, 3)
        obj_box = Gtk.ComboBox.new_with_model_and_entry(self._object_store)
        obj_box.set_entry_text_column(1)
        obj_box.set_id_column(0)
        cmd_box.pack_start(obj_box, False, False, 3)
        self.pack_start(cmd_box, False, False, 3)
        cmd_opts = []
        for opt in opts:
            ko = KlassCommandOption(*opt)
            cmd_box.pack_start(ko.get_widget(), False, False, 3)
            cmd_opts.append(ko)
        button = Gtk.Button(label="Execute")
        button.connect("clicked", self.exec_cmd, cmd_id, obj_box, cmd_opts)
        cmd_box.pack_end(button, False, False, 3)
    def exec_cmd(self, button, cmd_id, combo, cmd_opts):
        iter = combo.get_active_iter()
        model = combo.get_model()
        opts = {}
        for opt in cmd_opts:
            opts[opt.name] = opt.get_value()
        if self.klass is ObjectTypes.DIGITAL_PIN:
            if opts["state"] == 2:
                opts[opt.name] = True
                self.callback(self.klass, model[iter][0], cmd_id, opts)
                time.sleep(0.01)
                opts[opt.name] = False
                self.callback(self.klass, model[iter][0], cmd_id, opts)
                return
            else:
                opts[opt.name] = not(bool(opts[opt.name]))
        self.callback(self.klass, model[iter][0], cmd_id, opts)
    def clear(self):
        self._object_store.clear()
        for child in self.get_children():
            self.remove(child)
            child.destroy()
            del child

class KlassFrame(Gtk.Frame):
    def __init__(self, label):
        super().__init__(label=label)
        self.set_label_align(0.01, 0.6)
        self.set_margin_top(5)
        self.set_margin_bottom(5)
        self.set_margin_start(5)
        self.set_margin_end(5)
        self.top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(self.top_box)
        self.events = Gtk.Expander(label="Events")
        self.top_box.pack_end(self.events, True, True, 3)
        self.commands = Gtk.Expander(label="Commands")
        self.top_box.pack_end(self.commands, True, True, 3)
        self._objects = {}
    def add_object(self, obj_id, name, obj):
        scroll = Gtk.ScrolledWindow()
        scroll.add(obj)
        if isinstance(obj, DisplayKlassObject):
            scroll.set_min_content_height(150)
        self.top_box.pack_start(scroll, True, True, 3)
        self._objects[obj_id] = obj
    def add_commands(self, cmds):
        self.commands.add(cmds)
    def add_events(self, events):
        self.events.add(events)
    def remove(self, obj):
        self.top_box.remove(obj)
        for i, o in self._objects.items():
            if i == obj:
                del self._objects[i]
                break
    def get_object(self, obj_id):
        return self._objects.get(obj_id, None)
    def clear(self):
        for child in self.top_box.get_children():
            if isinstance(child, Gtk.Expander):
                c = child.get_child()
                if c:
                    child.remove(c)
                    c.clear()
                    del c
                continue
            self.top_box.remove(child)
            child.destroy()
            del child
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

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        monitor_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        scroll = Gtk.ScrolledWindow()
        object_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroll.add(object_box)
        self.set_widget_margin(object_box, 5)
        for klass in ObjectTypes:
            if klass is ObjectTypes.NONE:
                continue
            label = str(klass).replace('_', " ")
            self.klass_frames[klass] = KlassFrame(label=label.title())
            object_box.pack_start(self.klass_frames[klass], True, True, 3)
        monitor_box.pack_start(scroll, True, True, 3)

        control_box = Gtk.ButtonBox(orientation=Gtk.Orientation.VERTICAL)
        control_box.set_layout(Gtk.ButtonBoxStyle.START)
        control_box.set_spacing(5)
        self.set_widget_margin(control_box, 15)

        self.precision_spin = Gtk.SpinButton.new_with_range(-1, 15, 1)
        self.precision_spin.set_value(8)
        control_box.pack_start(self.precision_spin, False, True, 3)

        pause_button = Gtk.Button(label="Pause")
        pause_button.connect("clicked", self.pause_emulation)
        control_box.pack_start(pause_button, False, True, 3)

        resume_button = Gtk.Button(label="Resume")
        resume_button.connect("clicked", self.resume_emulation)
        control_box.pack_start(resume_button, False, True, 3)
        monitor_box.pack_end(control_box, False, False, 3)

        main_box.pack_start(monitor_box, True, True, 3)

        button_box = Gtk.ButtonBox(orientation=Gtk.Orientation.HORIZONTAL)
        button_box.set_layout(Gtk.ButtonBoxStyle.END)
        exit_button = Gtk.Button(label="Exit")
        exit_button.connect("clicked", self.destroy)
        button_box.pack_end(exit_button, True, True, 3)
        
        main_box.pack_end(button_box, False, True, 3)
        self.add(main_box)
        self.show_all()
        self.timer = GLib.timeout_add(500, self.update)

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
            self.set_widget_margin(self.klass_frames[klass].top_box, 5)
            for i, obj in enumerate(self.emulation_data.objects[klass]):
                # We want the widgets in the scrolled window to be
                # right aligned. So, they have to be added to the end
                # of the horizontal box. However, to get the right
                # layout, the property names have to be reversed and
                # then the entries added before the corresponding
                # label.
                obj_set.append((obj["id"], obj["name"]))
                if klass is ObjectTypes.DISPLAY:
                    kobj = DisplayKlassObject(obj["name"])
                else:
                    kobj = KlassObject(obj["name"])
                props = list(data[obj["id"]].keys())
                props.reverse()
                for j, prop in enumerate(props):
                    if klass is ObjectTypes.DISPLAY and prop == "data":
                        kobj.set_size(data[obj["id"]]["width"],
                                      data[obj["id"]]["height"])
                        kobj.update(data[obj["id"]][prop])
                    else:
                        kobj.add_property(prop)
                        kobj.set_value(prop, data[obj["id"]][prop])
                self.klass_frames[klass].add_object(obj["id"], obj["name"], kobj)
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

def main():
    app = MainWindow()
    Gtk.main()
    return 0

sys.exit(main())
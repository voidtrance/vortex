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
import gi
from vortex.controllers.types import ModuleTypes
gi.require_version("Gtk", "3.0")
gi.require_version('GLib', '2.0')
from gi.repository import Gtk
from gi.repository import GLib


socket_path = "/tmp/vortex_monitor"

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Vortex Monitor")
        self.set_default_size(1024, -1)
        self.connect("destroy", Gtk.main_quit)
        self.connection = None
        self.objects = []

        self.entries = {}
        self.klass_frames = {}
        self.klass_boxes = {}
        self.run_update = True

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        monitor_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        frame = Gtk.Frame(label="Object Status")
        self.set_widget_margin(frame, 5)
        monitor_box.pack_start(frame, True, True, 3)

        object_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_widget_margin(object_box, 5)
        for klass in ModuleTypes:
            if klass is ModuleTypes.NONE:
                continue
            label = str(klass).replace('_', " ")
            self.klass_frames[klass] = Gtk.Frame(label=label.title())
            self.klass_frames[klass].set_label_align(0.01, 0.6)
            object_box.pack_start(self.klass_frames[klass], True, True, 3)
        frame.add(object_box)

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

    def send_request(self, request, data={}):
        request = {"request": request}
        request.update(data)
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
        if isinstance(value, float):
            if precision != -1:
                if value and round(value, precision):
                    value = round(value, precision)
        elif isinstance(value, list):
            value = ", ".join([str(x) for x in value if not isinstance(x,str) or x])
        return str(value)
    
    def populate_grids(self, data):
        for klass in self.objects:
            self.klass_boxes[klass] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.set_widget_margin(self.klass_boxes[klass], 5)
            self.klass_frames[klass].add(self.klass_boxes[klass])
            for i, obj in enumerate(self.objects[klass]):
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                object_label = Gtk.Label(label='')
                object_label.set_markup(f'<b>{obj["name"]}</b>')
                object_label.hexpand = True
                object_label.hexpand_set = True
                object_label.set_xalign(0.)
                hbox.pack_start(object_label, False, False, 3)
                self.entries[obj["id"]] = {}
                scroll = Gtk.ScrolledWindow()
                hbox.pack_end(scroll, True, True, 3)
                prop_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
                scroll.add(prop_hbox)
                # We want the widgets in the scrolled window to be
                # right aligned. So, they have to be added to the end
                # of the horizontal box. However, to get the right
                # layout, the property names have to be reversed and
                # then the entries added before the corresponding
                # label.
                props = list(data[obj["id"]].keys())
                props.reverse()
                for j, prop in enumerate(props):
                    entry = Gtk.Entry()
                    entry.editable = False
                    entry.can_focus = False
                    value = self.get_data_value(data[obj["id"]][prop])
                    entry.set_text(value)
                    prop_hbox.pack_end(entry, False, False, 3)
                    self.entries[obj["id"]][prop] = entry
                    label = Gtk.Label(label=prop)
                    prop_hbox.pack_end(label, False, False, 3)
                self.klass_boxes[klass].pack_start(hbox, False, False, 3)
        self.show_all()

    def set_widget_margin(self, widget, top, bottom=None, left=None, right=None):
        widget.set_margin_top(top)
        widget.set_margin_bottom(bottom if bottom is not None else top)
        widget.set_margin_start(left if left is not None else top)
        widget.set_margin_end(right if right is not None else top)

    def pause_emulation(self, button):
        self.send_request("pause", {"action": True})
        return self.get_response()
    
    def resume_emulation(self, button):
        self.send_request("pause", {"action": False})
        return self.get_response()
    
    def get_status(self, klass=None):
        obj_ids = []
        klass_set = [klass] if klass is not None else [x for x in ModuleTypes]
        for klass in klass_set:
            if klass not in self.objects:
                continue                
            for obj in self.objects[klass]:
                obj_ids.append(obj["id"])
        try:
            self.send_request("query", {"objects": obj_ids})
            return self.get_response()
        except (BrokenPipeError, EOFError):
            self.connection = None
            for klass in ModuleTypes:
                if klass in self.klass_frames and klass in self.klass_boxes:
                    self.klass_frames[klass].remove(self.klass_boxes[klass])
            self.klass_boxes.clear()
            self.objects.clear()
            return None

    def update(self):
        need_populate = False
        if self.connection is None:
            self.connect_to_server()
            if self.connection is None:
                return self.run_update
        if not self.objects:
            self.send_request("object_list")
            data = self.get_response()
            self.objects = data["objects"]
            need_populate = True
        try:
            status = self.get_status()
        except:
            status = None
        if status is None:
            return self.run_update
        if need_populate:
            self.populate_grids(status)
        for obj_id in status:
            for prop in status[obj_id]:
                value = self.get_data_value(status[obj_id][prop])
                self.entries[obj_id][prop].set_text(value)
        return self.run_update
    
    def destroy(self, button):
        self.run_update = False
        super().destroy()

def main():
    app = MainWindow()
    Gtk.main()
    return 0

sys.exit(main())
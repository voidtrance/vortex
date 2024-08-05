# vortex - GCode machine emulator
# Copyright (C) 2024  Mitko Haralanov
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
import select
import os
import logging
from vortex.frontends import BaseFrontend
from vortex.controllers.types import ModuleTypes
import vortex.frontends.lib

class DirectFrontend(BaseFrontend):
    FIFO = "/tmp/direct_frontend_fifo"
    def __init__(self):
        super().__init__()
        try:
            os.mkfifo(self.FIFO)
        except FileExistsError:
            pass
        mfd, sfd = vortex.frontends.lib.create_pty(self.FIFO)
        self._fd = os.fdopen(mfd, 'r')
        self._poll = select.poll()
        self._poll.register(self._fd, select.POLLIN|select.POLLHUP)
        self._command_id_queue = []

    def _process_commands(self, *args):
        while self._run:
            events = self._poll.poll(0.1)
            if not events or self._fd.fileno() not in [e[0] for e in events]:
                continue
            event = [e for e in events if e[0] == self._fd.fileno()]
            if not (event[0][1] & select.POLLIN):
                continue
            cmd = self._fd.readline()
            logging.debug(f"Received command: {cmd.strip()}")
            try:
                parts = cmd.strip().split(':', maxsplit=4)
                klass, object, cmd = parts[:3]
                opts = ""
                timestamp = 0
                if len(parts) == 4:
                    opts = parts[3]
                if len(parts) == 5:
                    timestamp = int(parts[4])
            except ValueError as e:
                print(e)
                continue

            klass = ModuleTypes[klass]
            self.queue_command(klass, object, cmd, opts, timestamp)

    def __del__(self):
        self._fd.close()
        os.unlink(self.FIFO)

    def complete_command(self, id, result):
        logging.debug(f"Command {id} complete: {result}")
        super().complete_command(id, result)

    def event_handler(self, event, owner, timestamp, *args):
        super().event_handler(event, owner, timestamp, *args)
        if event == "move_complete":
            print(owner.get_status())


def create():
    return DirectFrontend()
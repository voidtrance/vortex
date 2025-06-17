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
from vortex.frontends import BaseFrontend
from vortex.core import ObjectTypes
from vortex.frontends.proto import CommandStatus, Completion

class DirectFrontend(BaseFrontend):
    def __init__(self):
        super().__init__()

    def _process_command(self, data):
        cmd = data.decode().strip()
        self.log.debug(f"Received command: {cmd}")
        try:
            parts = cmd.split(':', maxsplit=4)
            klass, object, cmd = parts[:3]
            opts = ""
            timestamp = 0
            if len(parts) == 4:
                opts = parts[3]
            if len(parts) == 5:
                timestamp = int(parts[4])
        except ValueError as e:
            if cmd == "reset":
                status = self.reset()
                if status:
                    super().respond(CommandStatus.SUCCESS, True)
                else:
                    super().respond(CommandStatus.FAIL, False)
            else:
                self.log.error(f"Unable to parse command: {e}")
            return

        klass = ObjectTypes[klass.upper()]
        cmd_id = self.queue_command(klass, object, cmd, opts)
        if cmd_id is False:
            self.log.error("Failed to queue command")
            super().respond(CommandStatus.FAIL, False)
        else:
            super().respond(CommandStatus.QUEUED, cmd_id)

    def complete_command(self, id, result, data=None):
        self.log.debug(f"Command {id} complete: {result}")
        super().complete_command(id, result, data)
        super().respond(CommandStatus.COMPLETE, Completion(id, result, data))

    def event_handler(self, event, owner, timestamp, *args):
        super().event_handler(event, owner, timestamp, *args)
        if event == "move_complete":
            print(owner.get_status())


def create():
    return DirectFrontend()
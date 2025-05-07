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
import errno
from vortex.core import ObjectTypes

class VirtualObjectBase:
    type = ObjectTypes.NONE
    commands = []
    events = []
    virtual = True
    def __init__(self, config, obj_lookup, obj_query, cmd_complete, event_submit):
        self.config = config
        self.lookup = obj_lookup
        self.query = obj_query
        self._event_submit = event_submit
        self._cmd_complete = cmd_complete
        self._id = -1
    def exec_command(self, cmd_id, cmd, opts):
        if not self.commands:
            return -errno.EINVAL
        command = None
        for _cmd in self.commands:
            if _cmd[0] == cmd:
                command = _cmd
                break
        if not command:
            return -errno.EINVAL
        for opt, type in command[2]:
            if opts.get(opt, None) is None:
                return -errno.EINVAL
        return 0
    def event_submit(self, event, data):
        self._event_submit(event, self._id, data)
    def complete_command(self, cmd_id, status):
        self._cmd_complete(cmd_id, status)
    def get_status(self):
        return {}
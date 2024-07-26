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
import pty
import os
import fcntl
import termios

def create_pty(filename):
    master, slave = pty.openpty()
    try:
        os.unlink(filename)
    except os.error:
        pass
    os.symlink(os.ttyname(slave), filename)
    fcntl.fcntl(master, fcntl.F_SETFL, fcntl.fcntl(master, fcntl.F_GETFL) | os.O_NONBLOCK)
    tcattr = termios.tcgetattr(master)
    tcattr[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                    termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON)
    tcattr[1] &= ~termios.OPOST
    tcattr[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG |
                    termios.IEXTEN)
    tcattr[2] &= ~(termios.CSIZE | termios.PARENB)
    tcattr[2] |= termios.CS8
    tcattr[6][termios.VMIN] = 0
    tcattr[6][termios.VTIME] = 0
    termios.tcsetattr(master, termios.TCSAFLUSH, tcattr)
    return (master, slave)
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
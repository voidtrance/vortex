import queue
import uuid
from collections import OrderedDict
import logging
from lib.constants import *
from controllers.core import CoreError
from ctypes import addressof

__all__ = ["Emulator"]

class Command:
    def __init__(self, obj_id, cmd_id, opts, timestamp=None):
        self.obj_id, self.cmd_id, self.opts, self.time = \
            obj_id, cmd_id, opts, timestamp
        self.id = uuid.uuid4()
    def __str__(self):
        return f"[{self.obj_id}:{self.cmd_id}@{self.time}"
        
class CommandQueue(queue.Queue):
    def put(self, command):
        if not isinstance(command, Command):
            raise ValueError("'command' is not a Command instance")
        super().put(command)
        return command.id
    def queue_command(self, obj_id, cmd_id, opts, timestamp=None):
        return self.put(Command(obj_id, cmd_id, opts, timestamp))

class ScheduleQueue:
    class TimeDict(OrderedDict):
        def __setitem__(self, timestamp, value):
            super().__setitem__(timestamp, queue.Queue())
            self[timestamp].put(value)
            if timestamp < list(self.keys())[-1]:
                self.clear()
                self.update(dict(sorted(self.items()))) 

    def __init__(self):
        # Queue of commands that are not scheduled at a specific
        # time. These commands can be executed on the next emulator
        # cycle.
        self._now = queue.Queue()

        # Command queues indexed by execution timestamp. These
        # commands need to be executed at or before the specified
        # time.
        self._timeslots = self.TimeDict()

    def put(self, command):
        if command.time is None:
            self._now.put(command)
        else:
            self._timeslots[command.time] = command

    def get(self, timestamp):
        # Return the first available command. If the non-scheduled
        # queue has pending commands, return those first.
        if not self._now.empty():
            return self._now.get()
        if self._timeslots:
            # Get all timestamps on or before 'timestamp'.
            stamps = [x for x in self._timeslots if x <= timestamp]
            if not stamps:
                return None
            first = stamps[0]
            command = self._timeslots[first].get()
            if self._timeslots[first].empty():
                self._timeslots.popitem(first)
            return command
        return None

    def get_all(self, timestamp):
        # Iterate over all commands scheduled on or before 'timestamp'
        command = self.get(timestamp)
        while command is not None:
            yield command
            command = self.get(timestamp)
        return None
            
EMULATOR_MAX_FREQUENCY = 1 * MHZ2HZ

class Emulator:
    def __init__(self, controller, frontend):
        self._command_queue = CommandQueue()
        self._frontend = frontend
        self._frontend.set_command_queue(self._command_queue)
        self._frontend.set_controller_data(controller.get_params())
        self._controller = controller
        self._scheduled_queue = ScheduleQueue()
        self._run_emulation = True
        self._frequency = 0

    def set_frequency(self, frequency):
        if (frequency / MHZ2HZ) > 10:
            logging.warning("Frequency greater than 10MHz may result in inaccurate timing")
        self._frequency = frequency

    def run(self):
        try:
           self._controller.start(self._frequency)
        except CoreError:
            self._controller.stop()
            return
        self._frontend.run()
        while self._run_emulation:
            timestep = self._controller.get_timestep()
            self._schedule_commands(timestep)
            self._process_schedule(timestep)
    
    def stop(self):
        self._frontend.stop()
        self._controller.stop()

    def _schedule_commands(self, timestep):
        if not self._command_queue.empty():
            cmd = self._command_queue.get()
            cmd.time = timestep
            self._scheduled_queue.put(cmd)

    def _process_schedule(self, timestamp):
        for command in self._scheduled_queue.get_all(timestamp):
            result = self._controller.exec_command(command.id.hex, command.obj_id,
                                                   command.cmd_id, addressof(command.opts))
            self._frontend.complete_command(command.id, result)
            

        
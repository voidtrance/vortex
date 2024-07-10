import time

class Event:
    def __init__(self, name, owner, args=()):
        self.name = name
        self.owner = owner
        self.timestamp = 0
        self.args = args

class EventFactory:
    def __init__(self, owner):
        self.owner = owner

    def create(self, name, *args):
        return Event(name, self.owner, args)
    
class EventQueue:
    def __init__(self):
        self._queue = []
        self._handlers = {}

    def register_handler(self, event, handler):
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append(handler)

    def unregister_handler(self, handler):
        for event in self._handlers:
            self._handlers[event].remove(handler)

    def queue_event(self, event):
        assert isinstance(event, Event)
        event.timestamp = time.time_ns()
        self._queue.append(event)

    def process_queue(self):
        for event in self._queue:
            handlers = self._handlers.get(f"{event.owner.config.name}:{event.name}", [])
            for handler in handlers:
                handled = handler(event.name, event.owner, event.timestamp, *event.args)
                if handled:
                    self.unregister_handler(handler)
        self._queue.clear()

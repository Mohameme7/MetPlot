from collections import defaultdict
import asyncio

class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, event_type, handler):
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type, *args, **kwargs):
        for handler in self._subscribers[event_type]:
            if asyncio.iscoroutinefunction(handler):
                await handler(*args, **kwargs)
            else:
                handler(*args, **kwargs)

class Observable:
    def __init__(self,name, inital_value, bus):
        self.name = name
        self._value = inital_value
        self._bus = bus

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        old_value = self._value
        self._value = value
        asyncio.run(
            self._bus.publish(f"{self.name}_changed",)
            )



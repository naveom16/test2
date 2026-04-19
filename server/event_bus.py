import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self) -> None:
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable = None):
        if handler is None:
            def decorator(fn: Callable):
                self.subscribers.setdefault(event_name, []).append(fn)
                logger.debug("Subscribed handler to event '%s'", event_name)
                return fn
            return decorator

        self.subscribers.setdefault(event_name, []).append(handler)
        logger.debug("Subscribed handler to event '%s'", event_name)
        return handler

    def publish(self, event_name: str, *args, **kwargs) -> None:
        logger.info("Event published: %s %s %s", event_name, args or '', kwargs or '')
        for handler in self.subscribers.get(event_name, []):
            try:
                handler(*args, **kwargs)
            except Exception as exc:
                logger.exception("Error in event handler '%s': %s", event_name, exc)

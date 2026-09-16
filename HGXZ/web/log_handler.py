from __future__ import annotations

import collections
import logging
import queue
import time


class LogBuffer(logging.Handler):
    """Thread-safe logging handler that keeps recent records in a ring buffer
    and notifies WebSocket subscribers via stdlib queues."""

    def __init__(self, maxlen: int = 2000):
        super().__init__()
        self.buffer: collections.deque[dict] = collections.deque(maxlen=maxlen)
        self._queues: list[queue.Queue] = []

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            'level': record.levelname,
            'message': self.format(record),
            'timestamp': record.created,
        }
        self.buffer.append(entry)
        for q in list(self._queues):
            try:
                q.put_nowait(entry)
            except queue.Full:
                pass

    def recent(self, n: int = 200) -> list[dict]:
        items = list(self.buffer)
        return items[-n:]

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        self._queues.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

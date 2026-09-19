"""Short-lived server-memory credentials, never serialized to cookies or disk."""
from threading import RLock
from time import monotonic


class SessionKeys:
    def __init__(self, ttl=8 * 60 * 60, clock=monotonic):
        self._values = {}
        self._lock = RLock()
        self._ttl, self._clock = ttl, clock

    def put(self, session_id, key):
        with self._lock:
            now = self._clock()
            self._values = {sid: value for sid, value in self._values.items() if value[1] > now}
            self._values[session_id] = (key, now + self._ttl)

    def get(self, session_id):
        with self._lock:
            value = self._values.get(session_id)
            if value and value[1] > self._clock():
                return value[0]
            self._values.pop(session_id, None)
            return None

    def remove(self, session_id):
        with self._lock:
            self._values.pop(session_id, None)

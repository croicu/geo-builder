from __future__ import annotations

import json as _json
import queue as _queue
import secrets
import threading
from typing import Any, Callable

from ..diagnostics import Logger

_PING_ID = "__geo_ping__"


class Api:
    def __init__(self, send: Callable[[str], None]) -> None:
        self._send = send
        self._queue: _queue.Queue[tuple | None] = _queue.Queue()
        self._handlers: dict[str, Callable[[Any], None]] = {}
        self._token: str | None = None
        self._thread: threading.Thread | None = None
        self.is_open = False
        self.subscribe(_PING_ID, self._on_ping)

    def invoke(self, id: str, payload: Any) -> None:
        self._queue.put(("invoke", id, payload))

    def subscribe(self, id: str, fn: Callable[[Any], None]) -> None:
        self._handlers[id] = fn

    def ping(self) -> None:
        self.is_open = False
        self._token = secrets.token_hex(16)
        self.invoke(_PING_ID, self._token)

    def run(self) -> None:
        self._thread = threading.current_thread()
        while True:
            item = self._queue.get()
            if item is None:
                break
            kind = item[0]
            if kind == "invoke":
                _, id, payload = item
                msg = _json.dumps({"id": id, "data": payload})
                self._send(f"window.__geo_dispatch({msg})")
            elif kind == "msg":
                self._dispatch(item[1])

    def stop(self) -> None:
        self._queue.put(None)

    def _on_message(self, raw: str) -> None:
        self._queue.put(("msg", raw))

    def _on_ping(self, payload: Any) -> None:
        if payload == self._token:
            self.is_open = True
            Logger.info("API gateway opened.")
        else:
            Logger.warning(f"Ping token mismatch: expected {self._token!r}, got {payload!r}")

    def _dispatch(self, raw: str) -> None:
        assert threading.current_thread() is self._thread, "Api._dispatch must run on the dispatcher thread"
        try:
            msg = _json.loads(raw)
            handler = self._handlers.get(msg.get("id", ""))
            if handler is not None:
                handler(msg.get("data"))
        except Exception:
            pass

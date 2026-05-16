from __future__ import annotations

import json as _json
import secrets
from typing import Any, Callable

from ..diagnostics import Logger

_HANDSHAKE_ID = "__geo_handshake__"


class Api:
    def __init__(self, send: Callable[[str], None]) -> None:
        self._send = send
        self._handlers: dict[str, Callable[[Any], None]] = {}
        self._token: str | None = None
        self.is_open = False
        self.subscribe(_HANDSHAKE_ID, self._on_handshake)

    def invoke(self, id: str, payload: Any) -> None:
        msg = _json.dumps({"id": id, "data": payload})
        self._send(f"window.__geo_dispatch({msg})")

    def subscribe(self, id: str, fn: Callable[[Any], None]) -> None:
        self._handlers[id] = fn

    def ping(self) -> None:
        self.is_open = False
        self._token = secrets.token_hex(16)
        self.invoke(_HANDSHAKE_ID, self._token)

    def _on_handshake(self, payload: Any) -> None:
        if payload == self._token:
            self.is_open = True
            Logger.info("API gateway opened.")
        else:
            Logger.warning(f"Handshake token mismatch: expected {self._token!r}, got {payload!r}")

    def _on_message(self, raw: str) -> None:
        try:
            msg = _json.loads(raw)
            handler = self._handlers.get(msg.get("id", ""))
            if handler is not None:
                handler(msg.get("data"))
        except Exception:
            pass

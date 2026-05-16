from __future__ import annotations

import dataclasses
import json as _json
import queue as _queue
import secrets
import threading
from typing import Any, Callable

from ..api import READY_ID as _READY_ID
from ..api import ReadyData
from ..diagnostics import Logger


@dataclasses.dataclass
class MethodDef:
    """JS → Python: a method the browser can call."""
    id: str
    input_type: type
    output_type: type | None


@dataclasses.dataclass
class EventDef:
    """Python → JS: an event the builder can fire."""
    id: str
    input_type: type
    output_type: type | None


class Gateway:
    def __init__(self, send: Callable[[str], None]) -> None:
        self._send = send
        self._queue: _queue.Queue[tuple | None] = _queue.Queue()
        self._thread: threading.Thread | None = None

        self._methods: dict[str, MethodDef] = {}   # JS → Python
        self._events: dict[str, EventDef] = {}     # Python → JS
        self._pending: dict[str, tuple[Callable, type | None]] = {}
        self._handlers: dict[str, dict[int, Callable]] = {}
        self._next_cookie: int = 0

        self.is_open = False

        self.define_event(_READY_ID, ReadyData)

    # --- Registration ---

    def define_method(self, id: str, input_type: type, output_type: type | None = None) -> None:
        """JS → Python: register a method the browser can call."""
        self._methods[id] = MethodDef(id=id, input_type=input_type, output_type=output_type)
        self._handlers.setdefault(id, {})

    def define_event(self, id: str, input_type: type, output_type: type | None = None) -> None:
        """Python → JS: declare an event the builder can fire."""
        self._events[id] = EventDef(id=id, input_type=input_type, output_type=output_type)

    def register(self, id: str, fn: Callable) -> int:
        self._handlers.setdefault(id, {})
        cookie = self._next_cookie
        self._next_cookie += 1
        self._handlers[id][cookie] = fn
        return cookie

    def unregister(self, cookie: int) -> None:
        for handlers in self._handlers.values():
            if cookie in handlers:
                del handlers[cookie]
                return

    # --- Outbound (Python → JS) ---

    def call(self, id: str, data: Any, callback: Callable | None = None) -> None:
        self._queue.put(("call", id, callback, data))

    def ready(self) -> None:
        self.is_open = True
        self.call(_READY_ID, ReadyData())
        Logger.info("API gateway ready.")

    # --- Dispatcher loop ---

    def run(self) -> None:
        self._thread = threading.current_thread()
        while True:
            item = self._queue.get()
            if item is None:
                break
            kind = item[0]
            if kind == "call":
                self._process_call(item[1], item[2], item[3])
            elif kind == "msg":
                self._dispatch(item[1])

    def stop(self) -> None:
        self._queue.put(None)

    # --- Inbound (JS → Python) ---

    def _on_message(self, raw: str) -> None:
        self._queue.put(("msg", raw))

    # --- Internals ---

    def _process_call(self, id: str, callback: Callable | None, data: Any) -> None:
        event = self._events.get(id)
        if event is None:
            Logger.warning(f"call: unknown event '{id}'")
            return
        request_id = secrets.token_hex(8) if callback is not None else None
        if request_id is not None:
            self._pending[request_id] = (callback, event.output_type)
        payload = dataclasses.asdict(data) if dataclasses.is_dataclass(data) else data
        msg: dict[str, Any] = {"id": id, "data": payload}
        if request_id is not None:
            msg["requestId"] = request_id
        self._send(f"window.__geo_dispatch({_json.dumps(msg)})")

    def _dispatch(self, raw: str) -> None:
        assert threading.current_thread() is self._thread, "Gateway._dispatch must run on the dispatcher thread"
        try:
            msg = _json.loads(raw)
            request_id = msg.get("requestId")
            method_id = msg.get("id")
            data = msg.get("data", {})

            if method_id is None and request_id is not None:
                # Response to a Python event call
                entry = self._pending.pop(request_id, None)
                if entry is not None:
                    callback, output_type = entry
                    result = output_type(**data) if output_type and isinstance(data, dict) else data
                    callback(result)

            elif method_id is not None:
                # Method call from JS
                method = self._methods.get(method_id)
                if method is None:
                    Logger.warning(f"dispatch: unknown method '{method_id}'")
                    return
                input_data = method.input_type(**data) if isinstance(data, dict) else data
                output = None
                for fn in self._handlers.get(method_id, {}).values():
                    result = fn(input_data)
                    if result is not None:
                        output = result
                if request_id and method.output_type and output is not None:
                    response: dict[str, Any] = {
                        "requestId": request_id,
                        "data": dataclasses.asdict(output),
                    }
                    self._send(f"window.__geo_dispatch({_json.dumps(response)})")

        except Exception as exc:
            Logger.warning(f"dispatch error: {exc}")

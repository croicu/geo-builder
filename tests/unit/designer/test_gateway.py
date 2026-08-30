import json
from dataclasses import dataclass

from geo_builder.designer.gateway import Gateway


@dataclass
class StubEventData:
    message: str


class TestCallNow:
    def test_sends_immediately_without_draining_queue(self):
        sent = []
        gateway = Gateway(sent.append)
        gateway.define_event("stub_event", StubEventData)

        gateway.call_now("stub_event", StubEventData(message="hello"))

        assert len(sent) == 1
        payload = json.loads(sent[0].removeprefix("window.__geo_dispatch(").removesuffix(")"))
        assert payload == {"id": "stub_event", "data": {"message": "hello"}}

    def test_unknown_event_logs_warning_and_sends_nothing(self):
        sent = []
        gateway = Gateway(sent.append)

        gateway.call_now("does_not_exist", StubEventData(message="hello"))

        assert sent == []

    def test_does_not_enqueue(self):
        """call_now must bypass _queue entirely -- queued call() sits there until drained."""
        sent = []
        gateway = Gateway(sent.append)
        gateway.define_event("stub_event", StubEventData)

        gateway.call_now("stub_event", StubEventData(message="hello"))

        assert gateway._queue.empty()

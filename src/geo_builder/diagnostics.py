from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum


class TelemetryLevel(Enum):
    VERBOSE = "verbose"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TelemetryRecord:
    def __init__(self, timestamp: datetime, level: TelemetryLevel, message: str) -> None:
        self.timestamp = timestamp
        self.level = level
        self.message = message


class DiagnosticsLogSink:
    _pending: list[TelemetryRecord] = []

    def log(self, level: TelemetryLevel, message: str) -> TelemetryRecord:
        record = TelemetryRecord(
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
        )
        DiagnosticsLogSink._pending.append(record)
        return record

    def flush(self) -> None:
        _logger = logging.getLogger("tpl")
        for record in DiagnosticsLogSink._pending:
            _logger.warning("%s: %s", record.timestamp.isoformat(), record.message)

    def clear(self) -> None:
        DiagnosticsLogSink._pending.clear()

    def drain(self) -> list[str]:
        messages = [r.message for r in DiagnosticsLogSink._pending]
        DiagnosticsLogSink._pending.clear()
        return messages

    def print(self, message: str) -> None:
        print(message)

    def diagnostic(self, message: str) -> None:
        self.log(TelemetryLevel.VERBOSE, message)

    def info(self, message: str) -> None:
        self.log(TelemetryLevel.INFO, message)

    def warning(self, message: str) -> None:
        self.log(TelemetryLevel.WARNING, message)

    def error(self, message: str) -> None:
        self.log(TelemetryLevel.ERROR, message)

    def fatal(self, message: str) -> None:
        self.log(TelemetryLevel.CRITICAL, message)


_LEVEL_RANK: dict[TelemetryLevel, int] = {
    TelemetryLevel.VERBOSE: 0,
    TelemetryLevel.INFO: 1,
    TelemetryLevel.WARNING: 2,
    TelemetryLevel.ERROR: 3,
    TelemetryLevel.CRITICAL: 4,
}


class ConsoleLogSink(DiagnosticsLogSink):
    def __init__(self, min_level: TelemetryLevel = TelemetryLevel.ERROR) -> None:
        self._min_level = min_level

    def log(self, level: TelemetryLevel, message: str) -> TelemetryRecord:
        record = super().log(level, message)
        if _LEVEL_RANK[level] >= _LEVEL_RANK[self._min_level]:
            print(f"[{level.value.upper()}] {record.message}", flush=True)
        return record


class Logger:
    # Public

    @staticmethod
    def set_logger(value: DiagnosticsLogSink | None) -> None:
        if value is None:
            if len(Logger._sinks) > 1:
                Logger._sinks.pop()
        else:
            Logger._sinks.append(value)

    @staticmethod
    def log(level: TelemetryLevel, message: str) -> TelemetryRecord:
        return Logger._sink().log(level, message)

    @staticmethod
    def flush() -> None:
        Logger._sink().flush()

    @staticmethod
    def clear() -> None:
        Logger._sink().clear()

    @staticmethod
    def drain() -> list[str]:
        return Logger._sink().drain()

    @staticmethod
    def print(message: str) -> None:
        Logger._sink().print(message)

    @staticmethod
    def diagnostic(message: str) -> None:
        Logger._sink().diagnostic(message)

    @staticmethod
    def info(message: str) -> None:
        Logger._sink().info(message)

    @staticmethod
    def warning(message: str) -> None:
        Logger._sink().warning(message)

    @staticmethod
    def error(message: str) -> None:
        Logger._sink().error(message)

    @staticmethod
    def fatal(message: str) -> None:
        Logger._sink().fatal(message)

    @staticmethod
    def _reset() -> None:
        Logger._sinks = [DiagnosticsLogSink()]

    # Private

    @staticmethod
    def _sink() -> DiagnosticsLogSink:
        return Logger._sinks[-1]

    # Members

    _sinks: list[DiagnosticsLogSink] = [DiagnosticsLogSink()]

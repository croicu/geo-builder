from __future__ import annotations

from contextlib import contextmanager
from enum import Enum

from .diagnostics import Logger, TelemetryLevel, TelemetryRecord


@contextmanager
def telemetry_session():
    try:
        yield
    finally:
        Logger.flush()
        Logger.clear()


class GeoError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.record: TelemetryRecord = Logger.log(TelemetryLevel.WARNING, message)


class TaskError(GeoError):
    pass


class CatalogError(GeoError):
    pass


class ProviderErrorReason(Enum):
    """Why a provider fetch failed, and what AcquisitionWorker should do about it."""

    TOO_LARGE = "too_large"  # query rejected as too large — splitting the bbox may help
    RATE_LIMITED = "rate_limited"  # rate limited — splitting won't help, defer and retry as-is
    FATAL = "fatal"  # unrecoverable — neither splitting nor retrying will help


class ProviderError(GeoError):
    def __init__(self, message: str, reason: ProviderErrorReason = ProviderErrorReason.FATAL) -> None:
        super().__init__(message)
        self.reason = reason


class WorkerError(GeoError):
    pass

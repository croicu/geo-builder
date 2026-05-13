from __future__ import annotations


class GeoError(Exception):
    pass


class TaskError(GeoError):
    pass


class CatalogError(GeoError):
    pass


class ProviderError(GeoError):
    pass


class WorkerError(GeoError):
    pass

# CLAUDE.md

## Mission

Build a simple, deterministic Python application that creates static geographic datasets for the geo ecosystem.

## Core Invariants

1. `geo-builder` builds; `geo-browser` displays.
2. Internal processing uses strongly typed dataclasses.
3. `protocols.py` contains persisted/shared data contracts.
4. `contracts.py` contains runtime behavioral interfaces.
5. Execution mutates an in-memory catalog.
6. Persistence occurs only after successful completion.
7. Child paths are relative to their parent files.
8. Prefer explicit, readable Python over clever abstractions.
9. Tests must run offline.
10. Static artifacts are immutable and deterministic.

## Processing Pipeline

```text
Task[]
    → Executor (stack-based DFS)
    → WorkerFactory
    → Worker.execute(executor)
    → Catalog mutation
    → Result.save()
```

## Task Types

- AcquisitionTask
- DedupingTask
- AggregationTask

## Worker Responsibilities

- AcquisitionWorker: provider fetch + area creation + layer insertion
- DedupingWorker: remove near-duplicates within each layer
- AggregationWorker: merge compatible layers within an area

## Provider Strategy

Providers are isolated under `providers/`.

Current:
- OverpassProvider

Future:
- FlickrProvider
- NominatimProvider

# IMPLEMENTATION.md

## Suggested Layout

```text
geo_builder/
  cli.py
  tasks.py
  executor.py
  protocols.py
  contracts.py

  workers/
    acquisition_worker.py
    deduping_worker.py
    aggregation_worker.py
    worker_factory.py

  providers/
    provider_factory.py
    overpass_provider.py

tests/
docs/
```

## CLI

```text
geo-builder <task_path> [--in <in_directory>] [--out <out_directory>]
```

## Execution Model

The executor uses a stack (`append` / `pop`) to process tasks depth-first.

## Acquisition

1. Resolve provider
2. `executor.add_area(task)`
3. Fetch layer
4. `executor.add_layer(area, layer)`
5. On provider failure, split bbox into four tasks

## Deduplication

- Scope: one layer
- Distance threshold: 10 meters
- First feature wins
- Alternate names and amenities are accumulated into arrays

## Aggregation

- Scope: one area
- Group by `mergeKey`
- Concatenate features
- Replace source layers with one merged layer

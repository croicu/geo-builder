# Python Repo Template

## Status: Implementation

## GitHub Issue: [geo-builder#60](https://github.com/croicu/geo-builder/issues/60)

## Problem statement

GitHub repo template for python projects using Claude as a coding assistant. The repo has to be
abstract — filled in once a new repo is created from it. `CLAUDE.md` and `./docs` should carry
rules that apply to any future python repo, with nothing specific to geo-builder. The base
classes proven out in geo-builder (`cli`, `errors`, `settings`, `diagnostics`, `contracts`,
`result`) should be preseeded rather than rebuilt from scratch each time.

The target is `./tpl-py`, already cloned locally as its own git repo (separate remote, currently
empty aside from `LICENSE`).

## Design decisions

- **Mechanism**: plain GitHub "template repository" (fork-and-rename), not cookiecutter/copier.
  Nothing prompts for values at generation time — placeholders are replaced by hand (or by
  asking Claude) right after creating the new repo.
- **Placeholder tokens**: dunder-wrapped (`__token__`), so a single case-insensitive grep for
  `__` surfaces every spot needing a replacement, including the package directory itself
  (Python allows dunder-named packages/modules as ordinary identifiers — unconventional, but
  functional, and it's overwritten within minutes of forking anyway):
  - `__package_name__` — importable package identifier (snake_case). Used for the
    `src/__package_name__/` directory and all internal imports.
  - `__project_name__` — distribution/CLI name. Used in `pyproject.toml`'s `[project].name`
    and the `[project.scripts]` key.
  - `__description__` — one-line description. Used in `pyproject.toml`'s `description` and the
    README tagline.
  - `__mission__` — body text of CLAUDE.md's `## Mission` section.
  - Instructions for performing the replacement live in `tpl-py/tasks/repo_setup.md`, following
    the same task-file lifecycle CLAUDE.md's own task workflow already defines: referenced from
    CLAUDE.md's `## New Task` section (same pattern as this repo), handed to Claude the first
    time the new repo is opened, and deleted once the repo is functional (placeholders replaced,
    build green) — no separate `SETUP.md` mechanism needed.
- **Base modules** — ported as full working generic skeletons (not stubs/TODOs), stripped of
  geo-builder-specific fields (e.g. `designUrl`, `logCategories`):
  - `cli.py` — argparse-based entrypoint, stdlib only (no click/typer — matches geo-builder,
    avoids a new dependency every future repo would inherit)
  - `errors.py` — generic error hierarchy
  - `settings.py` — generic `settings.json` loader
  - `diagnostics.py` — `Logger` + sink pattern; category-filtering mechanics kept, geo-builder's
    specific categories dropped
  - `contracts.py` — convention/skeleton for runtime behavioral interfaces
  - `result.py` — result-wrapper pattern
- **Docs** — `CLAUDE.md` (mission placeholder + the process/style rules already proven out here:
  task workflow with status labels, logging rules, coding style, "before committing" commands)
  plus skeleton `docs/ARCHITECTURE.md` and `docs/PROTOCOL.md` (section headers only, filled in
  per project). Excluded as too geo-builder-specific to templatize usefully: `LAYERS.md`,
  `MANIFEST.md`, `MESSAGING.md`, `ROADMAP.md`, `SUMMARY.md`, `IMPLEMENTATION.md`, `CLI.md`.
- **CI/CD** — `.github/workflows/ci.yaml` and `cd.yaml` copied near-verbatim; both are already
  fully generic (lint + format-check + pytest on push/PR; tag-triggered build + GH release).
- **pyproject.toml** — empty runtime `dependencies`; `dev = ["pytest", "ruff"]`; ruff config
  (line-length, target-version, `select = [E, F, I]`, format quote/indent style) copied as-is;
  `requires-python = ">=3.12"` kept.
- **License** — MIT, fixed to "Alexandru Croicu" (not a placeholder — every repo made from this
  template is the same author).

## Open questions

None outstanding — ready to move to Implementation.

## Implementation plan

```
tpl-py/
├── LICENSE                          MIT, Alexandru Croicu (fixed, already present)
├── README.md                        __project_name__ / __description__ placeholders
├── .gitignore                       generic Python entries + settings.local.json
├── pyproject.toml                   __project_name__/__package_name__/__description__; empty deps; dev=[pytest,ruff]; ruff config
├── pytest.ini                       single source of pytest config (testpaths=tests, addopts, log capture)
├── settings.json                    minimal example ({"settings": {"debug": false, "logLevel": "error"}})
├── CLAUDE.md                        __mission__ placeholder + coding style/logging/task-workflow rules from this repo
├── .vscode/
│   ├── launch.json                  genericized: CLI run (module __package_name__.cli, no
│   │                                 project-specific args) + pytest run; no designer/scratch
│   │                                 configs (not part of the generic template)
│   ├── settings.json                copied as-is (already generic: pytest paths, ./src extraPaths)
│   └── tasks.json                   copied as-is (already generic: venv create/build/install/
│                                     test/lint/format/zap/publish)
├── .github/workflows/ci.yaml        copied as-is (already generic)
├── .github/workflows/cd.yaml        copied as-is (already generic)
├── docs/ARCHITECTURE.md             skeleton headers only
├── docs/PROTOCOL.md                 skeleton headers only
├── tasks/repo_setup.md              placeholder list + replace instructions, referenced from CLAUDE.md's New Task section, deleted once done
├── src/__package_name__/
│   ├── __init__.py
│   ├── cli.py                       minimal argparse entrypoint (load Settings, wire ConsoleLogSink, exit codes) — no invented business logic
│   ├── errors.py                    telemetry_session, AppError, one example subclass
│   ├── settings.py                  settings.json + settings.local.json loader (debug, logging level, log_categories, excluded_categories only)
│   ├── diagnostics.py               Logger/TelemetryLevel/sinks, CATEGORY_GENERAL only
│   ├── contracts.py                 stub — docstring convention marker only (no fake generic Task/Worker/Provider protocols; that vocabulary is pipeline-specific to geo-builder)
│   └── protocols.py                 stub — docstring convention marker only
└── tests/unit/test_placeholder.py   trivial sanity test so pytest passes out of the box
```

Notes vs. the original base-module list: `result.py` dropped (geo-builder's version is a
one-off `Result(catalog: Catalog)` tied to `Catalog`, nothing generic to extract). No sibling
`tests/integration/` scaffolded yet — add it later if a real need shows up.

## Test results

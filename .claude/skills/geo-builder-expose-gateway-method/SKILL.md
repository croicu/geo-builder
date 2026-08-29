---
name: geo-builder-expose-gateway-method
description: Use when adding a new method or event to geo-builder's design-mode gateway — the Python↔JavaScript message bridge that lets an embedded geo-browser (?design=1) call into geo-builder and receive events back. Triggers on requests like "add a new designer API", "expose a method to geo-browser", "let the browser call/edit X", "add a gateway event". Encodes the exact multi-file procedure (api.py, designer/host.py, docs/MESSAGING.md) and the MethodResult/error-code conventions that are easy to miss or apply inconsistently.
---

# Exposing a gateway method or event

geo-builder's design mode embeds geo-browser in a WebView and exposes a small bidirectional
message API (see `docs/MESSAGING.md` for the wire protocol). There are two directions, and they
are not symmetric — pick the right one before writing any code:

- **Method** (browser → builder): JS calls Python, entry point `window.geo.invoke`. Use this when
  geo-browser needs to ask geo-builder to do something or fetch something.
- **Event** (builder → browser): Python calls JS, entry point `window.__geo_dispatch`. Use this
  when geo-builder needs to push a change to the browser without being asked.

Both directions are defined once in `src/geo_builder/api.py` and mirrored 1:1 into geo-browser's
`src/api.ts` — that mirroring is a separate skill (`geo-browser-call-gateway-method`) owned by the
other repo. This skill only covers the geo-builder side: defining the contract and implementing
the handler.

## 1. Define the contract in `api.py`

`api.py`'s own header comment states the rule: *"Only plain dataclasses with primitive / list /
dict fields belong here."* No methods, no imports of internal types — this file is a pure data
contract that gets transcribed into TypeScript by hand.

For a **method**, add:

```python
@dataclass
class RemoveUserPointInput:
    areaId: str
    lon: float
    lat: float


@dataclass
class RemoveUserPointOutput:
    error: int
    errorDescription: str | None = None
    # payload fields go after error/errorDescription, and must be Optional
    # (None on error) since the browser sees this same shape either way


REMOVE_USER_POINT_ID = "__geo_remove_user_point__"
```

Rules that aren't optional:

- Every `*Output` dataclass starts with `error: int` then `errorDescription: str | None = None`,
  in that order, before any payload fields. This is the API Response Contract in
  `docs/MESSAGING.md` — the TypeScript side is written to expect exactly this shape.
- The id constant is `<SCREAMING_SNAKE>_ID = "__geo_<lower_snake>__"` — double-underscore wrapped,
  no exceptions. geo-browser's `api.ts` must use this exact string, byte for byte; a mismatch is a
  silent runtime failure (message never routes), not a type error.

For an **event**, the payload dataclass has no `error`/`errorDescription` — it's not a
request/response pair:

```python
@dataclass
class AreaChangedData:
    area: AreaSummary


AREA_CHANGED_ID = "__geo_area_changed__"
```

**New error codes**: if the method needs a failure mode beyond the shared `OK = 0`, add the next
sequential integer to the error-code block at the top of `api.py` (alongside `ERR_AREA_NOT_FOUND`,
etc.). Never renumber or reuse an existing code — these integers are a wire contract, and
geo-browser's `api.ts` must be updated with the identical value in the same change.

## 2. Register the handler in `designer/host.py`

Everything is wired inside `_register_designer_handlers`. For a method:

```python
api.define_method(REMOVE_USER_POINT_ID, RemoveUserPointInput, RemoveUserPointOutput)

def on_remove_user_point(data: RemoveUserPointInput) -> RemoveUserPointOutput:
    area = ...  # look up whatever the handler needs
    if area is None:
        return MethodResult(RemoveUserPointOutput(error=ERR_AREA_NOT_FOUND, errorDescription=f"Area '{data.areaId}' not found"))

    # ... do the work ...

    return MethodResult(RemoveUserPointOutput(error=OK))

api.register(REMOVE_USER_POINT_ID, on_remove_user_point)
```

**`MethodResult(...)` wraps every return, success and error alike — never `return` a bare
dataclass.** This is `designer/host.py`'s own documented convention (see `docs/IMPLEMENTATION.md`'s
"Designer Handler Pattern"): `MethodResult` is the single exit path, and it logs a warning for any
non-`OK` result. A bare `return SomeOutput(error=OK)` isn't a type error — it silently bypasses
that logging, so a handler that "forgets" `MethodResult` on one branch fails invisibly.

For an event, there's no handler to register — declare it once during setup and fire it wherever
the underlying state actually changes:

```python
api.define_event(AREA_CHANGED_ID, AreaChangedData)
...
api.call(AREA_CHANGED_ID, AreaChangedData(area=area_summary))
```

**Threading**: handler code runs on the dispatcher thread automatically — `Gateway` routes every
inbound message and outbound call through its internal queue (see `docs/IMPLEMENTATION.md`'s
"Interactive Session — Threading Model"). Never spawn a separate thread to touch the catalog or
any shared model state from inside a handler; that reintroduces the race conditions the queue
exists to prevent.

## 3. Update `docs/MESSAGING.md`

Mandatory in the same change — geo-builder's own `CLAUDE.md` Documentation rule states this
explicitly for anything that affects `src/geo_builder/api.py`. `docs/MESSAGING.md` is what the
geo-browser side implements against; it drifting from `api.py` is exactly the kind of stale-doc
problem this skill exists to prevent elsewhere.

## Why this shape (not something simpler)

- **Capability-based, not schema-heavy.** geo-browser treats gateway responses as open/unknown
  JSON and only reads the fields it needs — there's no generated/enforced schema on either side.
  This is deliberate (see `README.md`'s Shared Contract Philosophy): the cost is deferred error
  detection, the benefit is no lockstep versioning between geo-builder and multiple future
  renderers (geo-ios, geo-desktop) that don't exist yet. Don't add schema validation to "fix" this.
- **`error`/`errorDescription` on every output, always in that position.** So the browser can
  always safely check `response.error` without knowing which method it called — a uniform contract
  is what lets the TypeScript side write one generic failure-handling pattern instead of one per
  method.

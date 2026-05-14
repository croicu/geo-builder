from __future__ import annotations


def layer_color(index: int) -> str:
    """Return the hex color for the nth layer within an area (0-based).

    Hue sequence starts at 240° (blue), steps by 120°, then interleaves
    at successively finer offsets (60°, 30°, 15°, …) so each new layer is
    as visually distinct as possible from the ones already assigned.

    index 0 → #0000ff  (240° blue)
    index 1 → #ff0000  (  0° red)
    index 2 → #00ff00  (120° green)
    index 3 → #ff00ff  (300° magenta)
    index 4 → #ffff00  ( 60° yellow)
    index 5 → #00ffff  (180° cyan)
    …
    """
    while len(_HUE_CACHE) <= index:
        _HUE_CACHE.append(next(_HUE_GEN))
    return _hue_to_hex(_HUE_CACHE[index])


def _hue_sequence():
    """Yields integer hues 0–359 in maximally-spread order, starting at 240."""
    step = 120
    base = 240
    seen: set[int] = set()

    for offset in _offsets(step):
        start = (base + offset) % 360
        for i in range(360 // step):
            h = (start + i * step) % 360
            if h not in seen:
                seen.add(h)
                yield h


def _offsets(step: int):
    """Yield offsets 0, then odd multiples of step/2, step/4, … within [0, step)."""
    seen: set[int] = {0}
    yield 0
    sub = step // 2
    while sub >= 1:
        for o in range(sub, step, sub * 2):
            if o not in seen:
                seen.add(o)
                yield o
        sub //= 2


def _hue_to_hex(hue: int) -> str:
    """Convert a hue (0–359, S=V=100%) to an #rrggbb hex string."""
    h = hue % 360
    sector = h // 60
    f = (h % 60) / 60.0

    if sector == 0:
        r, g, b = 1.0, f, 0.0
    elif sector == 1:
        r, g, b = 1.0 - f, 1.0, 0.0
    elif sector == 2:
        r, g, b = 0.0, 1.0, f
    elif sector == 3:
        r, g, b = 0.0, 1.0 - f, 1.0
    elif sector == 4:
        r, g, b = f, 0.0, 1.0
    else:
        r, g, b = 1.0, 0.0, 1.0 - f

    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


_HUE_GEN = _hue_sequence()
_HUE_CACHE: list[int] = []

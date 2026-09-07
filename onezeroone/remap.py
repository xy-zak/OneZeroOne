"""Linear value remapping with optional clamping."""

from __future__ import annotations


def remap(
    value: float,
    in_min: float,
    in_max: float,
    out_min: float,
    out_max: float,
    clamp: bool = True,
) -> float:
    """Map ``value`` from the [in_min, in_max] range to [out_min, out_max].

    If ``clamp`` is True the result is constrained to the output range.
    A degenerate input range (in_min == in_max) returns out_min.
    """
    if in_min == in_max:
        return out_min
    t = (value - in_min) / (in_max - in_min)
    result = out_min + t * (out_max - out_min)
    if clamp:
        lo, hi = (out_min, out_max) if out_min <= out_max else (out_max, out_min)
        if result < lo:
            result = lo
        elif result > hi:
            result = hi
    return result

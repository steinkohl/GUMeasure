"""Calibration logic: choice of certificate and interval, interpolation, drift, checks.

The functions on floats are shared by the evaluation and by the checks on load. All values of
a function are in the unit of that function.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

from pydantic import ConfigDict

from gumeasure.model import Calibration


@dataclass(frozen=True)
class Point:
    """A calibration point as floats in the unit of the function."""

    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    reference: float
    deviation: float
    U: float
    k: float
    deviation_as_found: float | None = None

    @property
    def as_found(self) -> float:
        return self.deviation if self.deviation_as_found is None else self.deviation_as_found

    @property
    def u(self) -> float:
        return self.U / self.k


def in_force(
    calibrations: Sequence[Calibration], day: date
) -> tuple[Calibration | None, Calibration | None]:
    """The latest certificate with date <= day, and the certificate before it."""
    valid = sorted((c for c in calibrations if c.date <= day), key=lambda c: c.date)
    if not valid:
        return None, None
    return valid[-1], (valid[-2] if len(valid) > 1 else None)


def column_days(interval_d: float) -> int:
    """Whole days that an interval of the data sheet covers.

    pint takes 1 year as 365.25 days. Rounding up lets "1 year" cover 366 days, so a
    calibration interval across 29 February falls in the 1-year column.
    """
    # TODO: check this (D10)
    return math.ceil(interval_d - 1e-9)


def interval_index(elapsed_days: int, intervals_d: Sequence[float]) -> tuple[int, bool]:
    """Column of the shortest interval that covers the elapsed days, and whether none does.

    Without intervals the single column holds until the calibration is due.
    """
    if not intervals_d:
        return 0, False
    for index, interval in enumerate(intervals_d):
        if elapsed_days <= column_days(interval):
            return index, False
    return len(intervals_d) - 1, True


def bracket(points: Sequence[Point], x: float) -> tuple[Point, Point] | None:
    """The two neighbouring points around x, or one point twice if x lies on it.

    None if x lies outside the calibrated span. The points must be sorted by reference.
    """
    for point in points:
        if math.isclose(point.reference, x, rel_tol=1e-12, abs_tol=0.0) or point.reference == x:
            return point, point
    for low, high in itertools.pairwise(points):
        if low.reference < x < high.reference:
            return low, high
    return None


def interpolate(low: Point, high: Point, x: float) -> float:
    """Deviation at x by linear interpolation between two points."""
    # D4: linear deviation between the neighbouring points.
    if low is high or low.reference == high.reference:
        return low.deviation
    t = (x - low.reference) / (high.reference - low.reference)
    return low.deviation + t * (high.deviation - low.deviation)


def drift_rates(
    current: Sequence[Point], previous: Sequence[Point], span_days: int
) -> list[tuple[float, float]]:
    """Drift rate per day for every reference point both certificates share.

    rate = (as-found deviation now − as-left deviation then) / days between the certificates.
    Returns pairs of reference and rate.
    """
    rates = []
    for now in current:
        for then in previous:
            if math.isclose(now.reference, then.reference, rel_tol=1e-9, abs_tol=0.0):
                rates.append((now.reference, (now.as_found - then.deviation) / span_days))
    return rates


def out_of_spec(deviation: float, half_width: float) -> bool:
    """True if a deviation exceeds the half-width of the data sheet."""
    return abs(deviation) > half_width * (1 + 1e-12)

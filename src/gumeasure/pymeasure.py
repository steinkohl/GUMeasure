"""Binding to PyMeasure instruments.

The Reader reads a property of a PyMeasure instrument or channel n times and evaluates the
series. It only reads properties and never controls the instrument. PyMeasure is not imported
at run time. Install the extra `gumeasure[pymeasure]` for a tested PyMeasure version.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from gumeasure import units
from gumeasure.errors import UsageError
from gumeasure.model import Instrument, Measurement
from gumeasure.units import Quantity


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Series:
    """The result of Reader.measure: the Measurement and the raw readings with their times."""

    measurement: Measurement
    readings: Quantity
    times: tuple[datetime, ...]


@dataclass
class Reader:
    instrument: Instrument
    function: str
    obj: Any
    prop: str
    range: Quantity | str | None = None
    range_prop: str | None = None
    # TODO: check this (D17). Plain floats are taken in the unit of the function.
    unit: str | None = None
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        self.instrument.datasheet.function(self.function)
        if self.range is not None and self.range_prop is not None:
            raise UsageError("give range or range_prop, not both")

    def measure(
        self,
        n: int = 1,
        interval: Quantity | str = "0 s",
        at: datetime | None = None,
        temperature: Quantity | str | None = None,
    ) -> Series:
        """Read the property n times, `interval` apart, and evaluate the series."""
        if n < 1:
            raise UsageError("n must be 1 or more")
        spacing = units.seconds(units.parse_quantity(interval))
        unit = self.unit or self.instrument.datasheet.function(self.function).unit
        times: list[datetime] = []
        magnitudes: list[float] = []
        for i in range(n):
            start = self.clock()
            times.append(start)
            value = getattr(self.obj, self.prop)
            magnitudes.append(_magnitude(value, unit))
            if i < n - 1 and spacing > 0:
                rest = spacing - (self.clock() - start).total_seconds()
                if rest > 0:
                    self.sleep(rest)
        range_: Quantity | str | None = self.range
        if self.range_prop is not None:
            # TODO: check this (D18). Read once, after the last reading of the series.
            raw = getattr(self.obj, self.range_prop)
            fn_unit = self.instrument.datasheet.function(self.function).unit
            range_ = raw if units.is_quantity(raw) else units.make(float(raw), fn_unit)
        readings = units.make(magnitudes, unit)
        measurement = self.instrument.evaluate(
            self.function,
            readings,
            range=range_,
            at=at if at is not None else times[0],
            temperature=temperature,
        )
        return Series(measurement=measurement, readings=readings, times=tuple(times))


def _magnitude(value: Any, unit: str) -> float:
    if units.is_quantity(value):
        return units.magnitude(value, unit)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise UsageError(f"the property returned {value!r}, not a number") from None

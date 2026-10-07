"""The evaluation: readings and inputs in, Measurement out.

`evaluate` is a pure function. It reads no clock and no files. Everything it uses is in its
arguments. The same readings and inputs always give an equal Measurement.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from gumeasure import units
from gumeasure.calibration import (
    Point,
    bracket,
    drift_rates,
    interpolate,
    interval_index,
    out_of_spec,
)
from gumeasure.errors import UsageError
from gumeasure.inputs import CalibrationRecord, Inputs, from_json, to_json
from gumeasure.model import (
    Contribution,
    Datasheet,
    Issue,
    IssueCode,
    Measurement,
    linear_half_width,
)
from gumeasure.units import Quantity

#: D6: coverage factor, always 2. No effective degrees of freedom yet.
K = 2.0
_SQRT3 = math.sqrt(3.0)


def evaluate(
    readings: Quantity, inputs: Mapping[str, Any], *, datasheet: Datasheet | None = None
) -> Measurement:
    """Measurement of one series of readings from the inputs snapshot.

    `datasheet` is needed only for a custom data sheet, whose half-width is code.
    """
    record = from_json(inputs)
    values = _values(readings, record.unit)
    half_width = _half_width_function(record, datasheet)
    return _Evaluation(record, values, half_width).run()


def recompute(
    record: Mapping[str, Any], readings: Quantity, *, datasheet: Datasheet | None = None
) -> Measurement:
    """Measurement from a record of Measurement.to_dict() and the readings of that record.

    The stored value, budget and issues are not read. They are computed again.
    """
    if not isinstance(record, Mapping) or "inputs" not in record:
        raise UsageError("record must be the output of Measurement.to_dict()")
    inputs = record["inputs"]
    if datasheet is None and inputs.get("datasheet", {}).get("custom"):
        datasheet = _resolve_custom(inputs)
    return evaluate(readings, inputs, datasheet=datasheet)


def _resolve_custom(inputs: Mapping[str, Any]) -> Datasheet:
    from gumeasure.registry import datasheet as load

    origin = inputs["datasheet"].get("origin")
    if not origin or origin.get("kind") not in ("builtin", "entry-point"):
        raise UsageError("custom data sheet without a registry name. Pass datasheet=.")
    ds = load(origin["name"])
    installed = ds.origin.version if ds.origin else None
    if installed != origin.get("version"):
        raise UsageError(
            f"custom data sheet {origin['name']} was version {origin.get('version')}, "
            f"installed is {installed}. Pass datasheet= to accept the installed one."
        )
    return ds


def _values(readings: Quantity, unit: str) -> list[float]:
    if not units.is_quantity(readings):
        raise UsageError(f"readings must be a quantity with a unit of {unit}")
    if not units.same_dimension(readings, unit):
        raise UsageError(f"readings must have the dimension of {unit}, got {readings.units}")
    array = np.atleast_1d(np.asarray(readings.to(unit).magnitude, dtype=float)).ravel()
    if array.size == 0:
        raise UsageError("readings are empty")
    if not np.all(np.isfinite(array)):
        raise UsageError("readings must be finite numbers")
    return [float(v) for v in array]


HalfWidth = Callable[[int, float], float]


def _half_width_function(record: Inputs, datasheet: Datasheet | None) -> HalfWidth:
    rng = record.datasheet.range
    if not record.datasheet.custom:

        def linear(column: int, x: float) -> float:
            a = rng.accuracy[column]
            return linear_half_width(
                a.of_reading, a.of_range, a.offset, a.counts, x, rng.full_scale, rng.resolution
            )

        return linear
    if datasheet is None:
        raise UsageError(
            f"data sheet {record.datasheet.model} is custom. Pass datasheet= to evaluate."
        )
    custom_ds = datasheet
    domain_range = custom_ds.range(record.function, units.make(rng.full_scale, record.unit))

    def custom(column: int, x: float) -> float:
        value = custom_ds.half_width(
            record.function, domain_range, units.make(x, record.unit), column
        )
        return units.magnitude(value, record.unit)

    return custom


@dataclass
class _Evaluation:
    record: Inputs
    values: list[float]
    half_width: HalfWidth
    budget: list[Contribution] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    # helpers ----------------------------------------------------------------------------

    def issue(self, code: IssueCode, message: str) -> None:
        self.issues.append(Issue.of(code, message))

    def add(self, name: str, u: float, type_: str, distribution: str, source: str) -> None:
        self.budget.append(Contribution(name, u, type_, distribution, source))

    def fmt(self, value: float) -> str:
        return units.fmt(value, self.record.unit)

    def column_name(self, column: int) -> str:
        names = self.record.datasheet.intervals
        return f"{names[column]} column" if names else "single accuracy column"

    # steps ------------------------------------------------------------------------------

    def run(self) -> Measurement:
        r = self.record
        ds = r.datasheet
        rng = ds.range
        intervals = ds.intervals_d
        cal = r.calibration
        day = r.at.date()  # TODO: check this (D9). Whole days, in the time zone of `at`.

        # 1. Calibration in force, and the check before use.
        elapsed: int | None = None
        column = max(len(intervals) - 1, 0)
        mode = r.mode
        if cal is None:
            self.issue(
                "calibration-missing",
                f"No calibration of {ds.model} {r.serial} on or before {day.isoformat()}.",
            )
            # TODO: check this (D11). Data sheet with its longest column.
            mode = "datasheet"
        else:
            if day > cal.due:
                self.issue(
                    "calibration-expired",
                    f"Certificate {cal.certificate} was due on {cal.due.isoformat()}.",
                )
            self.check_certificate(cal)
            # 2. Interval.
            elapsed = (day - cal.date).days
            column, exceeded = interval_index(elapsed, intervals)
            if exceeded:
                self.issue(
                    "interval-exceeded",
                    f"{elapsed} days since calibration exceed the longest interval of the "
                    f"data sheet, {ds.intervals[-1]}. The {ds.intervals[-1]} column is used.",
                )

        # 3. Range.
        top = max(abs(v) for v in self.values)
        if top > rng.full_scale * (1 + 1e-12):
            self.issue(
                "overrange",
                f"A reading of {self.fmt(top)} is above the full scale {self.fmt(rng.full_scale)}.",
            )

        # 4. Mean.
        x = statistics.fmean(self.values)
        n = len(self.values)

        # 5. Type A.
        if n >= 2:
            s = statistics.stdev(self.values)
            self.add(
                "repeatability",
                s / math.sqrt(n),
                "A",
                "normal",
                f"standard deviation of the mean of {n} readings",
            )
        else:
            self.issue("single-reading", "One reading. No Type A contribution.")

        # 6. Resolution. D7: added only where the accuracy does not cover it.
        if not rng.resolution_included:
            self.add(
                "resolution",
                rng.resolution / (2 * _SQRT3),
                "B",
                "rectangular",
                f"resolution {self.fmt(rng.resolution)} of the "
                f"{self.fmt(rng.full_scale)} range, data sheet {ds.model}",
            )

        # 7. Temperature.
        self.temperature(x)

        # 8. to 12.
        value = x
        if mode == "calibration":
            assert cal is not None and elapsed is not None
            pair = bracket(cal.points, x)
            if pair is None:
                span = (
                    f"between {self.fmt(cal.points[0].reference)} and "
                    f"{self.fmt(cal.points[-1].reference)}"
                    if cal.points
                    else "at no point of this function and range"
                )
                # D3, and TODO: check this (D12) for a certificate without points.
                self.issue(
                    "extrapolated",
                    f"The mean {self.fmt(x)} lies outside the points of certificate "
                    f"{cal.certificate}, which are {span}. Evaluated from the data sheet.",
                )
                mode = "datasheet"
            else:
                value = self.mode_b(cal, pair, x, column, elapsed)
        if mode == "datasheet":
            a = self.half_width(column, x)
            self.add(
                "accuracy",
                a / _SQRT3,
                "B",
                "rectangular",
                f"data sheet {ds.model}, {self.column_name(column)}",
            )

        # D5: no correlation between the contributions.
        u = math.sqrt(math.fsum(c.u * c.u for c in self.budget))
        return Measurement(
            value=value,
            unit=r.unit,
            u=u,
            k=K,
            budget=tuple(self.budget),
            issues=tuple(self.issues),
            inputs=to_json(r),
        )

    def check_certificate(self, cal: CalibrationRecord) -> None:
        """Every point of the certificate in force must lie within the data sheet."""
        ds = self.record.datasheet
        column, _ = interval_index((cal.due - cal.date).days, ds.intervals_d)
        for point in cal.points:
            a = self.half_width(column, point.reference)
            # TODO: check this (D19). The as-left deviation holds for readings after the
            # certificate. An as-found deviation out of specification is reported by
            # Instrument.check() and gumeasure check.
            if out_of_spec(point.deviation, a):
                self.issue(
                    "certificate-out-of-spec",
                    f"Certificate {cal.certificate}, {self.record.function}, "
                    f"{self.fmt(ds.range.full_scale)} range, {self.fmt(point.reference)}: "
                    f"deviation {self.fmt(point.deviation)} exceeds the data sheet half-width "
                    f"{self.fmt(a)} ({self.column_name(column)}).",
                )

    def temperature(self, x: float) -> None:
        r = self.record
        ds = r.datasheet
        if r.temperature_degC is None:
            # D8: assumed within the band.
            self.issue(
                "temperature-assumed",
                f"Temperature not given. Assumed within {ds.tcal_degC:g} ± {ds.band_K:g} °C.",
            )
            return
        # TODO: check this (D21). The data sheet tcal holds in both modes.
        outside = abs(r.temperature_degC - ds.tcal_degC) - ds.band_K
        if outside <= 0:
            return
        tempco = ds.range.tempco
        if tempco is None:
            # TODO: check this (D22)
            self.issue(
                "tempco-unknown",
                f"{r.temperature_degC:g} °C is {outside:g} K outside {ds.tcal_degC:g} ± "
                f"{ds.band_K:g} °C and the data sheet gives no temperature coefficient.",
            )
            return
        per_kelvin = linear_half_width(
            tempco.of_reading,
            tempco.of_range,
            tempco.offset,
            tempco.counts,
            x,
            ds.range.full_scale,
            ds.range.resolution,
        )
        self.add(
            "temperature",
            per_kelvin * outside / _SQRT3,
            "B",
            "rectangular",
            f"temperature coefficient of data sheet {ds.model}, {r.temperature_degC:g} °C is "
            f"{outside:g} K outside {ds.tcal_degC:g} ± {ds.band_K:g} °C",
        )

    def mode_b(
        self,
        cal: CalibrationRecord,
        pair: tuple[Point, Point],
        x: float,
        column: int,
        elapsed: int,
    ) -> float:
        r = self.record
        ds = r.datasheet
        low, high = pair

        # 9. Correction.
        deviation = interpolate(low, high, x)
        where = (
            f"at the point {self.fmt(low.reference)}"
            if low is high
            else f"interpolated between {self.fmt(low.reference)} and {self.fmt(high.reference)}"
        )

        # 10. Calibration. D4: U/k of the larger neighbour.
        u_cal = max(low.u, high.u)
        self.add(
            "calibration",
            u_cal,
            "B",
            "normal",
            f"certificate {cal.certificate} of {cal.laboratory}, deviation "
            f"{self.fmt(deviation)} {where}",
        )

        # 11. Short-term accuracy. D1, and TODO: check this (D20): only with two or more
        # intervals, because a single column already contains the drift.
        if len(ds.intervals_d) >= 2:
            a0 = self.half_width(0, x)
            self.add(
                "short-term accuracy",
                a0 / _SQRT3,
                "B",
                "rectangular",
                f"data sheet {ds.model}, {self.column_name(0)}",
            )

        # 12. Drift since calibration.
        if r.drift == "datasheet":
            if len(ds.intervals_d) < 2:
                self.issue(
                    "drift-unknown",
                    f"Drift from the data sheet needs two intervals or more. "
                    f"Data sheet {ds.model} has {len(ds.intervals_d)}.",
                )
            else:
                # D2: a(interval) − a(shortest interval).
                a = self.half_width(column, x) - self.half_width(0, x)
                self.add(
                    "drift since calibration",
                    a / _SQRT3,
                    "B",
                    "rectangular",
                    f"data sheet {ds.model}, {ds.intervals[column]} column minus "
                    f"{ds.intervals[0]} column, {elapsed} days since calibration",
                )
        elif r.drift == "history":
            self.history_drift(cal, elapsed)
        else:
            self.issue(
                "drift-unknown",
                f"No drift source configured for {r.function} in calibration mode.",
            )
        return x - deviation

    def history_drift(self, cal: CalibrationRecord, elapsed: int) -> None:
        previous = self.record.previous
        if previous is None:
            self.issue(
                "drift-unknown",
                f"Drift from history needs a certificate before {cal.certificate}.",
            )
            return
        span = (cal.date - previous.date).days
        rates = drift_rates(cal.points, previous.points, span)
        if not rates:
            self.issue(
                "drift-unknown",
                f"Certificates {previous.certificate} and {cal.certificate} share no "
                "calibration point of this function and range.",
            )
            return
        rate = max(abs(rate) for _, rate in rates)
        self.add(
            "drift since calibration",
            rate * elapsed / _SQRT3,
            "B",
            "rectangular",
            f"certificates {previous.certificate} and {cal.certificate}, largest drift "
            f"{self.fmt(rate)} per day over {span} days, {elapsed} days since calibration",
        )

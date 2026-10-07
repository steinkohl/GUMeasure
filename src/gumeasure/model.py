"""Data model of gumeasure.

All classes are frozen standard library dataclasses. Quantities are pint quantities of the
application registry. Percent and ppm values are dimensionless fractions.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, get_args

from gumeasure import units
from gumeasure.errors import ModelError, UsageError
from gumeasure.units import Quantity

Mode = Literal["datasheet", "calibration"]
DriftSource = Literal["datasheet", "history"]
Severity = Literal["error", "note"]
IssueCode = Literal[
    "calibration-missing",
    "calibration-expired",
    "certificate-out-of-spec",
    "drift-unknown",
    "overrange",
    "interval-exceeded",
    "tempco-unknown",
    "extrapolated",
    "temperature-assumed",
    "single-reading",
]
ContributionType = Literal["A", "B"]
Distribution = Literal["normal", "rectangular"]

MODES: tuple[str, ...] = get_args(Mode)
DRIFT_SOURCES: tuple[str, ...] = get_args(DriftSource)

#: Severity of every issue code. The only place where severities live.
SEVERITY: Mapping[str, Severity] = MappingProxyType(
    {
        "calibration-missing": "error",
        "calibration-expired": "error",
        "certificate-out-of-spec": "error",
        "drift-unknown": "error",
        "overrange": "error",
        "interval-exceeded": "error",
        # TODO: check this (D22). Not in the issue table of the design.
        "tempco-unknown": "error",
        "extrapolated": "note",
        "temperature-assumed": "note",
        "single-reading": "note",
    }
)


def linear_half_width(
    of_reading: float,
    of_range: float,
    offset: float,
    counts: int,
    x: float,
    full_scale: float,
    resolution: float,
) -> float:
    """Half-width a = of_reading·|x| + of_range·full_scale + offset + counts·resolution.

    All values in the unit of the function. The terms are summed in this order on every path,
    so every caller gets the same float.
    """
    return of_reading * abs(x) + of_range * full_scale + offset + counts * resolution


# --------------------------------------------------------------------------------------------
# Data sheet


@dataclass(frozen=True)
class Origin:
    """Where a data sheet or a calibration was loaded from."""

    name: str
    kind: Literal["builtin", "entry-point", "file", "object"]
    version: str | None = None
    sha256: str | None = None


@dataclass(frozen=True)
class Accuracy:
    """Half-width a = of_reading·|x| + of_range·full_scale + offset + counts·resolution."""

    of_reading: float = 0.0
    of_range: float = 0.0
    offset: Quantity | None = None
    counts: int = 0

    def values(self, unit: str) -> tuple[float, float, float, int]:
        """The four terms as floats, the offset in the given unit."""
        offset = 0.0 if self.offset is None else units.magnitude(self.offset, unit)
        return self.of_reading, self.of_range, offset, self.counts

    def half_width(self, x: Quantity, full_scale: Quantity, resolution: Quantity) -> Quantity:
        """Half-width at the reading x, in the unit of the full scale."""
        unit = str(full_scale.units)
        value = linear_half_width(
            *self.values(unit),
            units.magnitude(x, unit),
            units.magnitude(full_scale, unit),
            units.magnitude(resolution, unit),
        )
        return units.make(value, unit)


@dataclass(frozen=True)
class Range:
    full_scale: Quantity
    resolution: Quantity
    resolution_included: bool
    accuracy: tuple[Accuracy, ...]
    tempco: Accuracy | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "accuracy", tuple(self.accuracy))


@dataclass(frozen=True)
class Function:
    unit: str
    ranges: tuple[Range, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ranges", tuple(self.ranges))


@dataclass(frozen=True)
class Check:
    """Worked example of a data sheet, checked by `gumeasure check` and in the tests."""

    function: str
    range: Quantity
    reading: Quantity
    interval: Quantity | None
    half_width: Quantity


@dataclass(frozen=True)
class Datasheet:
    model: str
    vendor: str
    source: str
    tcal: Quantity
    band: Quantity
    intervals: tuple[Quantity, ...]
    functions: Mapping[str, Function]
    checks: tuple[Check, ...] = ()
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "intervals", tuple(self.intervals))
        object.__setattr__(self, "functions", MappingProxyType(dict(self.functions)))
        object.__setattr__(self, "checks", tuple(self.checks))
        problems = validate_datasheet(self)
        if problems:
            raise ModelError(f"data sheet {self.model}", problems)

    def half_width(
        self, function: str, range_: Range, reading: Quantity, interval_index: int
    ) -> Quantity:
        """Half-width of the accuracy at the reading, in the unit of the function.

        Subclasses override this for instruments that fit no linear form.
        """
        unit = self.function(function).unit
        value = linear_half_width(
            *range_.accuracy[interval_index].values(unit),
            units.magnitude(reading, unit),
            units.magnitude(range_.full_scale, unit),
            units.magnitude(range_.resolution, unit),
        )
        return units.make(value, unit)

    @property
    def custom(self) -> bool:
        """True if a subclass overrides half_width."""
        return type(self).half_width is not Datasheet.half_width

    def function(self, name: str) -> Function:
        try:
            return self.functions[name]
        except KeyError:
            known = ", ".join(sorted(self.functions))
            raise UsageError(
                f"data sheet {self.model} has no function {name!r}. Known: {known}"
            ) from None

    def range(self, function: str, full_scale: Quantity | str | None) -> Range:
        """The range of a function with this full scale, or the only range."""
        fn = self.function(function)
        if full_scale is None:
            if len(fn.ranges) == 1:
                return fn.ranges[0]
            raise UsageError(
                f"function {function!r} of {self.model} has {len(fn.ranges)} ranges. "
                "Give the range."
            )
        value = _as_quantity(full_scale, fn.unit, "range")
        target = units.magnitude(value, fn.unit)
        for range_ in fn.ranges:
            if units.close(units.magnitude(range_.full_scale, fn.unit), target):
                return range_
        known = ", ".join(units.plain(r.full_scale) for r in fn.ranges)
        raise UsageError(
            f"function {function!r} of {self.model} has no range {units.plain(value)}. "
            f"Known: {known}"
        )

    def interval_index(self, interval: Quantity | None) -> int:
        """Index of an interval of the data sheet. None for a data sheet without intervals."""
        if interval is None:
            if self.intervals:
                raise UsageError(f"data sheet {self.model} has intervals. Give the interval.")
            return 0
        for index, known in enumerate(self.intervals):
            if known.dimensionality == interval.dimensionality and units.close(
                units.days(known), units.days(interval)
            ):
                return index
        raise UsageError(f"data sheet {self.model} has no interval {units.plain(interval)}")

    def tempco_half_width(self, function: str, range_: Range, reading: Quantity) -> Quantity | None:
        """Half-width of the temperature coefficient per kelvin, or None."""
        if range_.tempco is None:
            return None
        unit = self.function(function).unit
        value = linear_half_width(
            *range_.tempco.values(unit),
            units.magnitude(reading, unit),
            units.magnitude(range_.full_scale, unit),
            units.magnitude(range_.resolution, unit),
        )
        return units.make(value, unit)


def interval_name(interval: Quantity) -> str:
    """Name of an interval for messages, such as '1 year' or '24 hour'."""
    return f"{interval.magnitude:g} {interval.units}"


def validate_datasheet(ds: Datasheet) -> list[tuple[str, str]]:
    """All problems of a data sheet, as pairs of key path and message."""
    problems: list[tuple[str, str]] = []

    def need(ok: bool, key: str, message: str) -> bool:
        if not ok:
            problems.append((key, message))
        return ok

    if need(units.is_quantity(ds.tcal), "tcal", "must be a quantity") and need(
        units.same_dimension(ds.tcal, "kelvin"), "tcal", "must be a temperature"
    ):
        pass
    if (
        need(units.is_quantity(ds.band), "band", "must be a quantity")
        and need(units.same_dimension(ds.band, "kelvin"), "band", "must be a temperature")
        and need(not units.is_offset(ds.band), "band", "a temperature difference needs K")
    ):
        need(units.difference_kelvin(ds.band) >= 0, "band", "must not be negative")
    previous = 0.0
    for i, interval in enumerate(ds.intervals):
        key = f"intervals[{i}]"
        if need(units.is_quantity(interval), key, "must be a quantity") and need(
            units.same_dimension(interval, "day"), key, "must be a time"
        ):
            value = units.days(interval)
            need(value > previous, key, "intervals must be positive and strictly rising")
            previous = value
    columns = max(1, len(ds.intervals))
    need(bool(ds.functions), "function", "a data sheet needs at least one function")
    for name, fn in ds.functions.items():
        base = f"function.{_key(name)}"
        try:
            units.units_of(fn.unit)
        except ValueError as err:
            problems.append((f"{base}.unit", str(err)))
            continue
        need(bool(fn.ranges), f"{base}.range", "a function needs at least one range")
        last = -math.inf
        for j, range_ in enumerate(fn.ranges):
            rkey = f"{base}.range[{j}]"
            if _dimension(problems, range_.full_scale, fn.unit, f"{rkey}.full_scale"):
                fs = units.magnitude(range_.full_scale, fn.unit)
                need(fs > 0, f"{rkey}.full_scale", "must be positive")
                need(fs > last, f"{rkey}.full_scale", "ranges must be sorted by full scale")
                last = fs
            if _dimension(problems, range_.resolution, fn.unit, f"{rkey}.resolution"):
                need(
                    units.magnitude(range_.resolution, fn.unit) > 0,
                    f"{rkey}.resolution",
                    "must be positive",
                )
            need(
                len(range_.accuracy) == columns,
                f"{rkey}.accuracy",
                f"needs {columns} entries, one per interval, got {len(range_.accuracy)}",
            )
            for k, acc in enumerate(range_.accuracy):
                _accuracy(problems, acc, fn.unit, f"{rkey}.accuracy[{k}]")
            if range_.tempco is not None:
                _accuracy(problems, range_.tempco, fn.unit, f"{rkey}.tempco")
    for i, check in enumerate(ds.checks):
        key = f"check[{i}]"
        fn_ = ds.functions.get(check.function)
        if not need(fn_ is not None, f"{key}.function", f"unknown function {check.function!r}"):
            continue
        assert fn_ is not None
        for attr in ("range", "reading", "half_width"):
            _dimension(problems, getattr(check, attr), fn_.unit, f"{key}.{attr}")
        if ds.intervals:
            need(check.interval is not None, f"{key}.interval", "the data sheet has intervals")
        else:
            need(check.interval is None, f"{key}.interval", "the data sheet has no intervals")
        if not problems:
            try:
                ds.range(check.function, check.range)
            except UsageError as err:
                problems.append((f"{key}.range", str(err)))
            try:
                ds.interval_index(check.interval)
            except UsageError as err:
                problems.append((f"{key}.interval", str(err)))
    return problems


def _key(name: str) -> str:
    return name if name.replace("_", "").replace("-", "").isalnum() else f'"{name}"'


def _dimension(problems: list[tuple[str, str]], value: object, unit: str, key: str) -> bool:
    if not units.is_quantity(value):
        problems.append((key, "must be a quantity"))
        return False
    assert units.is_quantity(value)
    if not units.same_dimension(value, unit):
        problems.append((key, f"must have the dimension of {unit}, got {units.plain(value)}"))
        return False
    return True


def _accuracy(problems: list[tuple[str, str]], acc: Accuracy, unit: str, key: str) -> None:
    for attr in ("of_reading", "of_range"):
        value = getattr(acc, attr)
        if not isinstance(value, float | int) or value < 0:
            problems.append((f"{key}.{attr}", "must be a fraction of zero or more"))
    if not isinstance(acc.counts, int) or acc.counts < 0:
        problems.append((f"{key}.counts", "must be a whole number of zero or more"))
    if (
        acc.offset is not None
        and _dimension(problems, acc.offset, unit, f"{key}.offset")
        and units.magnitude(acc.offset, unit) < 0
    ):
        problems.append((f"{key}.offset", "must not be negative"))


def _as_quantity(value: Quantity | str | float, unit: str, what: str) -> Quantity:
    if isinstance(value, str):
        try:
            value = units.parse_quantity(value)
        except ValueError as err:
            raise UsageError(f"{what}: {err}") from None
    if not units.is_quantity(value):
        raise UsageError(f"{what} must be a quantity with a unit, got {value!r}")
    assert units.is_quantity(value)
    if not units.same_dimension(value, unit):
        raise UsageError(f"{what} must have the dimension of {unit}, got {units.plain(value)}")
    return value


def check_results(ds: Datasheet) -> list[tuple[int, Check, Quantity, bool]]:
    """Every worked example of a data sheet with the computed half-width and the outcome."""
    results = []
    for i, check in enumerate(ds.checks):
        unit = ds.function(check.function).unit
        got = ds.half_width(
            check.function,
            ds.range(check.function, check.range),
            check.reading,
            ds.interval_index(check.interval),
        )
        ok = units.close(units.magnitude(got, unit), units.magnitude(check.half_width, unit))
        results.append((i, check, got, ok))
    return results


# --------------------------------------------------------------------------------------------
# Calibration


@dataclass(frozen=True)
class CalPoint:
    function: str
    range: Quantity
    reference: Quantity
    deviation: Quantity
    U: Quantity
    k: float
    deviation_as_found: Quantity | None = None

    @property
    def as_found(self) -> Quantity:
        """The deviation before any adjustment."""
        return self.deviation if self.deviation_as_found is None else self.deviation_as_found


@dataclass(frozen=True)
class Calibration:
    model: str
    serial: str
    certificate: str
    laboratory: str
    accredited: bool
    date: dt.date
    due: dt.date
    temperature: Quantity | None
    points: tuple[CalPoint, ...] = ()
    origin: Origin | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", tuple(self.points))
        problems: list[tuple[str, str]] = []
        if self.due <= self.date:
            problems.append(("due", "must be after date"))
        if self.temperature is not None and not (
            units.is_quantity(self.temperature) and units.same_dimension(self.temperature, "kelvin")
        ):
            problems.append(("temperature", "must be a temperature"))
        seen: dict[tuple[str, float, float], int] = {}
        for i, point in enumerate(self.points):
            if point.k <= 0:
                problems.append((f"point[{i}].k", "must be positive"))
            try:
                ident = (
                    point.function,
                    float(point.range.to_base_units().magnitude),
                    float(point.reference.to_base_units().magnitude),
                )
            except Exception:
                problems.append((f"point[{i}]", "range and reference must be quantities"))
                continue
            if ident in seen:
                problems.append(
                    (f"point[{i}]", f"same function, range and reference as point[{seen[ident]}]")
                )
            seen[ident] = i
        if problems:
            raise ModelError(f"certificate {self.certificate}", problems)

    def points_of(self, function: str, full_scale: Quantity, unit: str) -> list[CalPoint]:
        """Points of this function and range, sorted by reference."""
        target = units.magnitude(full_scale, unit)
        found = [
            p
            for p in self.points
            if p.function == function and units.close(units.magnitude(p.range, unit), target)
        ]
        return sorted(found, key=lambda p: units.magnitude(p.reference, unit))


# --------------------------------------------------------------------------------------------
# Instrument


@dataclass(frozen=True)
class Instrument:
    datasheet: Datasheet
    serial: str
    calibrations: tuple[Calibration, ...]
    modes: Mapping[str, str]
    drift: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ds = self.datasheet
        cals = tuple(sorted(self.calibrations, key=lambda c: c.date))
        object.__setattr__(self, "calibrations", cals)
        object.__setattr__(self, "modes", MappingProxyType(dict(self.modes)))
        object.__setattr__(self, "drift", MappingProxyType(dict(self.drift)))
        for cal in cals:
            if cal.model != ds.model:
                raise UsageError(
                    f"certificate {cal.certificate} is for model {cal.model}, "
                    f"the data sheet for {ds.model}"
                )
            if cal.serial != self.serial:
                raise UsageError(
                    f"certificate {cal.certificate} is for serial {cal.serial}, "
                    f"the instrument has {self.serial}"
                )
            for i, point in enumerate(cal.points):
                fn = ds.functions.get(point.function)
                if fn is None:
                    raise UsageError(
                        f"certificate {cal.certificate}, point[{i}]: "
                        f"unknown function {point.function!r}"
                    )
                for attr in ("range", "reference", "deviation", "U"):
                    _as_quantity(
                        getattr(point, attr), fn.unit, f"certificate {cal.certificate}, {attr}"
                    )
                if point.deviation_as_found is not None:
                    _as_quantity(point.deviation_as_found, fn.unit, "deviation_as_found")
                ds.range(point.function, point.range)
        dates = [c.date for c in cals]
        if len(set(dates)) != len(dates):
            # TODO: check this (D16)
            raise UsageError(f"two certificates of {self.serial} share a date")
        for name, mode in self.modes.items():
            ds.function(name)
            if mode not in MODES:
                raise UsageError(f"mode of {name!r} must be one of {MODES}, got {mode!r}")
        for name, source in self.drift.items():
            ds.function(name)
            if source not in DRIFT_SOURCES:
                raise UsageError(
                    f"drift of {name!r} must be one of {DRIFT_SOURCES}, got {source!r}"
                )

    def mode(self, function: str) -> str:
        # TODO: check this (D13). A function missing from modes is evaluated from the data sheet.
        return self.modes.get(function, "datasheet")

    def check(self) -> tuple[Issue, ...]:
        """Certificate checks of all certificates of this unit.

        Every point must lie within the data sheet, as found and as left, using the column that
        the calibration interval falls in.
        """
        from gumeasure.calibration import interval_index

        ds = self.datasheet
        issues: list[Issue] = []
        intervals_d = [units.days(i) for i in ds.intervals]
        for cal in self.calibrations:
            column, _ = interval_index((cal.due - cal.date).days, intervals_d)
            for point in cal.points:
                unit = ds.function(point.function).unit
                range_ = ds.range(point.function, point.range)
                limit = ds.half_width(point.function, range_, point.reference, column)
                a = units.magnitude(limit, unit)
                for label, deviation in (
                    ("as found", point.as_found),
                    ("as left", point.deviation),
                ):
                    d = units.magnitude(deviation, unit)
                    if abs(d) > a * (1 + 1e-12):
                        issues.append(
                            Issue.of(
                                "certificate-out-of-spec",
                                f"certificate {cal.certificate}, {point.function}, "
                                f"{units.plain(point.range)} range, "
                                f"{units.plain(point.reference)}: "
                                f"{label} deviation {units.fmt(d, unit)} exceeds the data sheet "
                                f"half-width {units.fmt(a, unit)} ({_column_name(ds, column)})",
                            )
                        )
                    if point.deviation_as_found is None:
                        break
        return tuple(issues)

    def evaluate(
        self,
        function: str,
        readings: Quantity,
        *,
        range: Quantity | str | None = None,
        at: datetime,
        temperature: Quantity | str | None = None,
    ) -> Measurement:
        """Measurement with uncertainty budget for one series of readings.

        `at` is the time of the readings and must be timezone-aware. The clock is never read.
        """
        from gumeasure import inputs
        from gumeasure.evaluate import evaluate

        fn = self.datasheet.function(function)
        range_ = self.datasheet.range(function, range)
        if not isinstance(at, datetime):
            raise UsageError(f"at must be a datetime, got {at!r}")
        if at.tzinfo is None or at.utcoffset() is None:
            raise UsageError("at must be timezone-aware")
        temp: Quantity | None = None
        if temperature is not None:
            temp = _as_quantity(temperature, "kelvin", "temperature")
        if not units.is_quantity(readings):
            raise UsageError(f"readings must be a quantity with a unit of {fn.unit}")
        snapshot = inputs.build(self, function, range_, at, temp)
        return evaluate(readings, snapshot, datasheet=self.datasheet)


def _column_name(ds: Datasheet, column: int) -> str:
    if not ds.intervals:
        return "single accuracy column"
    return f"{interval_name(ds.intervals[column])} column"


# --------------------------------------------------------------------------------------------
# Results


@dataclass(frozen=True)
class Contribution:
    name: str
    u: float
    type: str
    distribution: str
    source: str


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    message: str

    @classmethod
    def of(cls, code: IssueCode, message: str) -> Issue:
        return cls(code=code, severity=SEVERITY[code], message=message)


MEASUREMENT_FORMAT = "gumeasure.measurement/1"


@dataclass(frozen=True)
class Measurement:
    value: float
    unit: str
    u: float
    k: float
    budget: tuple[Contribution, ...]
    issues: tuple[Issue, ...]
    inputs: Mapping[str, Any]

    @property
    def U(self) -> float:
        return self.k * self.u

    @property
    def usable(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe record. The budget has the form {name: {u, type, distribution, source}}."""
        return {
            "format": MEASUREMENT_FORMAT,
            "value": self.value,
            "unit": self.unit,
            "u": self.u,
            "k": self.k,
            "U": self.U,
            "usable": self.usable,
            "budget": {
                c.name: {
                    "u": c.u,
                    "type": c.type,
                    "distribution": c.distribution,
                    "source": c.source,
                }
                for c in self.budget
            },
            "issues": [
                {"code": i.code, "severity": i.severity, "message": i.message} for i in self.issues
            ],
            "inputs": _json_copy(self.inputs),
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> Measurement:
        """A Measurement from the output of to_dict. U and usable are derived again."""
        if record.get("format") != MEASUREMENT_FORMAT:
            raise UsageError(f"not a record of format {MEASUREMENT_FORMAT}")
        return cls(
            value=float(record["value"]),
            unit=str(record["unit"]),
            u=float(record["u"]),
            k=float(record["k"]),
            budget=tuple(
                Contribution(
                    name=name,
                    u=float(c["u"]),
                    type=str(c["type"]),
                    distribution=str(c["distribution"]),
                    source=str(c["source"]),
                )
                for name, c in record["budget"].items()
            ),
            issues=tuple(
                Issue(code=str(i["code"]), severity=str(i["severity"]), message=str(i["message"]))
                for i in record["issues"]
            ),
            inputs=_json_copy(record["inputs"]),
        )


def _json_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _json_copy(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [_json_copy(v) for v in value]
    return value

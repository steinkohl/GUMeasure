"""The inputs snapshot of a Measurement.

The snapshot holds every number the evaluation uses besides the readings. It is JSON-safe and
holds no references to files, so a record stays recomputable when the files are gone. Values of
the function are floats in the unit of the function. Temperatures are in °C, temperature
differences in K and durations in days.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Literal

from pydantic import ConfigDict, TypeAdapter, ValidationError

from gumeasure import units
from gumeasure._version import __version__
from gumeasure.calibration import Point, in_force
from gumeasure.errors import UsageError
from gumeasure.model import Accuracy, Calibration, Origin, Range, interval_name

if TYPE_CHECKING:
    from gumeasure.model import Instrument
    from gumeasure.units import Quantity

FORMAT = "gumeasure.inputs/1"
_STRICT = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class OriginRecord:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    name: str
    kind: str
    version: str | None
    sha256: str | None


@dataclass(frozen=True)
class AccuracyRecord:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    of_reading: float
    of_range: float
    offset: float
    counts: int


@dataclass(frozen=True)
class RangeRecord:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    full_scale: float
    resolution: float
    resolution_included: bool
    accuracy: tuple[AccuracyRecord, ...]
    tempco: AccuracyRecord | None


@dataclass(frozen=True)
class DatasheetRecord:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    origin: OriginRecord | None
    model: str
    source: str
    custom: bool
    tcal_degC: float
    band_K: float
    intervals: tuple[str, ...]
    intervals_d: tuple[float, ...]
    range: RangeRecord


@dataclass(frozen=True)
class CalibrationRecord:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    origin: OriginRecord | None
    certificate: str
    laboratory: str
    accredited: bool
    date: dt.date
    due: dt.date
    temperature_degC: float | None
    points: tuple[Point, ...]


@dataclass(frozen=True)
class Inputs:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    format: Literal["gumeasure.inputs/1"]
    gumeasure: str
    serial: str
    function: str
    unit: str
    mode: Literal["datasheet", "calibration"]
    drift: Literal["datasheet", "history"] | None
    at: datetime
    temperature_degC: float | None
    datasheet: DatasheetRecord
    calibration: CalibrationRecord | None
    previous: CalibrationRecord | None


ADAPTER: TypeAdapter[Inputs] = TypeAdapter(Inputs)


def to_json(record: Inputs) -> dict[str, Any]:
    data: dict[str, Any] = ADAPTER.dump_python(record, mode="json")
    return data


def from_json(data: Mapping[str, Any]) -> Inputs:
    """Typed inputs from a snapshot. Raises UsageError for a snapshot of another format."""
    if not isinstance(data, Mapping):
        raise UsageError("inputs must be a mapping")
    if data.get("format") != FORMAT:
        raise UsageError(f"inputs must have the format {FORMAT!r}, got {data.get('format')!r}")
    try:
        record = ADAPTER.validate_python(dict(data))
    except ValidationError as err:
        first = err.errors()[0]
        key = ".".join(str(part) for part in first["loc"])
        raise UsageError(f"inputs are not valid: {key}: {first['msg']}") from None
    if record.at.tzinfo is None or record.at.utcoffset() is None:
        raise UsageError("inputs.at must be timezone-aware")
    return record


def build(
    instrument: Instrument,
    function: str,
    range_: Range,
    at: datetime,
    temperature: Quantity | None,
) -> dict[str, Any]:
    """Snapshot for one evaluation, built from the domain objects."""
    ds = instrument.datasheet
    unit = ds.function(function).unit
    current, previous = in_force(instrument.calibrations, at.date())
    drift = instrument.drift.get(function)
    record = Inputs(
        format="gumeasure.inputs/1",
        gumeasure=__version__,
        serial=instrument.serial,
        function=function,
        unit=unit,
        mode=instrument.mode(function),  # type: ignore[arg-type]
        drift=drift,  # type: ignore[arg-type]
        at=at,
        temperature_degC=None if temperature is None else units.temperature_degc(temperature),
        datasheet=DatasheetRecord(
            origin=_origin(ds.origin),
            model=ds.model,
            source=ds.source,
            custom=ds.custom,
            tcal_degC=units.temperature_degc(ds.tcal),
            band_K=units.difference_kelvin(ds.band),
            intervals=tuple(interval_name(i) for i in ds.intervals),
            intervals_d=tuple(units.days(i) for i in ds.intervals),
            range=RangeRecord(
                full_scale=units.magnitude(range_.full_scale, unit),
                resolution=units.magnitude(range_.resolution, unit),
                resolution_included=range_.resolution_included,
                accuracy=tuple(_accuracy(a, unit) for a in range_.accuracy),
                tempco=None if range_.tempco is None else _accuracy(range_.tempco, unit),
            ),
        ),
        calibration=_calibration(current, function, range_, unit),
        previous=_calibration(previous, function, range_, unit) if drift == "history" else None,
    )
    return to_json(record)


def _origin(origin: Origin | None) -> OriginRecord | None:
    if origin is None:
        return None
    return OriginRecord(
        name=origin.name, kind=origin.kind, version=origin.version, sha256=origin.sha256
    )


def _accuracy(acc: Accuracy, unit: str) -> AccuracyRecord:
    of_reading, of_range, offset, counts = acc.values(unit)
    return AccuracyRecord(of_reading=of_reading, of_range=of_range, offset=offset, counts=counts)


def _calibration(
    cal: Calibration | None, function: str, range_: Range, unit: str
) -> CalibrationRecord | None:
    if cal is None:
        return None
    return CalibrationRecord(
        origin=_origin(cal.origin),
        certificate=cal.certificate,
        laboratory=cal.laboratory,
        accredited=cal.accredited,
        date=cal.date,
        due=cal.due,
        temperature_degC=None
        if cal.temperature is None
        else units.temperature_degc(cal.temperature),
        points=tuple(
            Point(
                reference=units.magnitude(p.reference, unit),
                deviation=units.magnitude(p.deviation, unit),
                U=units.magnitude(p.U, unit),
                k=float(p.k),
                deviation_as_found=None
                if p.deviation_as_found is None
                else units.magnitude(p.deviation_as_found, unit),
            )
            for p in cal.points_of(function, range_.full_scale, unit)
        ),
    )

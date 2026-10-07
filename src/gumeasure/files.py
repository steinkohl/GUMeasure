"""Data sheet and calibration files in TOML.

The classes here mirror the files key by key. pydantic validates them and gives the JSON
Schema. The loader converts them into the classes of gumeasure.model.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    TypeAdapter,
    ValidationError,
    WithJsonSchema,
)

from gumeasure import units
from gumeasure.errors import FileFormatError, ModelError
from gumeasure.model import (
    Accuracy,
    Calibration,
    CalPoint,
    Check,
    Datasheet,
    Function,
    Origin,
    Range,
)
from gumeasure.units import Quantity

DATASHEET_FORMAT = "gumeasure.datasheet/1"
CALIBRATION_FORMAT = "gumeasure.calibration/1"
DEVIATION_SIGN = "indication - reference"

QuantityStr = Annotated[
    Quantity,
    PlainValidator(units.parse_quantity),
    PlainSerializer(str),
    WithJsonSchema({"type": "string", "description": "number and unit, such as '10 mA'"}),
]
# TODO: check this (D15). Fractions need % or ppm.
FractionStr = Annotated[
    float,
    PlainValidator(units.parse_fraction),
    WithJsonSchema(
        {"type": "string", "pattern": "(%|ppm)\\s*$", "description": "such as '0.0015 %'"}
    ),
]
_STRICT = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class AccuracyFile:
    """Half-width a = of_reading·|x| + of_range·full_scale + offset + counts·resolution."""

    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    of_reading: FractionStr = 0.0
    of_range: FractionStr = 0.0
    offset: QuantityStr | None = None
    counts: Annotated[int, Field(ge=0)] = 0


@dataclass(frozen=True)
class RangeFile:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    full_scale: QuantityStr
    resolution: QuantityStr
    resolution_included: bool
    accuracy: list[AccuracyFile]
    tempco: AccuracyFile | None = None


@dataclass(frozen=True)
class FunctionFile:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    unit: str
    range: list[RangeFile]


@dataclass(frozen=True)
class CheckFile:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    function: str
    range: QuantityStr
    reading: QuantityStr
    half_width: QuantityStr
    interval: QuantityStr | None = None


@dataclass(frozen=True)
class DatasheetFile:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", title="gumeasure data sheet"
    )

    schema: Literal["gumeasure.datasheet/1"]
    model: str
    vendor: str
    source: str
    tcal: QuantityStr
    band: QuantityStr
    function: dict[str, FunctionFile]
    intervals: list[QuantityStr] = field(default_factory=list)
    check: list[CheckFile] = field(default_factory=list)


@dataclass(frozen=True)
class PointFile:
    __pydantic_config__: ClassVar[ConfigDict] = _STRICT

    function: str
    range: QuantityStr
    reference: QuantityStr
    deviation: QuantityStr
    U: QuantityStr
    k: Annotated[float, Field(gt=0)]
    deviation_as_found: QuantityStr | None = None


@dataclass(frozen=True)
class CalibrationFile:
    __pydantic_config__: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid", title="gumeasure calibration certificate"
    )

    schema: Literal["gumeasure.calibration/1"]
    model: str
    serial: str
    certificate: str
    laboratory: str
    accredited: bool
    date: dt.date
    due: dt.date
    deviation_sign: Literal["indication - reference"]
    temperature: QuantityStr | None = None
    point: list[PointFile] = field(default_factory=list)


_DATASHEET = TypeAdapter(DatasheetFile)
_CALIBRATION = TypeAdapter(CalibrationFile)


# --------------------------------------------------------------------------------------------
# Loading


def load(path: str | Path) -> Datasheet | Calibration:
    """Load a data sheet or a calibration file. The `schema` key tells them apart."""
    _, data, sha = _read(path)
    kind = data.get("schema")
    if isinstance(kind, str) and kind.startswith("gumeasure.datasheet/"):
        return _datasheet(str(path), data, sha)
    if isinstance(kind, str) and kind.startswith("gumeasure.calibration/"):
        return _calibration(str(path), data, sha)
    raise FileFormatError(
        str(path), [("schema", f"must be {DATASHEET_FORMAT!r} or {CALIBRATION_FORMAT!r}")]
    )


def load_datasheet(path: str | Path) -> Datasheet:
    _, data, sha = _read(path)
    return _datasheet(str(path), data, sha)


def load_calibration(path: str | Path) -> Calibration:
    _, data, sha = _read(path)
    return _calibration(str(path), data, sha)


def _read(path: str | Path) -> tuple[str, dict[str, Any], str]:
    name = str(path)
    try:
        raw = Path(path).read_bytes()
    except OSError as err:
        raise FileFormatError(name, [("", f"cannot read the file: {err.strerror}")]) from None
    try:
        text = raw.decode("utf-8")
        data = tomllib.loads(text)
    except UnicodeDecodeError:
        raise FileFormatError(name, [("", "the file is not UTF-8")]) from None
    except tomllib.TOMLDecodeError as err:
        raise FileFormatError(name, [("", f"not valid TOML: {err}")]) from None
    return text, data, hashlib.sha256(raw).hexdigest()


def _check_schema(path: str, data: dict[str, Any], expected: str) -> None:
    found = data.get("schema")
    if found != expected:
        message = "missing" if found is None else f"must be {expected!r}, got {found!r}"
        raise FileFormatError(path, [("schema", message)])


def _validate(adapter: TypeAdapter[Any], path: str, data: dict[str, Any]) -> Any:
    try:
        return adapter.validate_python(data)
    except ValidationError as err:
        raise FileFormatError(path, [_problem(e) for e in err.errors()]) from None


def _problem(error: Any) -> tuple[str, str]:
    loc = list(error["loc"])
    kind = error["type"]
    if kind in ("unexpected_keyword_argument", "extra_forbidden"):
        message = "unknown key"
    elif kind in ("missing", "missing_argument", "missing_keyword_only_argument"):
        message = "missing key"
    else:
        message = str(error["msg"]).removeprefix("Value error, ")
    # pydantic adds the name of the union member for optional values. Drop it.
    loc = [part for part in loc if part not in ("function-plain[parse_quantity()]",)]
    return _key_path(loc), message


def _key_path(loc: list[Any]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            text = str(part)
            if "." in text or " " in text:
                text = f'"{text}"'
            out += f".{text}" if out else text
    return out


def _datasheet(path: str, data: dict[str, Any], sha: str) -> Datasheet:
    _check_schema(path, data, DATASHEET_FORMAT)
    f: DatasheetFile = _validate(_DATASHEET, path, data)
    try:
        return Datasheet(
            model=f.model,
            vendor=f.vendor,
            source=f.source,
            tcal=f.tcal,
            band=f.band,
            intervals=tuple(f.intervals),
            functions={
                name: Function(
                    unit=fn.unit,
                    ranges=tuple(
                        Range(
                            full_scale=r.full_scale,
                            resolution=r.resolution,
                            resolution_included=r.resolution_included,
                            accuracy=tuple(_accuracy(a) for a in r.accuracy),
                            tempco=None if r.tempco is None else _accuracy(r.tempco),
                        )
                        for r in fn.range
                    ),
                )
                for name, fn in f.function.items()
            },
            checks=tuple(
                Check(
                    function=c.function,
                    range=c.range,
                    reading=c.reading,
                    interval=c.interval,
                    half_width=c.half_width,
                )
                for c in f.check
            ),
            origin=Origin(name=path, kind="file", sha256=sha),
        )
    except ModelError as err:
        raise FileFormatError(path, err.problems) from None


def _accuracy(a: AccuracyFile) -> Accuracy:
    return Accuracy(of_reading=a.of_reading, of_range=a.of_range, offset=a.offset, counts=a.counts)


def _calibration(path: str, data: dict[str, Any], sha: str) -> Calibration:
    _check_schema(path, data, CALIBRATION_FORMAT)
    f: CalibrationFile = _validate(_CALIBRATION, path, data)
    try:
        return Calibration(
            model=f.model,
            serial=f.serial,
            certificate=f.certificate,
            laboratory=f.laboratory,
            accredited=f.accredited,
            date=f.date,
            due=f.due,
            temperature=f.temperature,
            points=tuple(
                CalPoint(
                    function=p.function,
                    range=p.range,
                    reference=p.reference,
                    deviation=p.deviation,
                    U=p.U,
                    k=p.k,
                    deviation_as_found=p.deviation_as_found,
                )
                for p in f.point
            ),
            origin=Origin(name=path, kind="file", sha256=sha),
        )
    except ModelError as err:
        raise FileFormatError(path, err.problems) from None


# --------------------------------------------------------------------------------------------
# JSON Schema

SCHEMA_KINDS = ("datasheet", "calibration")


def json_schema(kind: str) -> dict[str, Any]:
    """JSON Schema of a file format, 'datasheet' or 'calibration'."""
    if kind == "datasheet":
        schema = _DATASHEET.json_schema()
        fmt = DATASHEET_FORMAT
    elif kind == "calibration":
        schema = _CALIBRATION.json_schema()
        fmt = CALIBRATION_FORMAT
    else:
        raise ValueError(f"kind must be one of {SCHEMA_KINDS}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$comment": f"Generated by gumeasure for the format {fmt}. Do not edit.",
        **schema,
    }


def json_schema_text(kind: str) -> str:
    return json.dumps(json_schema(kind), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def schema_path(kind: str) -> Path:
    """Path of the committed schema file in the package."""
    return Path(__file__).parent / "schema" / f"{kind}.schema.json"

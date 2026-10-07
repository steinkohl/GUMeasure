"""Units and quantities.

gumeasure uses the application registry of pint, so quantities of gumeasure and of the caller
can be mixed. All parsing of quantity strings goes through this module. Files and Python data
sheets use the same functions, so equal text gives equal objects.
"""

from __future__ import annotations

import functools
import math
import re
from typing import TYPE_CHECKING, Any, TypeAlias, TypeGuard

import pint

if TYPE_CHECKING:
    Quantity: TypeAlias = pint.Quantity[Any]
else:
    Quantity = pint.Quantity

_NUMBER_AND_UNIT = re.compile(
    r"\s*(?P<number>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(?P<unit>.*?)\s*"
)
_FRACTION_UNITS = ("%", "percent", "ppm")


def registry() -> Any:
    """The pint application registry."""
    return pint.get_application_registry()  # type: ignore[no-untyped-call]


def is_quantity(value: object) -> TypeGuard[Quantity]:
    return isinstance(value, pint.Quantity)


def make(magnitude: Any, unit: str | Any) -> Quantity:
    """A quantity of the application registry."""
    ureg = registry()
    units = ureg.parse_units(unit) if isinstance(unit, str) else unit
    result: Quantity = ureg.Quantity(magnitude, units)
    return result


def parse_quantity(text: object) -> Quantity:
    """Parse a string such as "10 mA" or "23 °C" into a quantity.

    pint reads "23 °C" as 23 × °C and refuses it, because °C is an offset unit. So the number is
    split from the unit here. A string without a unit is refused.
    """
    if is_quantity(text):
        return text
    if not isinstance(text, str):
        raise ValueError(f"expected a string with a number and a unit, got {text!r}")
    match = _NUMBER_AND_UNIT.fullmatch(text)
    if match is None:
        raise ValueError(f"not a number with a unit: {text!r}")
    unit = match["unit"]
    if not unit:
        raise ValueError(f"missing unit in {text!r}")
    try:
        units = registry().parse_units(unit)
    except (pint.UndefinedUnitError, pint.errors.DefinitionSyntaxError, AttributeError) as err:
        raise ValueError(f"unknown unit {unit!r} in {text!r}") from err
    except Exception as err:  # pint raises several types for malformed units
        raise ValueError(f"unknown unit {unit!r} in {text!r}") from err
    return make(float(match["number"]), units)


def parse_fraction(text: object) -> float:
    """Parse "0.0015 %" or "5 ppm" into a dimensionless fraction.

    A bare number is refused, because it is unclear whether a fraction or a percentage is meant.
    """
    # TODO: check this (D15)
    if isinstance(text, float | int) and not isinstance(text, bool):
        raise ValueError(f"a fraction needs % or ppm, got the bare number {text!r}")
    if not isinstance(text, str):
        raise ValueError(f"expected a string such as '0.01 %', got {text!r}")
    stripped = text.strip()
    if not stripped.endswith(_FRACTION_UNITS):
        raise ValueError(f"a fraction needs % or ppm, got {text!r}")
    value = parse_quantity(stripped)
    return float(value.to("dimensionless").magnitude)


def q(text: str) -> Quantity:
    """Short form of parse_quantity for data sheets written in Python."""
    return parse_quantity(text)


def frac(text: str) -> float:
    """Short form of parse_fraction for data sheets written in Python."""
    return parse_fraction(text)


def units_of(unit: str) -> Any:
    """Parse a unit string. Raises ValueError for an unknown unit."""
    try:
        return registry().parse_units(unit)
    except Exception as err:
        raise ValueError(f"unknown unit {unit!r}") from err


@functools.lru_cache(maxsize=256)
def is_logarithmic(unit: str) -> bool:
    """True for a logarithmic unit such as dBm.

    Differences of a logarithmic unit, such as half-widths, resolutions and deviations, are
    given in dB. A function in dBm has its readings in dBm and its half-widths in dB.
    """
    try:
        value = make(1.0, unit)
    except Exception:
        return False
    return not bool(value._is_multiplicative) and not bool(
        value.dimensionality == units_of("kelvin").dimensionality
    )


def _is_decibel(value: Quantity) -> bool:
    return str(value.units) == "decibel"


def same_dimension(value: Quantity, unit: str) -> bool:
    if is_logarithmic(unit) and _is_decibel(value):
        return True
    return bool(value.dimensionality == units_of(unit).dimensionality)


def is_offset(value: Quantity) -> bool:
    """True for quantities in an offset unit such as °C."""
    return not bool(value._is_multiplicative)


def magnitude(value: Quantity, unit: str) -> float:
    """Magnitude of a scalar quantity in the given unit, as a float.

    For a logarithmic unit, a difference in dB is taken as it is.
    """
    if _is_decibel(value) and is_logarithmic(unit):
        return float(value.magnitude)
    return float(value.to(unit).magnitude)


def temperature_degc(value: Quantity) -> float:
    return float(value.to("degC").magnitude)


def difference_kelvin(value: Quantity) -> float:
    """Magnitude of a temperature difference in kelvin."""
    return float(value.to("kelvin").magnitude)


def days(value: Quantity) -> float:
    return float(value.to("day").magnitude)


def seconds(value: Quantity) -> float:
    return float(value.to("second").magnitude)


def close(a: float, b: float) -> bool:
    """Equality of two values of the same unit within 1e-9 relative."""
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=0.0)


def fmt(value: float, unit: str, digits: int = 4) -> str:
    """A value with unit for messages, with an SI prefix that suits it."""
    if is_logarithmic(unit):
        return f"{value:.{digits}g} {_symbol(unit)}"
    if value == 0 or not math.isfinite(value):
        return f"{value:g} {_symbol(unit)}"
    compact = make(value, unit).to_compact()
    return f"{compact:.{digits}g~P}"


def fmt_delta(value: float, unit: str, digits: int = 4) -> str:
    """A difference, half-width or uncertainty for messages. In dB for a logarithmic unit."""
    if is_logarithmic(unit):
        return f"{value:.{digits}g} dB"
    return fmt(value, unit, digits)


def plain(value: Quantity) -> str:
    """A quantity as it was written, such as '10 V' or '23 °C'."""
    return f"{value:g~P}"


def _symbol(unit: str) -> str:
    return f"{make(1, unit).units:~P}"

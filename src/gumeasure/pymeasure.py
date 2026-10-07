"""Binding to PyMeasure instruments.

`Measured` wraps a PyMeasure instrument. Reading a measured property returns a Measurement
instead of a float. Everything else passes through to the instrument unchanged.

    psu = Measured(SPD1305X("TCPIP::192.168.1.20::INSTR"), calibrations=["cal.toml"])
    m = psu.ch_1.current               # Measurement of one reading
    s = psu.ch_1.measure("current", n=10, interval="20 ms")   # Series of ten readings
    psu.ch_1.voltage_setpoint = 5      # passes through to PyMeasure

`Reader` is the building block below it. It reads one property n times and evaluates the
series. gumeasure only reads measured properties. PyMeasure is not imported at run time.
Install the extra `gumeasure[pymeasure]` for a tested PyMeasure version.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gumeasure import units
from gumeasure.errors import UsageError
from gumeasure.model import Calibration, Datasheet, Instrument, Measurement
from gumeasure.registry import instrument as build_instrument
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
    raw_unit: str | None = None
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
        unit: str | None = None,
    ) -> Series:
        """Read the property n times, `interval` apart, and evaluate the series.

        `unit` converts the result, also between dB and linear units.
        """
        if n < 1:
            raise UsageError("n must be 1 or more")
        spacing = units.seconds(units.parse_quantity(interval))
        raw_unit = self.raw_unit or self.instrument.datasheet.function(self.function).unit
        times: list[datetime] = []
        magnitudes: list[float] = []
        for i in range(n):
            start = self.clock()
            times.append(start)
            value = getattr(self.obj, self.prop)
            magnitudes.append(_magnitude(value, raw_unit))
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
        readings = units.make(magnitudes, raw_unit)
        measurement = self.instrument.evaluate(
            self.function,
            readings,
            range=range_,
            at=at if at is not None else times[0],
            temperature=temperature,
            unit=unit,
        )
        return Series(measurement=measurement, readings=readings, times=tuple(times))


def _magnitude(value: Any, unit: str) -> float:
    if units.is_quantity(value):
        return units.magnitude(value, unit)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise UsageError(f"the property returned {value!r}, not a number") from None


# --------------------------------------------------------------------------------------------
# Wrapper


@dataclass(frozen=True)
class Prop:
    """How a measured property of a PyMeasure instrument maps to a function of the data sheet.

    `range` is a fixed full scale. `range_prop` names a property that returns it, relative to
    the object that holds the measured property. `raw_unit` is the unit of plain floats.
    """

    function: str
    range: Quantity | str | None = None
    range_prop: str | None = None
    raw_unit: str | None = None


@dataclass(frozen=True)
class Binding:
    """Data sheet and measured properties of a PyMeasure instrument class."""

    datasheet: str
    properties: Mapping[str, Prop | str]


#: Bindings of PyMeasure classes, by module and class name. Subclasses use the binding of the
#: nearest class in their method resolution order. Add more with `register`.
BINDINGS: dict[str, Binding] = {
    "pymeasure.instruments.siglenttechnologies.siglent_spd1305x.SPD1305X": Binding(
        datasheet="gumeasure:siglent.SPD1305X",
        properties={"ch_1.voltage": "readback.voltage", "ch_1.current": "readback.current"},
    ),
}


def register(cls: type | str, binding: Binding) -> None:
    """Add or replace the binding of a PyMeasure class."""
    key = cls if isinstance(cls, str) else f"{cls.__module__}.{cls.__qualname__}"
    BINDINGS[key] = binding


def binding_of(driver: object) -> Binding | None:
    for cls in type(driver).__mro__:
        found = BINDINGS.get(f"{cls.__module__}.{cls.__qualname__}")
        if found is not None:
            return found
    return None


TemperatureSource = Quantity | str | Callable[[], Quantity | str | None] | None


@dataclass
class _State:
    driver: Any
    instrument: Instrument
    properties: dict[str, Prop]
    temperature: TemperatureSource
    unit: Mapping[str, str]
    clock: Callable[[], datetime]
    sleep: Callable[[float], None]
    last: Series | None = None
    history: list[Series] = field(default_factory=list)
    keep: int = 0


class _Node:
    """A PyMeasure object, or a part of it, with its measured properties replaced."""

    __slots__ = ("_path", "_state")
    _path: str
    _state: _State

    def __init__(self, state: _State, path: str) -> None:
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_path", path)

    # PyMeasure side ---------------------------------------------------------------------

    def _target(self) -> Any:
        obj = self._state.driver
        for part in self._path.split(".") if self._path else ():
            obj = getattr(obj, part)
        return obj

    def _full(self, name: str) -> str:
        return f"{self._path}.{name}" if self._path else name

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        path = self._full(name)
        if path in self._state.properties:
            return self._read(path, 1, "0 s", None, None, None).measurement
        if any(key.startswith(path + ".") for key in self._state.properties):
            return _Node(self._state, path)
        return getattr(self._target(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if self._full(name) in self._state.properties:
            raise AttributeError(f"{self._full(name)} is a measured property and read only")
        setattr(self._target(), name, value)

    def __dir__(self) -> list[str]:
        own = {
            k[len(self._path) + 1 :].split(".")[0] if self._path else k.split(".")[0]
            for k in self._state.properties
            if not self._path or k.startswith(self._path + ".")
        }
        return sorted(set(dir(self._target())) | own | {"measure"})

    def __repr__(self) -> str:
        return f"<gumeasure Measured {self._path or type(self._state.driver).__name__}>"

    # gumeasure side ---------------------------------------------------------------------

    def measure(
        self,
        name: str,
        n: int = 1,
        interval: Quantity | str = "0 s",
        *,
        at: datetime | None = None,
        temperature: Quantity | str | None = None,
        unit: str | None = None,
    ) -> Series:
        """Read a measured property n times, `interval` apart, and evaluate the series.

        The Series holds the Measurement and the raw readings with their times.
        """
        path = self._full(name)
        if path not in self._state.properties:
            known = ", ".join(sorted(self._state.properties))
            raise UsageError(f"{path!r} is no measured property. Known: {known}")
        return self._read(path, n, interval, at, temperature, unit)

    def _read(
        self,
        path: str,
        n: int,
        interval: Quantity | str,
        at: datetime | None,
        temperature: Quantity | str | None,
        unit: str | None,
    ) -> Series:
        state = self._state
        prop = state.properties[path]
        holder_path, _, attr = path.rpartition(".")
        holder: Any = state.driver
        for part in holder_path.split(".") if holder_path else ():
            holder = getattr(holder, part)
        if temperature is None:
            source = state.temperature
            temperature = source() if callable(source) else source
        reader = Reader(
            state.instrument,
            prop.function,
            holder,
            attr,
            range=prop.range,
            range_prop=prop.range_prop,
            raw_unit=prop.raw_unit,
            clock=state.clock,
            sleep=state.sleep,
        )
        series = reader.measure(
            n=n,
            interval=interval,
            at=at,
            temperature=temperature,
            unit=unit or state.unit.get(path),
        )
        state.last = series
        if state.keep:
            state.history.append(series)
            del state.history[: -state.keep]
        return series


class Measured(_Node):
    """A PyMeasure instrument whose measured properties return Measurements.

    Without `instrument`, gumeasure builds one from the binding of the PyMeasure class, or
    from `datasheet` and `properties`, and from the certificate files in `calibrations`.

    - `modes` and `drift` are as for `gumeasure.instrument`. A function missing from `modes`
      is evaluated from the data sheet.
    - `temperature` is the ambient temperature: a quantity, a string such as "23 °C", or a
      function that returns one at each reading. None notes `temperature-assumed`.
    - `unit` maps a property path to the unit of its result, such as {"ch_1.current": "mA"}.
    - `keep` is how many past Series `history` holds. `last` is always the latest Series.
    """

    def __init__(
        self,
        driver: Any,
        instrument: Instrument | None = None,
        *,
        calibrations: Sequence[str | Path | Calibration] = (),
        modes: Mapping[str, str] | None = None,
        drift: Mapping[str, str] | None = None,
        serial: str | None = None,
        datasheet: str | Datasheet | None = None,
        properties: Mapping[str, Prop | str] | None = None,
        temperature: TemperatureSource = None,
        unit: Mapping[str, str] | None = None,
        keep: int = 0,
        clock: Callable[[], datetime] = utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        binding = binding_of(driver)
        if properties is None:
            if binding is None:
                raise UsageError(
                    f"no binding for {type(driver).__qualname__}. Give datasheet and properties, "
                    "or register a Binding."
                )
            properties = binding.properties
        if instrument is None:
            name = datasheet if datasheet is not None else binding.datasheet if binding else None
            if name is None:
                raise UsageError("give instrument or datasheet")
            instrument = build_instrument(
                name, calibrations, modes=modes or {}, drift=drift, serial=serial
            )
        props = {path: p if isinstance(p, Prop) else Prop(p) for path, p in properties.items()}
        for prop in props.values():
            instrument.datasheet.function(prop.function)
        state = _State(
            driver=driver,
            instrument=instrument,
            properties=props,
            temperature=temperature,
            unit=dict(unit or {}),
            clock=clock,
            sleep=sleep,
            keep=keep,
        )
        super().__init__(state, "")

    @property
    def instrument(self) -> Instrument:
        return self._state.instrument

    @property
    def driver(self) -> Any:
        """The wrapped PyMeasure instrument."""
        return self._state.driver

    @property
    def last(self) -> Series | None:
        """The latest Series, with raw readings and times."""
        return self._state.last

    @property
    def history(self) -> Iterator[Series]:
        return iter(self._state.history)

    @property
    def temperature(self) -> TemperatureSource:
        return self._state.temperature

    @temperature.setter
    def temperature(self, value: TemperatureSource) -> None:
        self._state.temperature = value

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "temperature":
            self._state.temperature = value
            return
        super().__setattr__(name, value)

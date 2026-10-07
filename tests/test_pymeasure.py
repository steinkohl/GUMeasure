from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("pymeasure")
from pymeasure.instruments.siglenttechnologies import SPD1305X
from pymeasure.test import expected_protocol

import gumeasure as gm
from gumeasure.pymeasure import Reader

from .conftest import DATA, E1_READINGS


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 1, 8, tzinfo=UTC)
        self.slept: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def test_reader_with_expected_protocol():
    inst = gm.instrument(
        "gumeasure:siglent.SPD1305X",
        [DATA / "SPD1305X-factory.toml"],
        modes={"readback.current": "datasheet"},
    )
    clock = FakeClock()
    protocol = [(b"MEAS:CURR? CH1", str(r).encode()) for r in E1_READINGS]
    with expected_protocol(SPD1305X, protocol) as psu:
        reader = Reader(
            inst,
            function="readback.current",
            obj=psu.ch_1,
            prop="current",
            clock=clock,
            sleep=clock.sleep,
        )
        series = reader.measure(n=10, interval="20 ms")
    m = series.measurement
    assert abs(m.u - 6.100521297e-3) <= 1e-9 * 6.100521297e-3
    assert len(series.times) == 10
    assert series.times[0] == datetime(2026, 6, 1, 8, tzinfo=UTC)
    assert m.inputs["at"].startswith("2026-06-01T08:00:00")
    assert clock.slept == [pytest.approx(0.02)] * 9
    assert series.readings.to("A").magnitude.tolist() == E1_READINGS


class FakeDMM:
    def __init__(self) -> None:
        self.values = iter([7.0, 7.00001])
        self.reads: list[str] = []

    @property
    def voltage(self) -> float:
        self.reads.append("voltage")
        return next(self.values)

    @property
    def voltage_range(self) -> float:
        self.reads.append("range")
        return 10.0


def test_range_prop_read_after_the_series():
    inst = gm.instrument("gumeasure:example.EXAMPLE_DMM", ["examples/EX0001-2026.toml"], modes={})
    dmm = FakeDMM()
    clock = FakeClock()
    series = Reader(
        inst, "dcv", dmm, "voltage", range_prop="voltage_range", clock=clock, sleep=clock.sleep
    ).measure(n=2)
    assert dmm.reads == ["voltage", "voltage", "range"]
    assert series.measurement.inputs["datasheet"]["range"]["full_scale"] == 10.0


def test_measured_wrapper_returns_measurements():
    from gumeasure.pymeasure import Measured

    clock = FakeClock()
    protocol = [(b"MEAS:CURR? CH1", b"0.182")]
    protocol += [(b"MEAS:CURR? CH1", str(r).encode()) for r in E1_READINGS]
    protocol += [(b"CH1:VOLT 5", None), (b"MEAS:VOLT? CH1", b"5.002")]
    with expected_protocol(SPD1305X, protocol) as driver:
        psu = Measured(
            driver,
            calibrations=[DATA / "SPD1305X-factory.toml"],
            temperature="24 °C",
            unit={"ch_1.voltage": "mV"},
            keep=5,
            clock=clock,
            sleep=clock.sleep,
        )
        single = psu.ch_1.current
        series = psu.ch_1.measure("current", n=10, interval="20 ms")
        psu.ch_1.voltage_setpoint = 5
        volts = psu.ch_1.voltage
    assert isinstance(single, gm.Measurement) and single.value == 0.182
    assert [i.code for i in single.issues] == ["single-reading"]
    assert series.measurement.issues == ()  # ten readings, temperature given
    assert series.measurement.inputs["temperature_degC"] == 24.0
    assert volts.unit == "mV" and abs(volts.value - 5002.0) < 1e-9
    assert psu.last is not None and psu.last.measurement == volts
    assert len(list(psu.history)) == 3
    assert psu.instrument.serial == "TEST0001"


def test_measured_refuses_writing_a_measured_property():
    from gumeasure.pymeasure import Measured

    with expected_protocol(SPD1305X, []) as driver:
        psu = Measured(driver, calibrations=[DATA / "SPD1305X-factory.toml"])
        with pytest.raises(AttributeError):
            psu.ch_1.current = 1.0
        with pytest.raises(gm.UsageError):
            psu.ch_1.measure("power")


def test_measured_without_binding_needs_properties():
    from gumeasure.pymeasure import Measured

    dmm = FakeDMM()
    with pytest.raises(gm.UsageError):
        Measured(dmm, calibrations=["examples/EX0001-2026.toml"])
    clock = FakeClock()
    wrapped = Measured(
        dmm,
        datasheet="gumeasure:example.EXAMPLE_DMM",
        calibrations=["examples/EX0001-2026.toml"],
        properties={"voltage": "dcv"},
        clock=clock,
        sleep=clock.sleep,
    )
    assert wrapped.voltage.value == 7.0
    assert wrapped.voltage_range == 10.0

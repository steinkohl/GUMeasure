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

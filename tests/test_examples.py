"""Worked examples E1 to E5 of the design, with fixed expected values."""

from __future__ import annotations

import math
from datetime import date, datetime

import gumeasure as gm
from gumeasure.units import make, q

from .conftest import CEST, DATA, E1_READINGS, E2_AT, example_instrument, rel


def budget(m: gm.Measurement) -> dict[str, float]:
    return {c.name: c.u for c in m.budget}


def codes(m: gm.Measurement) -> list[str]:
    return [i.code for i in m.issues]


def spd(
    serial: str = "TEST0001",
    files: tuple[str, ...] = ("SPD1305X-factory.toml",),
    mode: str = "datasheet",
    drift: str | None = None,
) -> gm.Instrument:
    return gm.instrument(
        "gumeasure:siglent.SPD1305X",
        [DATA / f for f in files],
        modes={"readback.current": mode},
        drift={"readback.current": drift} if drift else {},
    )


def test_e1_mode_a_spd1305x_current():
    m = spd().evaluate(
        "readback.current", make(E1_READINGS, "A"), at=datetime(2026, 6, 1, 10, tzinfo=CEST)
    )
    b = budget(m)
    assert rel(m.value, 0.1827)
    assert rel(b["repeatability"], 2.134374746e-4)
    assert rel(b["accuracy"], 6.089948374e-3)
    assert rel(b["resolution"], 2.886751346e-4)
    assert rel(m.u, 6.100521297e-3)
    assert rel(m.U, 1.220104259e-2)
    assert codes(m) == ["temperature-assumed"]
    assert m.usable
    assert {c.name: (c.type, c.distribution) for c in m.budget} == {
        "repeatability": ("A", "normal"),
        "resolution": ("B", "rectangular"),
        "accuracy": ("B", "rectangular"),
    }


def test_e2_half_widths(example_ds):
    rng = example_ds.range("dcv", "10 V")
    got = [example_ds.half_width("dcv", rng, q("7 V"), i).to("mV").magnitude for i in range(3)]
    for g, want in zip(got, [0.145, 0.225, 0.295], strict=True):
        assert rel(g, want)


def test_e2_mode_a():
    m = example_instrument().evaluate("dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C")
    assert m.value == 7.0
    assert rel(m.u, 1.703183294e-4)
    assert rel(m.U, 3.406366588e-4)
    assert codes(m) == ["single-reading"]
    assert "1 year" in m.budget[0].source


def test_e2_mode_b_datasheet_drift():
    m = example_instrument("calibration", "datasheet").evaluate(
        "dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C"
    )
    b = budget(m)
    assert rel(m.value, 6.999948)
    assert rel(b["calibration"], 2.0e-5)
    assert rel(b["short-term accuracy"], 8.371578903e-5)
    assert rel(b["drift since calibration"], 8.660254038e-5)
    assert rel(m.u, 1.220996860e-4)
    assert rel(m.U, 2.441993721e-4)
    assert codes(m) == ["single-reading"]
    assert "EX-2026-0042" in m.budget[0].source


def test_e3_temperature():
    m = example_instrument("calibration", "datasheet").evaluate(
        "dcv", make([7.0], "V"), at=E2_AT, temperature="30 °C"
    )
    assert rel(budget(m)["temperature"], 5.196152423e-5)
    assert rel(m.u, 1.326963953e-4)
    assert rel(m.U, 2.653927907e-4)


def test_e4_history_drift():
    m = example_instrument("calibration", "history").evaluate(
        "dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C"
    )
    assert rel(budget(m)["drift since calibration"], 9.490689357e-6)
    assert rel(budget(m)["drift since calibration"] * math.sqrt(3), 1.643835616e-5)
    assert m.usable


def test_e5_certificate_out_of_spec():
    bad = gm.load_calibration(DATA / "EX0001-out-of-spec.toml")
    inst = gm.Instrument(
        gm.datasheet("gumeasure:example.EXAMPLE_DMM"),
        "EX0001",
        (bad,),
        modes={"dcv": "calibration"},
        drift={"dcv": "datasheet"},
    )
    assert [i.code for i in inst.check()] == ["certificate-out-of-spec"]
    m = inst.evaluate("dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C")
    assert "certificate-out-of-spec" in codes(m)
    assert not m.usable


def test_e5_expired():
    m = example_instrument().evaluate(
        "dcv", make([7.0], "V"), at=datetime(2027, 3, 10, tzinfo=CEST), temperature="23 °C"
    )
    assert "calibration-expired" in codes(m)
    assert not m.usable


def test_e5_due_date_still_valid():
    m = example_instrument().evaluate(
        "dcv", make([7.0], "V"), at=datetime(2027, 3, 2, 23, tzinfo=CEST), temperature="23 °C"
    )
    assert m.usable


def test_e5_extrapolated():
    m = example_instrument("calibration", "datasheet").evaluate(
        "dcv", make([2.0], "V"), at=E2_AT, temperature="23 °C"
    )
    assert "extrapolated" in codes(m)
    assert m.usable
    assert [c.name for c in m.budget] == ["accuracy"]
    assert m.value == 2.0


def test_e5_drift_unknown_without_intervals():
    inst = spd("TEST0002", ("SPD1305X-points.toml",), "calibration", "datasheet")
    m = inst.evaluate(
        "readback.current", make(E1_READINGS, "A"), at=datetime(2026, 6, 1, tzinfo=CEST)
    )
    assert "drift-unknown" in codes(m)
    assert not m.usable


def test_calibration_missing():
    m = example_instrument().evaluate(
        "dcv", make([7.0], "V"), at=datetime(2024, 1, 1, tzinfo=CEST), temperature="23 °C"
    )
    assert codes(m)[0] == "calibration-missing"
    assert not m.usable


def test_interval_exceeded_and_leap_year():
    from gumeasure.calibration import interval_index

    assert interval_index(366, [1.0, 90.0, 365.25]) == (2, False)
    assert interval_index(367, [1.0, 90.0, 365.25]) == (2, True)
    assert (date(2028, 3, 2) - date(2027, 3, 2)).days == 366


def test_history_needs_two_certificates():
    m = example_instrument("calibration", "history", ("EX0001-2026.toml",)).evaluate(
        "dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C"
    )
    assert "drift-unknown" in codes(m)


def test_no_drift_source_in_mode_b():
    m = example_instrument("calibration").evaluate(
        "dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C"
    )
    assert "drift-unknown" in codes(m)


def test_overrange():
    m = example_instrument().evaluate("dcv", make([10.5], "V"), at=E2_AT, temperature="23 °C")
    assert "overrange" in codes(m)

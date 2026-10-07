"""Use of the built-in data sheets of real instruments, with fictional certificates."""

from datetime import UTC, date, datetime

import gumeasure as gm
from gumeasure.units import make

AT = datetime(2026, 6, 1, tzinfo=UTC)


def dmm(temperature: str | None = "23 °C") -> gm.Instrument:
    from gumeasure.units import q

    cal = gm.Calibration(
        "SDM3065X",
        "FICTIONAL",
        "TEST-1",
        "Fictional laboratory",
        True,
        date(2026, 1, 1),
        date(2027, 1, 1),
        None if temperature is None else q(temperature),
    )
    return gm.Instrument(gm.datasheet("gumeasure:siglent.SDM3065X"), "FICTIONAL", (cal,), modes={})


def codes(m: gm.Measurement) -> list[str]:
    return [i.code for i in m.issues]


def test_ten_percent_over_range_is_covered():
    m = dmm().evaluate("dcv", make([21.5], "V"), range="20 V", at=AT, temperature="23 °C")
    assert "overrange" not in codes(m)
    m = dmm().evaluate("dcv", make([22.5], "V"), range="20 V", at=AT, temperature="23 °C")
    assert "overrange" in codes(m)
    m = dmm().evaluate("dcv", make([1000.5], "V"), range="1000 V", at=AT, temperature="23 °C")
    assert "overrange" in codes(m)


def test_tcal_from_the_certificate():
    m = dmm("21 °C").evaluate("dcv", make([10.0], "V"), range="20 V", at=AT, temperature="28 °C")
    budget = {c.name: c.u for c in m.budget}
    # 2 K outside 21 °C ± 5 K: (0.0005 % × 10 V + 0.0001 % × 20 V) × 2 K
    assert abs(budget["temperature"] * 3**0.5 - 1.4e-4) < 1e-12
    assert m.inputs["datasheet"]["tcal_degC"] == 21.0


def test_tcal_unknown():
    m = dmm(None).evaluate("dcv", make([10.0], "V"), range="20 V", at=AT, temperature="23 °C")
    assert "temperature-assumed" in codes(m) and m.usable


def test_resolution_not_stated():
    sdg = gm.Instrument(
        gm.datasheet("gumeasure:siglent.SDG6052X"),
        "S",
        (
            gm.Calibration(
                "SDG6052X", "S", "C", "lab", False, date(2026, 1, 1), date(2027, 1, 1), None
            ),
        ),
        modes={},
    )
    m = sdg.evaluate("output.dc", make([5.0], "V"), at=AT, temperature="23 °C")
    assert [c.name for c in m.budget] == ["accuracy"]
    assert abs(m.budget[0].u * 3**0.5 - 0.052) < 1e-12


def test_level_of_the_spectrum_analyser_in_mw():
    sa = gm.Instrument(
        gm.datasheet("gumeasure:siglent.SSA3032X_R"),
        "S",
        (
            gm.Calibration(
                "SSA3032X-R", "S", "C", "lab", False, date(2026, 1, 1), date(2027, 1, 1), None
            ),
        ),
        modes={},
    )
    m = sa.evaluate("level", make([-20.0], "dBm"), at=AT, temperature="25 °C", unit="mW")
    assert abs(m.value - 0.01) < 1e-15
    assert "linearised" in codes(m)

"""Functions in a logarithmic unit: readings in dBm, half-widths in dB.

The data sheet here is fictional and exists only for this test.
"""

import math
from datetime import UTC, date, datetime

import gumeasure as gm
from gumeasure.units import make, q

LEVEL_DS = gm.Datasheet(
    model="FICTIONAL-SA",
    vendor="none",
    source="Fictional data sheet for the tests of gumeasure",
    tcal=q("23 °C"),
    band=q("5 K"),
    intervals=(),
    functions={
        "level": gm.Function(
            unit="dBm",
            ranges=(
                gm.Range(
                    full_scale=q("20 dBm"),
                    resolution=q("0.01 dB"),
                    resolution_included=True,
                    accuracy=(gm.Accuracy(offset=q("0.7 dB")),),
                    tempco=gm.Accuracy(offset=q("0.01 dB")),
                ),
            ),
        )
    },
    checks=(gm.Check("level", q("20 dBm"), q("-30 dBm"), None, q("0.7 dB")),),
)
CAL = gm.Calibration(
    "FICTIONAL-SA", "S1", "C1", "lab", False, date(2026, 1, 1), date(2027, 1, 1), None
)
AT = datetime(2026, 6, 1, tzinfo=UTC)


def test_level_in_dbm():
    inst = gm.Instrument(LEVEL_DS, "S1", (CAL,), modes={})
    m = inst.evaluate("level", make([-30.0, -30.2], "dBm"), at=AT, temperature="33 °C")
    budget = {c.name: c.u for c in m.budget}
    assert m.unit == "dBm" and abs(m.value + 30.1) < 1e-12
    assert abs(budget["accuracy"] - 0.7 / 3**0.5) < 1e-12
    assert abs(budget["temperature"] - 0.05 / 3**0.5) < 1e-12
    assert [i.code for i in m.issues] == []


def test_level_overrange_is_above_full_scale():
    inst = gm.Instrument(LEVEL_DS, "S1", (CAL,), modes={})
    low = inst.evaluate("level", make([-60.0], "dBm"), at=AT, temperature="23 °C")
    high = inst.evaluate("level", make([25.0], "dBm"), at=AT, temperature="23 °C")
    assert "overrange" not in [i.code for i in low.issues]
    assert "overrange" in [i.code for i in high.issues]


def test_convert_log_linear_log():
    import json

    inst = gm.Instrument(LEVEL_DS, "S1", (CAL,), modes={})
    readings = make([-30.0, -30.2], "dBm")
    m = inst.evaluate("level", readings, at=AT, temperature="23 °C")
    mw = m.to("mW")
    assert abs(mw.value - 10 ** (-30.1 / 10)) < 1e-15
    assert abs(mw.u - mw.value * math.log(10) / 10 * m.u) < 1e-18
    assert [i.code for i in mw.issues] == ["linearised"]
    back = mw.to("dBm")
    assert abs(back.value - m.value) < 1e-12 and abs(back.u - m.u) < 1e-12
    record = json.loads(json.dumps(back.to_dict()))
    assert gm.recompute(record, readings) == back
    assert m.to("dBW").value == m.value - 30


def test_linear_readings_for_a_dbm_function_and_unit_argument():
    inst = gm.Instrument(LEVEL_DS, "S1", (CAL,), modes={})
    m = inst.evaluate("level", make([1.0, 1.0], "uW"), at=AT, unit="mW")
    assert abs(m.value - 1e-3) < 1e-15
    assert m.inputs["conversions"] == ["mW"]


def test_voltage_log_units():
    from gumeasure.units import convert, q

    assert abs(convert(0.0, "dBV", "dBµV")[0] - 120.0) < 1e-9
    assert abs(q("3 dBuV").to("dBV").magnitude + 117.0) < 1e-9


def test_log_functions_refuse_fractions():
    import dataclasses

    import pytest

    rng = LEVEL_DS.functions["level"].ranges[0]
    bad = dataclasses.replace(rng, accuracy=(gm.Accuracy(of_reading=0.01),))
    with pytest.raises(gm.ModelError, match="offset in dB"):
        dataclasses.replace(LEVEL_DS, functions={"level": gm.Function("dBm", (bad,))})


def test_cannot_convert_negative_to_log():
    import pytest

    from tests.test_examples import spd

    m = spd().evaluate("readback.current", make([-0.01], "A"), at=AT)
    with pytest.raises(gm.UsageError):
        m.to("dBm")

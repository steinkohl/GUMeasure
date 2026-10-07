"""Functions in a logarithmic unit: readings in dBm, half-widths in dB.

The data sheet here is fictional and exists only for this test.
"""

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

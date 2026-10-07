import json

import gumeasure as gm
from gumeasure.units import make

from .conftest import DATA, E1_READINGS, E2_AT, example_instrument


def test_recompute_after_json_round_trip():
    readings = make([7.0, 7.00002, 6.99999], "V")
    for mode, drift in [
        ("datasheet", None),
        ("calibration", "datasheet"),
        ("calibration", "history"),
    ]:
        m = example_instrument(mode, drift).evaluate("dcv", readings, at=E2_AT, temperature="31 °C")
        record = json.loads(json.dumps(m.to_dict()))
        again = gm.recompute(record, readings)
        assert again == m
        assert again == gm.Measurement.from_dict(record)


def test_recompute_in_other_unit_is_close():
    inst = gm.instrument("gumeasure:siglent.SPD1305X", [DATA / "SPD1305X-factory.toml"], modes={})
    m = inst.evaluate("readback.current", make(E1_READINGS, "A"), at=E2_AT)
    again = gm.recompute(m.to_dict(), make([1000 * r for r in E1_READINGS], "mA"))
    assert abs(again.u - m.u) <= 1e-9 * m.u


def test_budget_dict_format():
    m = example_instrument().evaluate("dcv", make([7.0], "V"), at=E2_AT)
    record = m.to_dict()
    assert set(record["budget"]["accuracy"]) == {"u", "type", "distribution", "source"}
    assert record["usable"] is True and record["U"] == m.U

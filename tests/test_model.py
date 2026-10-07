from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime

import pytest

import gumeasure as gm
from gumeasure.model import check_results
from gumeasure.units import frac, make, q

from .conftest import E2_AT, example_instrument


def test_checks_of_builtins_hold():
    for name in ("gumeasure:example.EXAMPLE_DMM", "gumeasure:siglent.SPD1305X"):
        results = check_results(gm.datasheet(name))
        assert results and all(ok for *_, ok in results)


def test_accuracy_length_must_match_intervals(example_ds):
    fn = example_ds.functions["dcv"]
    short = replace(fn.ranges[0], accuracy=fn.ranges[0].accuracy[:2])
    with pytest.raises(gm.ModelError, match=r"function.dcv.range\[0\].accuracy"):
        replace(example_ds, functions={"dcv": gm.Function("V", (short,))})


def test_wrong_dimension_in_python(example_ds):
    fn = example_ds.functions["dcv"]
    bad = replace(fn.ranges[0], resolution=q("10 µA"))
    with pytest.raises(gm.ModelError, match="resolution"):
        replace(example_ds, functions={"dcv": gm.Function("V", (bad,))})


def test_band_needs_kelvin(example_ds):
    with pytest.raises(gm.ModelError, match="band"):
        replace(example_ds, band=q("5 °C"))


def test_custom_datasheet(example_ds):
    class Doubled(gm.Datasheet):
        def half_width(self, function, range_, reading, interval_index):
            return 2 * super().half_width(function, range_, reading, interval_index)

    ds = Doubled(
        **{
            f: getattr(example_ds, f)
            for f in ("model", "vendor", "source", "tcal", "band", "intervals", "functions")
        }
    )
    assert ds.custom and not example_ds.custom
    cal = gm.load_calibration("examples/EX0001-2026.toml")
    inst = gm.Instrument(ds, "EX0001", (cal,), modes={})
    m = inst.evaluate("dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C")
    assert m.u == pytest.approx(2 * 1.703183294e-4, rel=1e-9)
    with pytest.raises(gm.UsageError, match="custom"):
        gm.evaluate(make([7.0], "V"), m.inputs)
    assert gm.evaluate(make([7.0], "V"), m.inputs, datasheet=ds) == m


def test_instrument_refuses_wrong_serial(cal_2026, example_ds):
    with pytest.raises(gm.UsageError, match="serial"):
        gm.Instrument(example_ds, "OTHER", (cal_2026,), modes={})


def test_instrument_refuses_wrong_model(cal_2026):
    with pytest.raises(gm.UsageError, match="model"):
        gm.Instrument(gm.datasheet("gumeasure:siglent.SPD1305X"), "EX0001", (cal_2026,), modes={})


def test_instrument_refuses_same_date(cal_2026, example_ds):
    twin = replace(cal_2026, certificate="OTHER")
    with pytest.raises(gm.UsageError, match="share a date"):
        gm.Instrument(example_ds, "EX0001", (cal_2026, twin), modes={})


def test_instrument_refuses_unknown_mode(example_ds):
    with pytest.raises(gm.UsageError):
        gm.Instrument(example_ds, "EX0001", (), modes={"dcv": "magic"})


def test_calibration_refuses_due_before_date():
    with pytest.raises(gm.ModelError, match="due"):
        gm.Calibration("M", "S", "C", "L", True, date(2026, 1, 2), date(2026, 1, 1), None)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"function": "acv"}, "no function"),
        ({"range": "100 V"}, "no range"),
        ({"at": datetime(2026, 9, 18)}, "timezone"),
        ({"readings": make([7.0], "A")}, "dimension"),
        ({"readings": [7.0]}, "quantity"),
        ({"readings": make([], "V")}, "empty"),
        ({"readings": make([float("nan")], "V")}, "finite"),
    ],
)
def test_wrong_use_raises(kwargs, match):
    args = {"function": "dcv", "readings": make([7.0], "V"), "range": None, "at": E2_AT}
    args.update(kwargs)
    with pytest.raises(gm.UsageError, match=match):
        example_instrument().evaluate(args.pop("function"), args.pop("readings"), **args)


def test_range_required_with_several_ranges(example_ds):
    rng = example_ds.functions["dcv"].ranges[0]
    big = replace(rng, full_scale=q("100 V"), resolution=q("100 µV"))
    ds = replace(example_ds, functions={"dcv": gm.Function("V", (rng, big))}, checks=())
    inst = gm.Instrument(ds, "X", (), modes={})
    with pytest.raises(gm.UsageError, match="Give the range"):
        inst.evaluate("dcv", make([7.0], "V"), at=E2_AT)
    assert (
        inst.evaluate("dcv", make([7.0], "V"), range="100 V", at=E2_AT).inputs["datasheet"][
            "range"
        ]["full_scale"]
        == 100.0
    )


def test_as_found_reported_by_check_not_by_evaluate(cal_2026, example_ds):
    point = replace(cal_2026.points[0], deviation_as_found=q("0.40 mV"))
    cal = replace(cal_2026, points=(point, cal_2026.points[1]))
    inst = gm.Instrument(
        example_ds, "EX0001", (cal,), modes={"dcv": "calibration"}, drift={"dcv": "datasheet"}
    )
    assert [i.code for i in inst.check()] == ["certificate-out-of-spec"]
    assert inst.evaluate("dcv", make([7.0], "V"), at=E2_AT, temperature="23 °C").usable


def test_measurement_round_trip():
    m = example_instrument().evaluate("dcv", make([7.0, 7.00001], "V"), at=E2_AT)
    assert gm.Measurement.from_dict(m.to_dict()) == m
    assert frac("1 %") == 0.01

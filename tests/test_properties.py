"""Property tests with hypothesis."""

from __future__ import annotations

import json
from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

import gumeasure as gm
from gumeasure.model import linear_half_width
from gumeasure.units import make

from .conftest import E2_AT, example_instrument

INSTRUMENTS = {
    (mode, drift): example_instrument(mode, drift)
    for mode, drift in [
        ("datasheet", None),
        ("calibration", "datasheet"),
        ("calibration", "history"),
    ]
}
readings_v = st.lists(
    st.floats(min_value=-10, max_value=10, allow_nan=False), min_size=1, max_size=20
)
setup = st.sampled_from(sorted(INSTRUMENTS, key=str))
days = st.integers(min_value=0, max_value=364)
temps = st.one_of(st.none(), st.floats(min_value=-20, max_value=60))


@settings(max_examples=60, deadline=None)
@given(readings_v, setup, days, temps)
def test_u_not_negative(values, which, day, temp):
    m = INSTRUMENTS[which].evaluate(
        "dcv",
        make(values, "V"),
        at=E2_AT + timedelta(days=day - 200),
        temperature=None if temp is None else make(temp, "degC"),
    )
    assert m.u >= 0
    assert all(c.u >= 0 for c in m.budget)


@given(
    st.floats(0, 1e-2),
    st.floats(0, 1e-2),
    st.floats(0, 1),
    st.integers(0, 100),
    st.floats(-100, 100),
    st.floats(-100, 100),
)
def test_half_width_rises_with_reading(of_reading, of_range, offset, counts, x1, x2):
    lo, hi = sorted((abs(x1), abs(x2)))
    a = linear_half_width(of_reading, of_range, offset, counts, lo, 100, 1e-3)
    b = linear_half_width(of_reading, of_range, offset, counts, hi, 100, 1e-3)
    assert a <= b


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(min_value=0.001, max_value=9.9), min_size=1, max_size=10), setup)
def test_millivolt_and_volt_agree(values, which):
    inst = INSTRUMENTS[which]
    a = inst.evaluate("dcv", make(values, "V"), at=E2_AT)
    b = inst.evaluate("dcv", make([1000 * v for v in values], "mV"), at=E2_AT)
    assert abs(a.u - b.u) <= 1e-9 * max(a.u, 1e-300)
    assert abs(a.value - b.value) <= 1e-9 * max(abs(a.value), 1e-12)


@settings(max_examples=60, deadline=None)
@given(readings_v, setup, temps)
def test_recompute_equals_original(values, which, temp):
    readings = make(values, "V")
    m = INSTRUMENTS[which].evaluate(
        "dcv", readings, at=E2_AT, temperature=None if temp is None else make(temp, "degC")
    )
    assert gm.recompute(json.loads(json.dumps(m.to_dict())), readings) == m

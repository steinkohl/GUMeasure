"""evaluate reads no clock and no files."""

import builtins
import time

import pytest

import gumeasure as gm
from gumeasure.units import make

from .conftest import E2_AT, example_instrument


def test_evaluate_reads_no_clock_and_no_file(monkeypatch):
    m = example_instrument("calibration", "history").evaluate(
        "dcv", make([7.0, 7.00001], "V"), at=E2_AT
    )
    readings = make([7.0, 7.00001], "V")
    gm.evaluate(readings, m.inputs)  # warm up lazy imports of pint and pydantic

    def forbidden(*args, **kwargs):
        raise AssertionError("evaluate must not use the clock or files")

    for name in ("time", "time_ns", "monotonic", "perf_counter", "localtime", "gmtime"):
        monkeypatch.setattr(time, name, forbidden)
    monkeypatch.setattr(builtins, "open", forbidden)
    assert gm.evaluate(readings, m.inputs) == m


def test_inputs_of_another_format_refused():
    with pytest.raises(gm.UsageError):
        gm.evaluate(make([1.0], "V"), {"format": "something/9"})

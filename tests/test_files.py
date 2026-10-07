from __future__ import annotations

from pathlib import Path

import pytest

import gumeasure as gm
from gumeasure.files import json_schema_text, load, load_datasheet, schema_path

from .conftest import EXAMPLES

DS = (EXAMPLES / "EXAMPLE-DMM.toml").read_text(encoding="utf-8")
CAL = (EXAMPLES / "EX0001-2026.toml").read_text(encoding="utf-8")


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "file.toml"
    path.write_text(text, encoding="utf-8")
    return path


def refused(tmp_path: Path, text: str) -> gm.FileFormatError:
    with pytest.raises(gm.FileFormatError) as info:
        load(write(tmp_path, text))
    assert "file.toml" in str(info.value)
    return info.value


def test_examples_load():
    assert isinstance(load(EXAMPLES / "EXAMPLE-DMM.toml"), gm.Datasheet)
    cal = load(EXAMPLES / "EX0001-2026.toml")
    assert isinstance(cal, gm.Calibration)
    assert cal.origin is not None and len(cal.origin.sha256 or "") == 64


def test_example_equals_builtin():
    assert load_datasheet(EXAMPLES / "EXAMPLE-DMM.toml") == gm.datasheet(
        "gumeasure:example.EXAMPLE_DMM"
    )


def test_missing_unit(tmp_path):
    err = refused(tmp_path, DS.replace('full_scale          = "10 V"', 'full_scale = "10"'))
    assert err.key == "function.dcv.range[0].full_scale"
    assert "missing unit" in str(err)


def test_wrong_dimension(tmp_path):
    err = refused(tmp_path, DS.replace('"10 µV"', '"10 µA"'))
    assert err.key == "function.dcv.range[0].resolution"


def test_unknown_key(tmp_path):
    err = refused(tmp_path, DS.replace("vendor    =", 'colour = "red"\nvendor    ='))
    assert err.key == "colour"
    assert "unknown key" in str(err)


def test_missing_key(tmp_path):
    err = refused(tmp_path, DS.replace('vendor    = "Example Instruments"\n', ""))
    assert err.key == "vendor"


def test_wrong_schema_version(tmp_path):
    err = refused(tmp_path, DS.replace("gumeasure.datasheet/1", "gumeasure.datasheet/2"))
    assert err.key == "schema"


def test_accuracy_not_matching_intervals(tmp_path):
    err = refused(
        tmp_path,
        DS.replace('intervals = ["24 h", "90 d", "1 year"]', 'intervals = ["24 h", "1 year"]'),
    )
    assert err.key == "function.dcv.range[0].accuracy"


def test_fraction_without_percent(tmp_path):
    err = refused(tmp_path, DS.replace('of_reading = "0.0015 %"', 'of_reading = "0.000015"'))
    assert err.key == "function.dcv.range[0].accuracy[0].of_reading"


def test_deviation_sign(tmp_path):
    err = refused(tmp_path, CAL.replace('"indication - reference"', '"reference - indication"'))
    assert err.key == "deviation_sign"


def test_duplicate_point(tmp_path):
    err = refused(tmp_path, CAL.replace('reference = "10 V"', 'reference = "5 V"'))
    assert err.key == "point[1]"


def test_not_toml(tmp_path):
    refused(tmp_path, "this is = = not toml")


@pytest.mark.parametrize("kind", ["datasheet", "calibration"])
def test_committed_schema_is_current(kind):
    assert schema_path(kind).read_text(encoding="utf-8") == json_schema_text(kind)

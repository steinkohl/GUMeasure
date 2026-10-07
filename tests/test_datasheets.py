"""Every built-in data sheet: TOML twin equals the Python object and every check holds."""

from pathlib import Path

import pytest

import gumeasure as gm
from gumeasure.files import load_datasheet
from gumeasure.model import check_results
from gumeasure.registry import BUILTIN

TWINS = Path(gm.__file__).parent / "datasheets"


def twin_of(ds: gm.Datasheet) -> Path:
    return TWINS / f"{ds.model}.toml"


@pytest.mark.parametrize("name", BUILTIN)
def test_twin_equals_object(name):
    ds = gm.datasheet(name)
    assert load_datasheet(twin_of(ds)) == ds


@pytest.mark.parametrize("name", BUILTIN)
def test_checks_hold(name):
    ds = gm.datasheet(name)
    results = check_results(ds)
    # Functions whose accuracy comes from settings-dependent specifications have their worked
    # examples in test_builtin_use.py.
    plain = [f for f in ds.functions.values() if not f.specs]
    assert results or not plain
    assert all(ok for *_, ok in results), [(i, str(got)) for i, _, got, ok in results if not ok]


@pytest.mark.parametrize("name", BUILTIN)
def test_source_given(name):
    ds = gm.datasheet(name)
    assert ds.source.strip()


def test_every_twin_is_registered():
    models = {gm.datasheet(n).model for n in BUILTIN}
    assert {p.stem for p in TWINS.glob("*.toml")} == models

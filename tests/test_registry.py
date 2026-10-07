import pytest

import gumeasure as gm
from gumeasure.registry import BUILTIN

from .conftest import EXAMPLES


def test_builtin_names():
    for name in BUILTIN:
        ds = gm.datasheet(name)
        assert ds.origin is not None
        assert ds.origin.kind == "builtin" and ds.origin.version == gm.__version__


def test_file_name():
    ds = gm.datasheet(str(EXAMPLES / "EXAMPLE-DMM.toml"))
    assert ds.origin is not None and ds.origin.kind == "file"


@pytest.mark.parametrize(
    "name",
    ["gumeasure:example.NOPE", "gumeasure:nope.X", "gumeasure:bad", "no-such-entry-point", ""],
)
def test_unknown_names(name):
    with pytest.raises(gm.UsageError):
        gm.datasheet(name)


def test_instrument_takes_serial_from_certificates():
    inst = gm.instrument("gumeasure:example.EXAMPLE_DMM", [EXAMPLES / "EX0001-2026.toml"], modes={})
    assert inst.serial == "EX0001"
    with pytest.raises(gm.UsageError):
        gm.instrument("gumeasure:example.EXAMPLE_DMM", [], modes={})

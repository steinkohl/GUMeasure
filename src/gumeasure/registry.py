"""Data sheets by name, and instruments from names and files.

A name is one of three things. There is no search order and no fallback.

- "gumeasure:<module>.<OBJECT>": a built-in data sheet in gumeasure.datasheets.<module>.
- a path ending in ".toml": a data sheet file.
- anything else: an entry point of that name in the group "gumeasure.datasheets".
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from importlib.metadata import entry_points
from pathlib import Path

from gumeasure._version import __version__
from gumeasure.errors import UsageError
from gumeasure.files import load_calibration, load_datasheet
from gumeasure.model import Calibration, Datasheet, Instrument, Origin

GROUP = "gumeasure.datasheets"
PREFIX = "gumeasure:"
BUILTIN = ("gumeasure:example.EXAMPLE_DMM", "gumeasure:siglent.SPD1305X")
_BUILTIN_NAME = re.compile(r"gumeasure:(?P<module>[a-z_][a-z0-9_]*)\.(?P<object>[A-Za-z_]\w*)")


def datasheet(name: str) -> Datasheet:
    """Load a data sheet by its explicit name."""
    if not isinstance(name, str) or not name:
        raise UsageError(f"a data sheet name must be a string, got {name!r}")
    if name.startswith(PREFIX):
        return _builtin(name)
    if name.endswith(".toml"):
        return load_datasheet(name)
    return _entry_point(name)


_by_name = datasheet


def _builtin(name: str) -> Datasheet:
    match = _BUILTIN_NAME.fullmatch(name)
    if match is None:
        raise UsageError(f"{name!r} is not a built-in name such as {BUILTIN[1]!r}")
    try:
        module = importlib.import_module(f"gumeasure.datasheets.{match['module']}")
        obj = getattr(module, match["object"])
    except (ImportError, AttributeError):
        raise UsageError(
            f"no built-in data sheet {name!r}. Built-in: {', '.join(BUILTIN)}"
        ) from None
    if not isinstance(obj, Datasheet):
        raise UsageError(f"{name!r} is not a data sheet")
    return replace(obj, origin=Origin(name=name, kind="builtin", version=__version__))


def _entry_point(name: str) -> Datasheet:
    found = [ep for ep in entry_points(group=GROUP) if ep.name == name]
    if not found:
        known = sorted(ep.name for ep in entry_points(group=GROUP))
        raise UsageError(
            f"no data sheet {name!r}. Use 'gumeasure:<module>.<OBJECT>', a .toml path, "
            f"or an entry point of group {GROUP}. Entry points: {', '.join(known) or 'none'}"
        )
    ep = found[0]
    obj = ep.load()
    if not isinstance(obj, Datasheet):
        raise UsageError(f"entry point {name!r} is not a data sheet")
    version = ep.dist.version if ep.dist is not None else None
    return replace(obj, origin=Origin(name=name, kind="entry-point", version=version))


def instrument(
    datasheet: str | Datasheet,
    calibrations: Sequence[str | Path | Calibration] = (),
    *,
    modes: Mapping[str, str],
    drift: Mapping[str, str] | None = None,
    serial: str | None = None,
) -> Instrument:
    """An Instrument from a data sheet name and certificate files.

    Without `serial` the serial of the certificates is used. They must agree.
    """
    ds = _by_name(datasheet) if isinstance(datasheet, str) else datasheet
    cals = tuple(c if isinstance(c, Calibration) else load_calibration(c) for c in calibrations)
    if serial is None:
        serials = sorted({c.serial for c in cals})
        if len(serials) != 1:
            raise UsageError(
                "give the serial" if not serials else f"certificates of several serials: {serials}"
            )
        serial = serials[0]
    return Instrument(
        datasheet=ds, serial=serial, calibrations=cals, modes=modes, drift=dict(drift or {})
    )

"""Built-in data sheets.

Each module holds data sheets as module-level objects. Each data sheet has a TOML twin in this
directory, which gives an equal object. Most modules load their objects from the twin, which is
the form closest to the tables of the vendor. Load them by name, such as
`gumeasure.datasheet("gumeasure:siglent.SDM3065X")`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from gumeasure.model import Datasheet

HERE = Path(__file__).parent


def from_twin(model: str) -> Datasheet:
    """The data sheet of a model from its TOML twin in this directory."""
    from gumeasure.files import load_datasheet

    return replace(load_datasheet(HERE / f"{model}.toml"), origin=None)

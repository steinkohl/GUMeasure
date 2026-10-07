from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import gumeasure as gm

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"
DATA = Path(__file__).parent / "data"
CEST = timezone(timedelta(hours=2))
E2_AT = datetime(2026, 9, 18, tzinfo=CEST)

E1_READINGS = [0.182, 0.183, 0.183, 0.182, 0.184, 0.183, 0.182, 0.183, 0.183, 0.182]


def rel(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol * abs(b)


@pytest.fixture
def example_ds() -> gm.Datasheet:
    return gm.datasheet("gumeasure:example.EXAMPLE_DMM")


@pytest.fixture
def cal_2026() -> gm.Calibration:
    return gm.load_calibration(EXAMPLES / "EX0001-2026.toml")


@pytest.fixture
def cal_2025() -> gm.Calibration:
    return gm.load_calibration(EXAMPLES / "EX0001-2025.toml")


def example_instrument(
    mode: str = "datasheet",
    drift: str | None = None,
    files: tuple[str, ...] = ("EX0001-2025.toml", "EX0001-2026.toml"),
) -> gm.Instrument:
    return gm.instrument(
        "gumeasure:example.EXAMPLE_DMM",
        [EXAMPLES / f for f in files],
        modes={"dcv": mode},
        drift={"dcv": drift} if drift else {},
    )

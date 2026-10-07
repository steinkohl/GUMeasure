"""Worked example E2: EXAMPLE-DMM, dcv, 10 V range, one reading of 7 V, 200 days after the
calibration. Run with `uv run python examples/e2.py`.

EXAMPLE-DMM and its certificates are fictional.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import gumeasure as gm
from gumeasure.cli import render
from gumeasure.units import make

HERE = Path(__file__).parent
AT = datetime(2026, 9, 18, tzinfo=timezone(timedelta(hours=2)))

for mode, drift in [("datasheet", None), ("calibration", "datasheet")]:
    inst = gm.instrument(
        "gumeasure:example.EXAMPLE_DMM",
        [HERE / "EX0001-2025.toml", HERE / "EX0001-2026.toml"],
        modes={"dcv": mode},
        drift={"dcv": drift} if drift else {},
    )
    m = inst.evaluate("dcv", make([7.0], "V"), range="10 V", at=AT, temperature="23 °C")
    print(render(inst, "dcv", m))
    print()

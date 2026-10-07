"""gumeasure: measurement uncertainty according to the GUM for every reading of a lab instrument.

It combines the data sheet of the instrument model, the calibration certificate of the unit
and the scatter of the readings into a value with standard and expanded uncertainty and the
full uncertainty budget.
"""

from gumeasure._version import __version__
from gumeasure.errors import FileFormatError, GumeasureError, ModelError, UsageError
from gumeasure.evaluate import evaluate, recompute
from gumeasure.files import load_calibration
from gumeasure.model import (
    Accuracy,
    Calibration,
    CalPoint,
    Check,
    Contribution,
    Datasheet,
    Function,
    Instrument,
    Issue,
    Measurement,
    Origin,
    Range,
)
from gumeasure.registry import datasheet, instrument

__all__ = [
    "Accuracy",
    "CalPoint",
    "Calibration",
    "Check",
    "Contribution",
    "Datasheet",
    "FileFormatError",
    "Function",
    "GumeasureError",
    "Instrument",
    "Issue",
    "Measurement",
    "ModelError",
    "Origin",
    "Range",
    "UsageError",
    "__version__",
    "datasheet",
    "evaluate",
    "instrument",
    "load_calibration",
    "recompute",
]

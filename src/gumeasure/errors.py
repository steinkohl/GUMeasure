"""Exceptions of gumeasure.

Only wrong use raises. The state of an instrument is an Issue in the result.
"""

from __future__ import annotations

from collections.abc import Sequence


class GumeasureError(Exception):
    """Base class of all exceptions of gumeasure."""


class UsageError(GumeasureError, ValueError):
    """gumeasure was called in a way it does not support."""


class ModelError(GumeasureError, ValueError):
    """A data sheet or a calibration object breaks a rule of the data model.

    `problems` holds pairs of key path and message. The key paths use the names of the file
    format, such as `function.dcv.range[0].resolution`.
    """

    def __init__(self, what: str, problems: Sequence[tuple[str, str]]) -> None:
        self.what = what
        self.problems = list(problems)
        lines = [f"{key}: {message}" if key else message for key, message in self.problems]
        super().__init__(f"{what}: " + "; ".join(lines))


class FileFormatError(GumeasureError, ValueError):
    """A data sheet or calibration file could not be loaded.

    `path` is the file. `problems` holds pairs of key path and message. `key` is the first key.
    """

    def __init__(self, path: str, problems: Sequence[tuple[str, str]]) -> None:
        self.path = path
        self.problems = list(problems)
        self.key = self.problems[0][0] if self.problems else ""
        lines = [f"{path}: {key}: {msg}" if key else f"{path}: {msg}" for key, msg in self.problems]
        super().__init__("\n".join(lines))

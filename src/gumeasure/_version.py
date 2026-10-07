"""Version of the installed package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gumeasure")
except PackageNotFoundError:  # pragma: no cover, only when run from a source tree
    __version__ = "0+unknown"

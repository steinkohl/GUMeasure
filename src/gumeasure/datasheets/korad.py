"""Korad data sheets.

KC3405 is typed from the Korad KC series user manual named in its source and loaded from its
TOML twin. Check it against the document before a release.
"""

from gumeasure.datasheets import from_twin

KC3405 = from_twin("KC3405")

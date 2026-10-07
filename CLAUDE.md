# Conventions for gumeasure

- British spelling in code comments, docs and messages (characterisation, behaviour).
- Documentation in short, plain sentences. Few colons, semicolons and dashes. No double
  negatives.
- Never invent instrument data. Values of a real data sheet carry their source (document,
  revision, table) and are checked against the document before a release. Fictional data
  sheets say that they are fictional.
- `evaluate` reads no clock and no files. Everything it uses is in its arguments or in
  `inputs`.
- State of the instrument is an Issue, never an exception.
- Decisions of the design are marked `# D1` to `# D8`. Decisions taken without the owner are
  marked `# TODO: check this (Dnn)`. See docs/architecture.md, section 13.
- Every built-in data sheet has a TOML twin in `src/gumeasure/datasheets/` that gives an equal
  object. Add the name to `registry.BUILTIN`.
- After changing a file class in `files.py`, regenerate the schemas:
  `uv run gumeasure schema datasheet > src/gumeasure/schema/datasheet.schema.json` and the
  same for `calibration`.
- Before each commit: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src`,
  `uv run pytest`, `uv run gumeasure check src/gumeasure/datasheets examples`.

# gumeasure

gumeasure gives every reading of a lab instrument its measurement uncertainty according to the
GUM (JCGM 100). It combines three sources.

- The **data sheet** of the instrument model: accuracy per function and range.
- The **calibration certificate** of the unit: deviation and expanded uncertainty per
  calibration point.
- The **readings** themselves: scatter of repeated readings (Type A).

The result is a value with unit, standard and expanded uncertainty, and the full uncertainty
budget. Each contribution carries its standard uncertainty, type (A or B), distribution and
source. A result can be recomputed later from the readings and the recorded inputs alone.

gumeasure is independent of any instrument driver library. An optional module binds it to
[PyMeasure](https://pymeasure.readthedocs.io).

gumeasure does not decide verdicts, does not control instruments, does not store raw data and
does not schedule calibrations. It reports whether a calibration is valid at the time of a
reading.

## Install

```sh
uv add "gumeasure @ git+https://github.com/steinkohl/GUMeasure"
uv add "gumeasure[pymeasure] @ git+https://github.com/steinkohl/GUMeasure"   # with the PyMeasure binding
```

Python 3.11 or newer.

## First example

```python
from datetime import datetime, timezone
import gumeasure as gm
from gumeasure.units import make

inst = gm.instrument(
    "gumeasure:example.EXAMPLE_DMM",            # data sheet by name
    ["examples/EX0001-2026.toml"],              # calibration certificates of the unit
    modes={"dcv": "calibration"},               # "datasheet" or "calibration"
    drift={"dcv": "datasheet"},                 # "datasheet" or "history"
)
m = inst.evaluate("dcv", make([7.0], "V"), range="10 V",
                  at=datetime(2026, 9, 18, tzinfo=timezone.utc), temperature="23 °C")

m.value, m.u, m.U        # 6.999948, 1.221e-4, 2.442e-4  (V)
m.usable                 # True: no issue of severity "error"
m.to_dict()              # JSON-safe record with budget, issues and inputs
gm.recompute(m.to_dict(), make([7.0], "V")) == m   # True
```

EXAMPLE-DMM and its certificates are fictional. They exist for the tests and the
documentation.

On the command line:

```sh
gumeasure explain --datasheet gumeasure:example.EXAMPLE_DMM \
  --calibration examples/EX0001-2026.toml --function dcv --range "10 V" \
  --reading "7 V" --at 2026-09-18 --temperature "23 °C" --mode calibration --drift datasheet
gumeasure check src/gumeasure/datasheets examples     # check files and certificates
gumeasure schema datasheet                            # JSON Schema of the file format
```

## Two modes

- **datasheet**: the accuracy of the data sheet for the time since calibration, as a
  rectangular contribution. The value is the mean of the readings.
- **calibration**: the deviation of the certificate, interpolated at the reading, corrects the
  value. The contributions are the calibration uncertainty, the short-term accuracy of the data
  sheet and the drift since calibration. The drift comes from the data sheet columns or from
  the history of the certificates.

The state of the instrument never raises an exception. An expired calibration, an overrange
reading or a certificate out of specification is an `Issue` in the result. The caller decides
what follows from it.

## Files

Data sheets and certificates are TOML files. See [docs/files.md](docs/files.md) for every key.
A file starting with `#:schema <path>` gets completion and checking in editors with Taplo
(Even Better TOML in VS Code). The schemas are in `src/gumeasure/schema/`.

Data sheets can also be Python objects. Other packages register them under the entry point
group `gumeasure.datasheets`.

## Built-in data sheets

| Name | Instrument | State |
|---|---|---|
| `gumeasure:example.EXAMPLE_DMM` | fictional DMM | for the tests and documentation |
| `gumeasure:siglent.SPD1305X` | Siglent SPD1305X power supply | values to be checked against the data sheet before the first release |

## Architecture

See [docs/architecture.md](docs/architecture.md).

## Related work

- Fluke MET/CAL computes uncertainty at run time from accuracy files of the standards
  (commercial, closed, for calibration procedures).
- NIST rminstr-specs gives data sheet specifications of a few instruments as Python classes
  (no readings with budgets, no calibration certificates).
- GTC (MSL New Zealand), MetroloPy, uncertainties and METAS UncLib propagate uncertainty but
  know no instruments.
- PTB dcclib and pyDCC read digital calibration certificates (DCC). A later version of
  gumeasure may read DCCs as a second source of calibration data.

## Authorship and licence

gumeasure is designed by Felix Steinkohl. Parts of the code and the documentation were
generated with Claude (Anthropic) on the basis of this design.

Licensed under the MIT licence or the Apache License 2.0, at your choice. See
[LICENSE-MIT](LICENSE-MIT) and [LICENSE-APACHE](LICENSE-APACHE).

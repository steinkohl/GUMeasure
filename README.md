<p align="center">
  <img src="docs/logo/logo.svg" alt="gumeasure" width="420">
</p>

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

## With a PyMeasure instrument

```python
from pymeasure.instruments.siglenttechnologies import SPD1305X
from gumeasure.pymeasure import Measured

psu = Measured(SPD1305X("TCPIP::192.168.1.20::INSTR"),
               calibrations=["certificates/SPD1305X-2026.toml"],
               temperature="23 °C")

psu.ch_1.voltage_setpoint = 5        # passes through to PyMeasure
m = psu.ch_1.current                 # a Measurement instead of a float
print(m)                             # 0.182 A ± 12.19 mA (k = 2)
s = psu.ch_1.measure("current", n=10, interval="20 ms")
s.measurement, s.readings, s.times   # result, raw readings and their times
```

`Measured` knows the data sheet and the measured properties of the PyMeasure classes in
`gumeasure.pymeasure.BINDINGS`. For other classes, give `datasheet` and `properties`, or
register a `Binding`. `temperature` may also be a function that reads a sensor.

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

## dB and linear units

A function may be in a logarithmic unit such as dBm, dBV or dBµV. Its accuracy is then an
offset in dB. Readings may come in any unit of the same quantity, such as mW for a dBm
function. A result converts between units, also between dB and linear units:

```python
m = sa.evaluate("level", make([-30.0, -30.2], "dBm"), at=at)   # -30.1 dBm ± 0.8327 dB (k = 2)
m.to("mW")                                                     # 0.000977237221 mW ± 187.4 nW (k = 2)
inst.evaluate(..., unit="mW")                                  # the same in one step
```

Each contribution is multiplied by the sensitivity coefficient at the value. Between dB and
linear units this is a first-order approximation. The result carries the note `linearised`.
The conversion is recorded in `inputs`, so `recompute` gives the converted result.

Some instruments state their accuracy in parts that depend on their settings. A spectrum
analyser has an absolute accuracy at 50 MHz, a frequency response, attenuator and RBW
switching errors, and a total accuracy for one set of conditions. Give the settings, and
gumeasure uses the valid specification with the smallest uncertainty:

```python
sa.evaluate("level", make([-20.0], "dBm"), at=at, settings={
    "frequency": "50 MHz", "attenuation": "20 dB", "rbw": "1 kHz", "vbw": "1 kHz",
    "preamp": False, "detector": "positive-peak"})             # ± 0.41 dB instead of ± 0.71 dB
```

A setting that is not given counts against you: its terms are included. Without a valid
specification the result has the error `no-specification`, with the conditions that failed.

pint's own `dBu` is dB relative to 1 µW. gumeasure adds `dBV`, `dBmV` and `dBµV` (also `dBuV`).

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
| `gumeasure:korad.KC3405` | Korad KC3405 power supply, setup accuracy | typed from the user manual |
| `gumeasure:siglent.SDG6022X`, `SDG6032X`, `SDG6052X` | Siglent SDG6000X generators: frequency, DC, amplitude at 10 kHz | typed from Date Sheet-2018.04 |
| `gumeasure:siglent.SDL1020X` | Siglent SDL1020X electronic load: readback and settings | typed from DataSheet-2019.10 |
| `gumeasure:siglent.SDM3065X`, `SDM3065X_SC` | Siglent SDM3065X DMM: DCV, DCI, resistance, ACV, ACI, frequency, capacitance | typed from DataSheet-2021.05 |
| `gumeasure:siglent.SPD1305X` | Siglent SPD1305X power supply | values from agnostibench |
| `gumeasure:siglent.SSA3032X_R` | Siglent SSA3032X-R spectrum analyser: level accuracy by frequency, attenuation, RBW and preamp | typed from DS0703R_E02F |

Every value typed from a document must be checked against it before a release. Functions
measured in several frequency bands, such as AC voltage, have one function per band, such as
`acv.10Hz-20kHz`. Functions named `setting.*` or `output.*` give the accuracy of a set value.

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

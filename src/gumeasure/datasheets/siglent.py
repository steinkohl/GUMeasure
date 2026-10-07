"""Siglent data sheets.

SPD1305X: values taken over from agnostibench. They must be checked against the Siglent
SPD1000X data sheet DS0501X before the first release. The worked examples are computed by hand
from these values, not taken from the data sheet. Its TOML twin is SPD1305X.toml.
"""

from gumeasure.model import Accuracy, Check, Datasheet, Function, Range
from gumeasure.units import frac, q

SPD1305X = Datasheet(
    model="SPD1305X",
    vendor="Siglent Technologies",
    source=(
        "Siglent SPD1000X data sheet DS0501X, valid at 25 ± 5 °C. Values taken over from "
        "agnostibench, to be checked against the data sheet before the first release"
    ),
    tcal=q("25 °C"),
    band=q("5 K"),
    intervals=(),
    functions={
        "readback.voltage": Function(
            unit="V",
            ranges=(
                Range(
                    full_scale=q("30 V"),
                    resolution=q("1 mV"),
                    # D7: added on top of the accuracy, as agnostibench does today.
                    resolution_included=False,
                    accuracy=(Accuracy(of_reading=frac("0.03 %"), offset=q("10 mV")),),
                ),
            ),
        ),
        "readback.current": Function(
            unit="A",
            ranges=(
                Range(
                    full_scale=q("5 A"),
                    resolution=q("1 mA"),
                    # D7: added on top of the accuracy, as agnostibench does today.
                    resolution_included=False,
                    accuracy=(Accuracy(of_reading=frac("0.3 %"), offset=q("10 mA")),),
                ),
            ),
        ),
    },
    checks=(
        # Computed by hand: 0.03 % × 12 V + 10 mV = 13.6 mV.
        Check(
            function="readback.voltage",
            range=q("30 V"),
            reading=q("12 V"),
            interval=None,
            half_width=q("13.6 mV"),
        ),
        # Computed by hand: 0.3 % × 2 A + 10 mA = 16 mA.
        Check(
            function="readback.current",
            range=q("5 A"),
            reading=q("2 A"),
            interval=None,
            half_width=q("16 mA"),
        ),
    ),
)

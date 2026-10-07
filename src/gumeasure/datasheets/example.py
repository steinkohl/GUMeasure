"""EXAMPLE-DMM.

A fictional data sheet. It exists for the tests and the documentation of gumeasure. No real
instrument has these values. Its TOML twin is EXAMPLE-DMM.toml.
"""

from gumeasure.model import Accuracy, Check, Datasheet, Function, Range
from gumeasure.units import frac, q

EXAMPLE_DMM = Datasheet(
    model="EXAMPLE-DMM",
    vendor="Example Instruments",
    source="Fictional data sheet for the tests and documentation of gumeasure",
    tcal=q("23 °C"),
    band=q("5 K"),
    intervals=(q("24 h"), q("90 d"), q("1 year")),
    functions={
        "dcv": Function(
            unit="V",
            ranges=(
                Range(
                    full_scale=q("10 V"),
                    resolution=q("10 µV"),
                    resolution_included=True,
                    accuracy=(
                        Accuracy(of_reading=frac("0.0015 %"), of_range=frac("0.0004 %")),
                        Accuracy(of_reading=frac("0.0025 %"), of_range=frac("0.0005 %")),
                        Accuracy(of_reading=frac("0.0035 %"), of_range=frac("0.0005 %")),
                    ),
                    tempco=Accuracy(of_reading=frac("0.0005 %"), of_range=frac("0.0001 %")),
                ),
            ),
        ),
    },
    checks=(
        Check(
            function="dcv",
            range=q("10 V"),
            reading=q("7 V"),
            interval=q("1 year"),
            half_width=q("0.295 mV"),
        ),
    ),
)

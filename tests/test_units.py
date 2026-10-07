import pytest

from gumeasure.units import frac, parse_fraction, parse_quantity, q


def test_offset_unit_parses():
    assert q("23 °C").to("degC").magnitude == 23.0
    assert q("23 degC") == q("23 °C")


@pytest.mark.parametrize("text", ["10 µV", "10 uV", "1 year", "24 h", "90 d", "-5e-3 A"])
def test_quantities_parse(text):
    assert parse_quantity(text).magnitude != 0


def test_fractions():
    assert frac("0.0015 %") == pytest.approx(1.5e-5)
    assert frac("5 ppm") == pytest.approx(5e-6)


@pytest.mark.parametrize("text", ["10", "abc V", "10 nosuchunit", 10.0, None])
def test_quantity_refused(text):
    with pytest.raises(ValueError):
        parse_quantity(text)


@pytest.mark.parametrize("text", ["0.0003", 0.0003, "3 V", "0.1"])
def test_fraction_refused(text):
    with pytest.raises(ValueError):
        parse_fraction(text)

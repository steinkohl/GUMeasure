"""Use of the built-in data sheets of real instruments, with fictional certificates."""

from datetime import UTC, date, datetime

import gumeasure as gm
from gumeasure.units import make

AT = datetime(2026, 6, 1, tzinfo=UTC)


def dmm(temperature: str | None = "23 °C") -> gm.Instrument:
    from gumeasure.units import q

    cal = gm.Calibration(
        "SDM3065X",
        "FICTIONAL",
        "TEST-1",
        "Fictional laboratory",
        True,
        date(2026, 1, 1),
        date(2027, 1, 1),
        None if temperature is None else q(temperature),
    )
    return gm.Instrument(gm.datasheet("gumeasure:siglent.SDM3065X"), "FICTIONAL", (cal,), modes={})


def codes(m: gm.Measurement) -> list[str]:
    return [i.code for i in m.issues]


def test_ten_percent_over_range_is_covered():
    m = dmm().evaluate("dcv", make([21.5], "V"), range="20 V", at=AT, temperature="23 °C")
    assert "overrange" not in codes(m)
    m = dmm().evaluate("dcv", make([22.5], "V"), range="20 V", at=AT, temperature="23 °C")
    assert "overrange" in codes(m)
    m = dmm().evaluate("dcv", make([1000.5], "V"), range="1000 V", at=AT, temperature="23 °C")
    assert "overrange" in codes(m)


def test_tcal_from_the_certificate():
    m = dmm("21 °C").evaluate("dcv", make([10.0], "V"), range="20 V", at=AT, temperature="28 °C")
    budget = {c.name: c.u for c in m.budget}
    # 2 K outside 21 °C ± 5 K: (0.0005 % × 10 V + 0.0001 % × 20 V) × 2 K
    assert abs(budget["temperature"] * 3**0.5 - 1.4e-4) < 1e-12
    assert m.inputs["datasheet"]["tcal_degC"] == 21.0


def test_tcal_unknown():
    m = dmm(None).evaluate("dcv", make([10.0], "V"), range="20 V", at=AT, temperature="23 °C")
    assert "temperature-assumed" in codes(m) and m.usable


def test_resolution_not_stated():
    sdg = gm.Instrument(
        gm.datasheet("gumeasure:siglent.SDG6052X"),
        "S",
        (
            gm.Calibration(
                "SDG6052X", "S", "C", "lab", False, date(2026, 1, 1), date(2027, 1, 1), None
            ),
        ),
        modes={},
    )
    m = sdg.evaluate("output.dc", make([5.0], "V"), at=AT, temperature="23 °C")
    assert [c.name for c in m.budget] == ["accuracy"]
    assert abs(m.budget[0].u * 3**0.5 - 0.052) < 1e-12


def analyser() -> gm.Instrument:
    cal = gm.Calibration(
        "SSA3032X-R", "S", "C", "lab", False, date(2026, 1, 1), date(2027, 1, 1), None
    )
    return gm.Instrument(gm.datasheet("gumeasure:siglent.SSA3032X_R"), "S", (cal,), modes={})


REFERENCE = {
    "preamp": False,
    "attenuation": "20 dB",
    "rbw": "1 kHz",
    "vbw": "1 kHz",
    "detector": "positive-peak",
    "frequency": "50 MHz",
}


def level(dbm: float, **settings: object) -> gm.Measurement:
    return analyser().evaluate(
        "level", make([dbm], "dBm"), at=AT, temperature="25 °C", settings={**REFERENCE, **settings}
    )


def budget(m: gm.Measurement) -> dict[str, float]:
    return {c.name: c.u for c in m.budget}


def test_ssa_at_the_reference_point_uses_the_absolute_accuracy():
    # ±0.4 dB at 95 %: u = 0.4 dB / 1.96
    m = level(-20.0)
    assert budget(m) == {"absolute amplitude accuracy": 0.4 / 1.96}
    assert m.usable


def test_ssa_away_from_50_mhz_uses_the_total_accuracy():
    # Absolute accuracy and frequency response: sqrt((0.4/1.96)² + (0.8/√3)²) = 0.505 dB.
    # Total accuracy: 0.7/1.96 = 0.357 dB is smaller, and valid.
    assert budget(level(-20.0, frequency="1 GHz")) == {"total amplitude accuracy": 0.7 / 1.96}
    assert budget(level(-35.0, frequency="1 GHz")) == {"total amplitude accuracy": 0.7 / 1.96}


def test_ssa_other_attenuation_adds_the_switching_terms():
    b = budget(level(-20.0, frequency="1 GHz", attenuation="10 dB"))
    assert abs(b["absolute amplitude accuracy"] - 0.4 / 1.96) < 1e-15
    assert abs(b["frequency response"] - 0.8 / 3**0.5) < 1e-15
    assert abs(b["input attenuation switching"] - 0.5 / 3**0.5) < 1e-15
    assert len(b) == 3


def test_ssa_rbw_10_khz_and_100_khz():
    b = budget(level(-20.0, rbw="10 kHz", vbw="10 kHz"))
    assert set(b) == {"absolute amplitude accuracy", "RBW switching"}
    b = budget(level(-20.0, rbw="100 kHz", vbw="100 kHz"))
    assert set(b) == {
        "absolute amplitude accuracy",
        "RBW switching",
        "RBW switching from 1 kHz to 10 kHz",
    }


def test_ssa_without_a_valid_specification():
    m = level(-30.0, rbw="100 kHz")
    assert "no-specification" in codes(m) and not m.usable
    m = analyser().evaluate("level", make([-20.0], "dBm"), at=AT, temperature="25 °C")
    assert "no-specification" in codes(m)


def test_ssa_missing_setting_is_assumed_conservatively():
    given = {"preamp": False, "detector": "positive-peak", "frequency": "50 MHz"}
    m = analyser().evaluate(
        "level", make([-20.0], "dBm"), at=AT, temperature="25 °C", settings=given
    )
    assert set(budget(m)) == {
        "absolute amplitude accuracy",
        "input attenuation switching",
        "RBW switching",
        "RBW switching from 1 kHz to 10 kHz",
    }
    assert codes(m).count("setting-assumed") == 3


def test_ssa_settings_are_checked_and_recorded():
    import json

    import pytest

    with pytest.raises(gm.UsageError, match="unknown setting"):
        level(-20.0, span="1 MHz")
    with pytest.raises(gm.UsageError):
        level(-20.0, preamp="no")
    with pytest.raises(gm.UsageError):
        level(-20.0, rbw="1 V")
    m = level(-20.0, frequency="1 GHz")
    assert m.inputs["settings"]["frequency"] == 1e9
    assert gm.recompute(json.loads(json.dumps(m.to_dict())), make([-20.0], "dBm")) == m


def test_ssa_calibration_mode_is_refused():
    import pytest

    cal = analyser().calibrations
    with pytest.raises(gm.UsageError, match="Calibration mode"):
        gm.Instrument(
            gm.datasheet("gumeasure:siglent.SSA3032X_R"), "S", cal, modes={"level": "calibration"}
        )


def test_level_of_the_spectrum_analyser_in_mw():
    m = analyser().evaluate(
        "level", make([-20.0], "dBm"), at=AT, temperature="25 °C", unit="mW", settings=REFERENCE
    )
    assert abs(m.value - 0.01) < 1e-15
    assert "linearised" in codes(m)

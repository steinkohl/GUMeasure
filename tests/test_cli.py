from gumeasure.cli import main
from gumeasure.files import json_schema_text

from .conftest import DATA, EXAMPLES, ROOT


def test_check_examples_and_builtins(capsys):
    assert main(["check", str(ROOT / "src/gumeasure/datasheets"), str(EXAMPLES)]) == 0
    assert "0 errors" in capsys.readouterr().out


def test_check_finds_out_of_spec(capsys):
    code = main(
        ["check", str(EXAMPLES / "EXAMPLE-DMM.toml"), str(DATA / "EX0001-out-of-spec.toml")]
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "error certificate-out-of-spec" in out and "EX0001-out-of-spec.toml" in out


def test_check_needs_datasheet(capsys):
    assert main(["check", str(EXAMPLES / "EX0001-2026.toml")]) == 1
    assert "datasheet-missing" in capsys.readouterr().out
    assert (
        main(
            [
                "check",
                str(EXAMPLES / "EX0001-2026.toml"),
                "--datasheet",
                "gumeasure:example.EXAMPLE_DMM",
            ]
        )
        == 0
    )


def test_check_reports_bad_file(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text('schema = "gumeasure.datasheet/1"\nmodel = "X"\n', encoding="utf-8")
    assert main(["check", str(bad)]) == 1
    assert "file-format" in capsys.readouterr().out


def test_schema(capsys):
    assert main(["schema", "datasheet"]) == 0
    assert capsys.readouterr().out == json_schema_text("datasheet")


def test_explain(capsys):
    code = main(
        [
            "explain",
            "--datasheet",
            "gumeasure:example.EXAMPLE_DMM",
            "--calibration",
            str(EXAMPLES / "EX0001-2026.toml"),
            "--function",
            "dcv",
            "--range",
            "10 V",
            "--reading",
            "7 V",
            "--at",
            "2026-09-18",
            "--temperature",
            "23 °C",
            "--mode",
            "calibration",
            "--drift",
            "datasheet",
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "drift since calibration" in out and "6.999948 V" in out

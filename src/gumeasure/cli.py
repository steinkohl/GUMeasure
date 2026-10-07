"""Command line of gumeasure: check, schema and explain."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

from gumeasure import units
from gumeasure._version import __version__
from gumeasure.errors import FileFormatError, GumeasureError, UsageError
from gumeasure.files import SCHEMA_KINDS, json_schema_text, load
from gumeasure.model import Calibration, Datasheet, Instrument, Measurement, check_results
from gumeasure.registry import datasheet as datasheet_by_name
from gumeasure.registry import instrument


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "run"):
        parser.print_help()
        return 2
    try:
        code: int = args.run(args)
    except GumeasureError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gumeasure", description="Measurement uncertainty according to the GUM."
    )
    parser.add_argument("--version", action="version", version=f"gumeasure {__version__}")
    sub = parser.add_subparsers(title="commands")

    check = sub.add_parser("check", help="check data sheet and calibration files")
    check.add_argument(
        "paths",
        nargs="+",
        metavar="PATH_OR_NAME",
        help="files, directories (all *.toml below) or data sheet names",
    )
    check.add_argument(
        "--datasheet",
        action="append",
        default=[],
        metavar="NAME",
        help="add a data sheet by name for the certificates",
    )
    check.set_defaults(run=_check)

    schema = sub.add_parser("schema", help="print the JSON Schema of a file format")
    schema.add_argument("kind", choices=SCHEMA_KINDS)
    schema.set_defaults(run=_schema)

    explain = sub.add_parser("explain", help="print the uncertainty budget of a reading")
    explain.add_argument("--datasheet", required=True, metavar="NAME")
    explain.add_argument("--calibration", action="append", default=[], metavar="FILE")
    explain.add_argument("--function", required=True)
    explain.add_argument("--range", metavar="R", help="full scale, such as '10 V'")
    explain.add_argument(
        "--reading",
        action="append",
        required=True,
        metavar="X",
        help="a reading, such as '7 V'. Repeat for a series.",
    )
    explain.add_argument(
        "--at",
        required=True,
        metavar="DATE",
        help="date or ISO datetime. A bare date means midnight UTC.",
    )
    explain.add_argument("--temperature", metavar="T", help="such as '30 °C'")
    explain.add_argument("--mode", choices=("datasheet", "calibration"), default="datasheet")
    explain.add_argument("--drift", choices=("datasheet", "history"))
    explain.add_argument("--serial")
    explain.set_defaults(run=_explain)
    return parser


# --------------------------------------------------------------------------------------------
# check


def _check(args: argparse.Namespace) -> int:
    errors = 0

    def finding(where: str, severity: str, code: str, message: str) -> None:
        nonlocal errors
        errors += severity == "error"
        print(f"{where}: {severity} {code}: {message}")

    datasheets: dict[str, list[tuple[str, Datasheet]]] = defaultdict(list)
    calibrations: list[tuple[str, Calibration]] = []

    names = list(args.datasheet)
    for item in args.paths:
        path = Path(item)
        if path.is_dir():
            files = sorted(path.rglob("*.toml"))
        elif path.exists() or item.endswith(".toml"):
            files = [path]
        else:
            names.append(item)
            continue
        for file in files:
            try:
                loaded = load(file)
            except FileFormatError as err:
                for key, message in err.problems:
                    finding(
                        str(file), "error", "file-format", f"{key}: {message}" if key else message
                    )
                continue
            if isinstance(loaded, Datasheet):
                datasheets[loaded.model].append((str(file), loaded))
            else:
                calibrations.append((str(file), loaded))
    for name in names:
        try:
            ds = datasheet_by_name(name)
        except (UsageError, FileFormatError) as err:
            finding(name, "error", "unknown-datasheet", str(err))
            continue
        datasheets[ds.model].append((name, ds))

    chosen: dict[str, Datasheet] = {}
    for model, found in datasheets.items():
        first_where, first = found[0]
        for where, other in found[1:]:
            if other != first:
                finding(
                    where,
                    "error",
                    "datasheet-conflict",
                    f"differs from the data sheet of {model} in {first_where}",
                )
        chosen[model] = first
        for where, ds in found:
            for i, check, got, ok in check_results(ds):
                if not ok:
                    finding(
                        where,
                        "error",
                        "check-failed",
                        f"check[{i}]: {check.function} at {units.plain(check.reading)} gives "
                        f"{units.plain(got)}, the data sheet states "
                        f"{units.plain(check.half_width)}",
                    )

    by_unit: dict[tuple[str, str], list[tuple[str, Calibration]]] = defaultdict(list)
    for where, cal in calibrations:
        by_unit[(cal.model, cal.serial)].append((where, cal))
    for (model, serial), cals in sorted(by_unit.items()):
        where = ", ".join(w for w, _ in cals)
        if model not in chosen:
            finding(
                where,
                "error",
                "datasheet-missing",
                f"no data sheet of model {model} among the arguments",
            )
            continue
        try:
            inst = Instrument(chosen[model], serial, tuple(c for _, c in cals), modes={})
        except UsageError as err:
            finding(where, "error", "instrument", str(err))
            continue
        files_by_cert = {c.certificate: w for w, c in cals}
        for issue in inst.check():
            cert = issue.message.split(",")[0].removeprefix("certificate ")
            finding(files_by_cert.get(cert, where), issue.severity, issue.code, issue.message)

    total = sum(len(v) for v in datasheets.values())
    print(f"checked {total} data sheets and {len(calibrations)} certificates, {errors} errors")
    return 1 if errors else 0


# --------------------------------------------------------------------------------------------
# schema


def _schema(args: argparse.Namespace) -> int:
    sys.stdout.write(json_schema_text(args.kind))
    return 0


# --------------------------------------------------------------------------------------------
# explain


def _explain(args: argparse.Namespace) -> int:
    modes = {args.function: args.mode}
    drift = {args.function: args.drift} if args.drift else {}
    serial = args.serial if args.serial or args.calibration else "unknown"
    inst = instrument(args.datasheet, args.calibration, modes=modes, drift=drift, serial=serial)
    unit = inst.datasheet.function(args.function).unit
    readings = units.make([_reading(r, unit) for r in args.reading], unit)
    m = inst.evaluate(
        args.function, readings, range=args.range, at=_when(args.at), temperature=args.temperature
    )
    print(render(inst, args.function, m))
    return 0 if m.usable else 1


def _reading(text: str, unit: str) -> float:
    try:
        value = units.parse_quantity(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            raise UsageError(f"not a reading: {text!r}") from None
    if not units.same_dimension(value, unit):
        raise UsageError(f"reading {text!r} must have the dimension of {unit}")
    return units.magnitude(value, unit)


def _when(text: str) -> datetime:
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), UTC)
        when = datetime.fromisoformat(text)
    except ValueError:
        raise UsageError(f"--at must be a date or an ISO datetime, got {text!r}") from None
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def render(inst: Instrument, function: str, m: Measurement) -> str:
    """The budget of a Measurement as a plain text table."""
    rec = m.inputs
    ds = rec["datasheet"]
    head = (
        f"{ds['model']} {inst.serial}, {function}, "
        f"{units.fmt(ds['range']['full_scale'], m.unit)} range, mode {rec['mode']}"
        + (f", drift {rec['drift']}" if rec["drift"] else "")
        + f", {rec['at'][:10]}"
    )
    lines = [
        head,
        f"value {m.value:.10g} {m.unit}   u {units.fmt(m.u, m.unit)}   "
        f"U {units.fmt(m.U, m.unit)} (k = {m.k:g})",
        "",
    ]
    rows = [("contribution", "type", "distribution", "u", "source")]
    rows += [(c.name, c.type, c.distribution, units.fmt(c.u, m.unit), c.source) for c in m.budget]
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    for row in rows:
        lines.append(
            "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:4])) + "  " + row[4]
        )
    if m.issues:
        lines.append("")
        lines += [f"{i.severity} {i.code}: {i.message}" for i in m.issues]
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

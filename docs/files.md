# File formats

gumeasure reads two kinds of TOML file: data sheets and calibration certificates. Every file
has a `schema` key with its format and version. Unknown keys are refused.

Quantities are strings of a number and a unit, such as `"10 mA"`, `"23 °C"` or `"1 year"`.
Fractions are strings with `%` or `ppm`, such as `"0.0015 %"`. A bare number is refused in
both.

Start a file with `#:schema <path to the schema>` for completion and checking in editors with
Taplo. The schemas are `src/gumeasure/schema/datasheet.schema.json` and
`src/gumeasure/schema/calibration.schema.json`.

## Data sheet, `gumeasure.datasheet/1`

| Key | Type | Meaning |
|---|---|---|
| `schema` | `"gumeasure.datasheet/1"` | format and version |
| `model` | string | instrument type, such as `"SPD1305X"` |
| `vendor` | string | |
| `source` | string | document, revision and table the values come from |
| `tcal` | temperature | calibration temperature, such as `"23 °C"` |
| `band` | temperature difference in K | the accuracy holds within `tcal ± band` |
| `intervals` | list of times, optional | time since calibration that each accuracy column holds for, rising. Empty or missing: one column, valid until the calibration is due |
| `function.<name>` | table | one per measured quantity |
| `check` | list of tables, optional | worked examples, checked by `gumeasure check` |

A function name with a dot needs quotes: `[function."readback.current"]`.

### `function.<name>`

| Key | Type | Meaning |
|---|---|---|
| `unit` | unit string | unit of the function, such as `"V"` or `"A"` |
| `range` | list of tables | the ranges, sorted by full scale |

### `function.<name>.range`

| Key | Type | Meaning |
|---|---|---|
| `full_scale` | quantity in the unit of the function | identifies the range |
| `resolution` | quantity in the unit of the function | one digit |
| `resolution_included` | boolean | true if the accuracy already covers the resolution |
| `accuracy` | list of accuracy tables | one per interval, in the order of `intervals`. Exactly one without intervals |
| `tempco` | accuracy table, optional | per kelvin outside `tcal ± band` |

### Accuracy table

The half-width is `a = of_reading·|x| + of_range·full_scale + offset + counts·resolution`. All
keys are optional and default to zero.

| Key | Type | Meaning |
|---|---|---|
| `of_reading` | fraction | of the reading |
| `of_range` | fraction | of the full scale |
| `offset` | quantity in the unit of the function | fixed term. For `tempco` it is per kelvin |
| `counts` | whole number | digits of the resolution |

### `check`

| Key | Type | Meaning |
|---|---|---|
| `function` | string | |
| `range` | quantity | full scale of the range |
| `reading` | quantity | |
| `interval` | time | required if the data sheet has intervals, else left out |
| `half_width` | quantity | the expected half-width. Must agree within 1e-9 relative |

## Calibration certificate, `gumeasure.calibration/1`

One file per certificate, typed from the PDF.

| Key | Type | Meaning |
|---|---|---|
| `schema` | `"gumeasure.calibration/1"` | format and version |
| `model` | string | must match the data sheet |
| `serial` | string | serial number of the unit |
| `certificate` | string | certificate number |
| `laboratory` | string | |
| `accredited` | boolean | true for an ISO/IEC 17025 certificate, such as DAkkS |
| `date` | TOML date | date of calibration |
| `due` | TOML date | the calibration is valid up to and including this date |
| `temperature` | temperature, optional | ambient temperature during calibration |
| `deviation_sign` | `"indication - reference"` | sign convention, required |
| `point` | list of tables, optional | calibration points. None for a factory certificate without values |

### `point`

| Key | Type | Meaning |
|---|---|---|
| `function` | string | function of the data sheet |
| `range` | quantity | full scale of the range |
| `reference` | quantity | reference value |
| `deviation` | quantity | indication minus reference, as left after any adjustment |
| `U` | quantity | expanded uncertainty |
| `k` | number | coverage factor |
| `deviation_as_found` | quantity, optional | only if the unit was adjusted |

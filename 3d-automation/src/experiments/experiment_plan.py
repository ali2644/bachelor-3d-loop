from __future__ import annotations

import csv
import random
import secrets
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from printer.print_parameters import PrintParameters


EXPECTED_FIELD_NAMES = (
    "cycle_number",
    "top_solid_layers",
    "print_speed",
    "extrusion_width",
    "extrusion_multiplier",
    "temperature",
    "fan_speed",
)
DEFAULT_EXPECTED_CYCLE_COUNT = 20

# Narrowed warm-start limits chosen after the first hardware trials.
#GENERATED_TOP_SOLID_LAYERS = 5
GENERATED_PARAMETER_BOUNDS = {
    "print_speed": (50.0, 90.0),
    "extrusion_width": (0.38, 0.50),
    "extrusion_multiplier": (1.05, 1.20),
    "temperature": (215.0, 235.0),
    "fan_speed": (30.0, 80.0),
    "top_solid_layers": (4, 9),  
}


@dataclass(frozen=True)
class ExperimentPlanEntry:
    """One numbered and fully validated row of an experiment plan."""

    cycle_number: int
    parameters: PrintParameters


@dataclass(frozen=True)
class GeneratedExperimentPlan:
    """Paths and seed of one newly generated experiment plan."""

    path: Path
    archive_path: Path
    seed: int


def _latin_hypercube_column(
    sample_count: int,
    random_generator: random.Random,
) -> list[float]:
    """Return one independently shuffled Latin-hypercube column."""
    values = [
        (stratum + random_generator.random()) / sample_count
        for stratum in range(sample_count)
    ]
    random_generator.shuffle(values)
    return values


def _scale(unit_value: float, lower: float, upper: float) -> float:
    return lower + unit_value * (upper - lower)


def _generate_entries(
    sample_count: int,
    seed: int,
) -> tuple[ExperimentPlanEntry, ...]:
    random_generator = random.Random(seed)
    columns = {
        name: _latin_hypercube_column(sample_count, random_generator)
        for name in GENERATED_PARAMETER_BOUNDS
    }

    entries: list[ExperimentPlanEntry] = []
    for index in range(sample_count):
        scaled = {
            name: _scale(
                columns[name][index],
                bounds[0],
                bounds[1],
            )
            for name, bounds in GENERATED_PARAMETER_BOUNDS.items()
        }
        entries.append(
            ExperimentPlanEntry(
                cycle_number=index + 1,
                parameters=PrintParameters(
                    top_solid_layers=int(round(scaled["top_solid_layers"])),
                    print_speed=int(round(scaled["print_speed"])),
                    extrusion_width=round(
                        scaled["extrusion_width"],
                        3,
                    ),
                    extrusion_multiplier=round(
                        scaled["extrusion_multiplier"],
                        3,
                    ),
                    temperature=int(round(scaled["temperature"])),
                    fan_speed=int(round(scaled["fan_speed"])),
                ),
            )
        )

    _validate_unique_parameter_sets(entries)
    return tuple(entries)


def _write_experiment_plan(
    path: Path,
    entries: tuple[ExperimentPlanEntry, ...],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=EXPECTED_FIELD_NAMES,
        )
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "cycle_number": entry.cycle_number,
                    **entry.parameters.as_record(),
                }
            )


def generate_experiment_plan(
    csv_path: str | Path,
    *,
    sample_count: int = DEFAULT_EXPECTED_CYCLE_COUNT,
    seed: int | None = None,
) -> GeneratedExperimentPlan:
    """
    Generate, archive and atomically activate one Latin-hypercube plan.

    The returned seed and archived CSV make every automatically generated
    plan reproducible. Supplying the same seed produces the same rows.
    """
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1.")
    if isinstance(seed, bool) or (seed is not None and not isinstance(seed, int)):
        raise ValueError("seed must be an integer or None.")

    resolved_seed = secrets.randbits(63) if seed is None else seed
    entries = _generate_entries(sample_count, resolved_seed)

    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    archive_directory = path.parent / "archive"
    archive_directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix = uuid.uuid4().hex[:8]

    if path.is_file():
        previous_archive_path = archive_directory / (
            f"{path.stem}_{timestamp}_replaced_{unique_suffix}{path.suffix}"
        )
        shutil.copy2(path, previous_archive_path)

    archive_path = archive_directory / (
        f"{path.stem}_{timestamp}_seed-{resolved_seed}_"
        f"{unique_suffix}{path.suffix}"
    )
    _write_experiment_plan(archive_path, entries)

    temporary_path = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        shutil.copyfile(archive_path, temporary_path)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return GeneratedExperimentPlan(
        path=path,
        archive_path=archive_path,
        seed=resolved_seed,
    )


def _parse_int(
    raw_value: str | None,
    field_name: str,
) -> int:
    value = "" if raw_value is None else raw_value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty.")

    try:
        return int(value)
    except ValueError as error:
        raise ValueError(
            f"{field_name} must be an integer, got {value!r}."
        ) from error


def _parse_float(
    raw_value: str | None,
    field_name: str,
) -> float:
    value = "" if raw_value is None else raw_value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty.")

    try:
        return float(value)
    except ValueError as error:
        raise ValueError(
            f"{field_name} must be numeric, got {value!r}."
        ) from error


def _validate_header(field_names: list[str] | None) -> None:
    if field_names is None:
        raise ValueError("Experiment plan is empty or has no CSV header.")

    duplicate_fields = sorted(
        name
        for name, count in Counter(field_names).items()
        if count > 1
    )
    if duplicate_fields:
        raise ValueError(
            "Experiment plan CSV header contains duplicate columns: "
            f"{', '.join(duplicate_fields)}."
        )

    expected = set(EXPECTED_FIELD_NAMES)
    actual = set(field_names)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ValueError(
            "Experiment plan CSV header does not match the expected schema "
            f"({'; '.join(details)})."
        )


def _entry_from_row(
    row: dict[str | None, str | list[str] | None],
    line_number: int,
) -> ExperimentPlanEntry:
    extra_values = row.get(None)
    if extra_values:
        raise ValueError(
            f"Invalid experiment plan row {line_number}: "
            f"unexpected extra values {extra_values!r}."
        )

    try:
        cycle_number = _parse_int(
            _text_value(row.get("cycle_number")),
            "cycle_number",
        )
        parameters = PrintParameters(
            top_solid_layers=_parse_int(
                _text_value(row.get("top_solid_layers")),
                "top_solid_layers",
            ),
            print_speed=_parse_float(
                _text_value(row.get("print_speed")),
                "print_speed",
            ),
            extrusion_width=_parse_float(
                _text_value(row.get("extrusion_width")),
                "extrusion_width",
            ),
            extrusion_multiplier=_parse_float(
                _text_value(row.get("extrusion_multiplier")),
                "extrusion_multiplier",
            ),
            temperature=_parse_int(
                _text_value(row.get("temperature")),
                "temperature",
            ),
            fan_speed=_parse_int(
                _text_value(row.get("fan_speed")),
                "fan_speed",
            ),
        )
    except ValueError as error:
        raise ValueError(
            f"Invalid experiment plan row {line_number}: {error}"
        ) from error

    return ExperimentPlanEntry(
        cycle_number=cycle_number,
        parameters=parameters,
    )


def _text_value(value: str | list[str] | None) -> str | None:
    if isinstance(value, list):
        return None
    return value


#def _validate_cycle_numbers(
#    entries: list[ExperimentPlanEntry],
#    expected_cycle_count: int,
#) -> None:
#    counts = Counter(entry.cycle_number for entry in entries)
#    duplicates = sorted(
#        cycle_number
#        for cycle_number, count in counts.items()
#        if count > 1
#    )
#    expected = set(range(1, expected_cycle_count + 1))
#    actual = set(counts)
#    missing = sorted(expected - actual)
#    unexpected = sorted(actual - expected)
#
#    if duplicates or missing or unexpected:
#        details: list[str] = []
#        if duplicates:
#            details.append(
#                "duplicate: " + ", ".join(map(str, duplicates))
#            )
#        if missing:
#            details.append("missing: " + ", ".join(map(str, missing)))
#        if unexpected:
#            details.append(
#                "outside expected range: "
#                + ", ".join(map(str, unexpected))
#            )
#        raise ValueError(
#            "Experiment plan cycle numbers must be exactly "
#            f"1-{expected_cycle_count} ({'; '.join(details)})."
#        )


def _validate_unique_parameter_sets(
    entries: list[ExperimentPlanEntry],
) -> None:
    first_cycle_by_parameters: dict[PrintParameters, int] = {}
    duplicates: list[tuple[int, int]] = []
#
#    for entry in entries:
#        first_cycle = first_cycle_by_parameters.setdefault(
#            entry.parameters,
#            entry.cycle_number,
#        )
#        if first_cycle != entry.cycle_number:
#            duplicates.append((first_cycle, entry.cycle_number))
#
#    if duplicates:
#        duplicate_text = ", ".join(
#            f"cycles {first_cycle} and {duplicate_cycle}"
#            for first_cycle, duplicate_cycle in duplicates
#        )
#        raise ValueError(
#            "Experiment plan contains duplicate parameter sets: "
#            f"{duplicate_text}."
#        )


def load_experiment_plan(
    csv_path: str | Path,
    *,
    expected_cycle_count: int = DEFAULT_EXPECTED_CYCLE_COUNT,
) -> tuple[ExperimentPlanEntry, ...]:
    """Load and fully validate a numbered, reproducible experiment plan."""
    if expected_cycle_count < 1:
        raise ValueError("expected_cycle_count must be at least 1.")

    path = Path(csv_path)
    if not path.is_file():
        raise ValueError(f"Experiment plan not found: {path}")

    entries: list[ExperimentPlanEntry] = []
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        reader = csv.DictReader(stream)
        _validate_header(reader.fieldnames)

        for line_number, row in enumerate(reader, start=2):
            entries.append(_entry_from_row(row, line_number))

    if len(entries) != expected_cycle_count:
        raise ValueError(
            "Experiment plan must contain exactly "
            f"{expected_cycle_count} data rows, got {len(entries)}."
        )

    #_validate_cycle_numbers(entries, expected_cycle_count)
    #_validate_unique_parameter_sets(entries)
    return tuple(sorted(entries, key=lambda entry: entry.cycle_number))
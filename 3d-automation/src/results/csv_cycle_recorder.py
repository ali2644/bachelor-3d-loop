from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path
from typing import Iterable

from orchestrator import CycleResult


RECORDED_PROFILE_PARAMETERS = (
    "top_solid_layers",
    "print_speed",
    "extrusion_width",
    "extrusion_multiplier",
    "temperature",
    "fan_speed",
)


def read_profile_parameters(
    profile_path: Path,
    parameter_names: Iterable[str] = RECORDED_PROFILE_PARAMETERS,
) -> dict[str, str]:
    """Read selected values from a section-less PrusaSlicer INI file."""
    requested = set(parameter_names)
    values: dict[str, str] = {}

    with profile_path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            name, value = line.split("=", maxsplit=1)
            name = name.strip()
            if name in requested:
                values[name] = value.strip()

    return values


class CsvCycleRecorder:
    """Append one stable-schema CSV row for every cycle attempt."""

    BASE_FIELD_NAMES = (
        "cycle_id",
        "mode",
        "status",
        "failed_stage",
        "error",
        "started_at",
        "finished_at",
        "duration_seconds",
        "print_time_seconds",
        "stl_path",
        "profile_path",
        "profile_sha256",
        "gcode_path",
        "camera_image_path",
        "Ra_um",
        "Rz_um",
        "printer_states",
    )

    def __init__(
        self,
        csv_path: str | Path,
        *,
        parameter_names: Iterable[str] = RECORDED_PROFILE_PARAMETERS,
    ) -> None:
        self.csv_path = Path(csv_path)
        self.parameter_names = tuple(parameter_names)
        self.field_names = (
            *self.BASE_FIELD_NAMES,
            *(f"parameter_{name}" for name in self.parameter_names),
        )

    def validate_destination(self) -> None:
        """Reject an incompatible existing result file before hardware runs."""
        if self.csv_path.exists() and not self.csv_path.is_file():
            raise ValueError(
                f"Cycle result path is not a file: {self.csv_path}"
            )
        if self.csv_path.is_file() and self.csv_path.stat().st_size > 0:
            self._validate_existing_header()

    def record(self, result: CycleResult) -> None:
        self.csv_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        file_has_content = (
            self.csv_path.is_file()
            and self.csv_path.stat().st_size > 0
        )
        if file_has_content:
            self._validate_existing_header()

        row: dict[str, object] = {
            "cycle_id": result.cycle_id,
            "mode": result.mode,
            "status": result.status.value,
            "failed_stage": (
                ""
                if result.status.value == "completed"
                else result.stage.value
            ),
            "error": result.error or "",
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "duration_seconds": round(result.duration_seconds, 3),
            "print_time_seconds": (
                ""
                if result.print_time_seconds is None
                else round(result.print_time_seconds, 3)
            ),
            "stl_path": str(result.stl_path),
            "profile_path": str(result.profile_path),
            "profile_sha256": result.profile_sha256,
            "gcode_path": str(result.gcode_path),
            "camera_image_path": result.camera_image_path or "",
            "Ra_um": result.measurements.get("Ra", ""),
            "Rz_um": result.measurements.get("Rz", ""),
            "printer_states": " -> ".join(result.printer_states),
        }
        row.update(
            {
                f"parameter_{name}": result.print_parameters.get(name, "")
                for name in self.parameter_names
            }
        )

        with self.csv_path.open(
            "a",
            encoding="utf-8",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=self.field_names,
                quoting=csv.QUOTE_ALL,
            )
            if not file_has_content:
                writer.writeheader()
            writer.writerow(row)
            stream.flush()
            os.fsync(stream.fileno())

    def _validate_existing_header(self) -> None:
        with self.csv_path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as stream:
            reader = csv.reader(stream)
            existing_header = next(reader, [])

        if existing_header == list(self.field_names):
            return

        legacy_field_names = tuple(
            name
            for name in self.field_names
            if name != "print_time_seconds"
        )
        if existing_header == list(legacy_field_names):
            self._add_empty_print_time_column(legacy_field_names)
            return

        raise ValueError(
            "Existing cycle CSV has a different schema. "
            "Choose a new --results-csv file for the new series. "
            f"Expected {list(self.field_names)!r}, "
            f"got {existing_header!r}."
        )

    def _add_empty_print_time_column(
        self,
        legacy_field_names: tuple[str, ...],
    ) -> None:
        """Upgrade only the immediately preceding known CSV schema."""
        with self.csv_path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as stream:
            rows = list(csv.DictReader(stream))

        temporary_path = self.csv_path.with_name(
            f".{self.csv_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary_path.open(
                "x",
                encoding="utf-8",
                newline="",
            ) as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=self.field_names,
                    quoting=csv.QUOTE_ALL,
                )
                writer.writeheader()
                for row in rows:
                    normalized = {
                        name: row.get(name, "")
                        for name in legacy_field_names
                    }
                    normalized["print_time_seconds"] = ""
                    writer.writerow(normalized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.csv_path)
        finally:
            temporary_path.unlink(missing_ok=True)

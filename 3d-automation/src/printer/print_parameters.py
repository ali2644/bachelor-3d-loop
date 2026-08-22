from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


PROFILE_PARAMETER_KEYS = (
    "top_solid_layers",
    "top_solid_infill_speed",
    "top_infill_extrusion_width",
    "extrusion_multiplier",
    "temperature",
    "max_fan_speed",
)
FIXED_TOP_SOLID_LAYERS = 5

# These are constant experimental conditions, not optimization variables.
# They make sure the six logical parameters have the intended effect.
FIXED_PROFILE_OVERRIDES = {
    "top_solid_layers": str(FIXED_TOP_SOLID_LAYERS),
    "skirts": "0",
    "brim_width": "0",
    "top_solid_min_thickness": "0",
    "slowdown_below_layer_time": "0",
    "enable_dynamic_fan_speeds": "0",
}


def _format_number(value: float) -> str:
    return format(value, ".12g")


def _read_profile_values(
    profile_path: Path,
    parameter_names: tuple[str, ...],
) -> dict[str, str]:
    requested = set(parameter_names)
    values: dict[str, str] = {}

    with profile_path.open(
        "r",
        encoding="utf-8",
        errors="strict",
    ) as stream:
        for raw_line in stream:
            line = raw_line.strip()
            if (
                not line
                or line.startswith(("#", ";"))
                or "=" not in line
            ):
                continue

            name, value = line.split("=", maxsplit=1)
            name = name.strip()
            if name not in requested:
                continue

            if name in values:
                raise ValueError(
                    f"Slicer profile contains duplicate setting {name!r}."
                )
            values[name] = value.strip()

    missing = requested.difference(values)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(
            f"Slicer profile is missing required settings: {missing_text}."
        )

    return values


def _parse_int(value: str, setting_name: str) -> int:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(
            f"Slicer setting {setting_name!r} must be numeric, got "
            f"{value!r}."
        ) from error

    if not parsed.is_integer():
        raise ValueError(
            f"Slicer setting {setting_name!r} must be an integer, got "
            f"{value!r}."
        )
    return int(parsed)


def _parse_float(value: str, setting_name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(
            f"Slicer setting {setting_name!r} must be an absolute numeric "
            f"value, got {value!r}."
        ) from error

    if not math.isfinite(parsed):
        raise ValueError(
            f"Slicer setting {setting_name!r} must be finite."
        )
    return parsed


@dataclass(frozen=True)
class PrintParameters:
    """The six logical optimization variables for one print cycle."""

    top_solid_layers: int
    print_speed: float
    extrusion_width: float
    extrusion_multiplier: float
    temperature: int
    fan_speed: int

    def __post_init__(self) -> None:
        if self.top_solid_layers != FIXED_TOP_SOLID_LAYERS:
            raise ValueError(
                "top_solid_layers is fixed at "
                f"{FIXED_TOP_SOLID_LAYERS}, got "
                f"{self.top_solid_layers}."
            )
        self._validate_float(
            "print_speed",
            self.print_speed,
            50,
            90,
        )
        self._validate_float(
            "extrusion_width",
            self.extrusion_width,
            0.38,
            0.50,
        )
        self._validate_float(
            "extrusion_multiplier",
            self.extrusion_multiplier,
            1.05,
            1.20,
        )
        self._validate_int(
            "temperature",
            self.temperature,
            215,
            235,
        )
        self._validate_int(
            "fan_speed",
            self.fan_speed,
            30,
            80,
        )

    @classmethod
    def from_profile(
        cls,
        profile_path: str | Path,
        *,
        top_solid_layers: int | None = None,
        print_speed: float | None = None,
        extrusion_width: float | None = None,
        extrusion_multiplier: float | None = None,
        temperature: int | None = None,
        fan_speed: int | None = None,
    ) -> "PrintParameters":
        """
        Extract the six start values from an existing full profile.

        A profile can contain different minimum and maximum fan values.
        max_fan_speed is used as the single start value; generated profiles
        then set minimum, maximum and bridge fan speed to this same value.
        """
        path = Path(profile_path)
        if not path.is_file():
            raise ValueError(f"Slicer profile not found: {path}")

        values = _read_profile_values(path, PROFILE_PARAMETER_KEYS)
        extracted_top_solid_layers = _parse_int(
            values["top_solid_layers"],
            "top_solid_layers",
        )
        extracted_print_speed = _parse_float(
            values["top_solid_infill_speed"],
            "top_solid_infill_speed",
        )
        extracted_extrusion_width = _parse_float(
            values["top_infill_extrusion_width"],
            "top_infill_extrusion_width",
        )
        extracted_extrusion_multiplier = _parse_float(
            values["extrusion_multiplier"],
            "extrusion_multiplier",
        )
        extracted_temperature = _parse_int(
            values["temperature"],
            "temperature",
        )
        extracted_fan_speed = _parse_int(
            values["max_fan_speed"],
            "max_fan_speed",
        )

        return cls(
            top_solid_layers=(
                extracted_top_solid_layers
                if top_solid_layers is None
                else top_solid_layers
            ),
            print_speed=(
                extracted_print_speed
                if print_speed is None
                else print_speed
            ),
            extrusion_width=(
                extracted_extrusion_width
                if extrusion_width is None
                else extrusion_width
            ),
            extrusion_multiplier=(
                extracted_extrusion_multiplier
                if extrusion_multiplier is None
                else extrusion_multiplier
            ),
            temperature=(
                extracted_temperature
                if temperature is None
                else temperature
            ),
            fan_speed=(
                extracted_fan_speed
                if fan_speed is None
                else fan_speed
            ),
        )

    def with_overrides(
        self,
        *,
        top_solid_layers: int | None = None,
        print_speed: float | None = None,
        extrusion_width: float | None = None,
        extrusion_multiplier: float | None = None,
        temperature: int | None = None,
        fan_speed: int | None = None,
    ) -> "PrintParameters":
        """Return a validated copy with explicitly supplied new values."""
        return replace(
            self,
            top_solid_layers=(
                self.top_solid_layers
                if top_solid_layers is None
                else top_solid_layers
            ),
            print_speed=(
                self.print_speed
                if print_speed is None
                else print_speed
            ),
            extrusion_width=(
                self.extrusion_width
                if extrusion_width is None
                else extrusion_width
            ),
            extrusion_multiplier=(
                self.extrusion_multiplier
                if extrusion_multiplier is None
                else extrusion_multiplier
            ),
            temperature=(
                self.temperature
                if temperature is None
                else temperature
            ),
            fan_speed=(
                self.fan_speed
                if fan_speed is None
                else fan_speed
            ),
        )

    def as_profile_overrides(self) -> dict[str, str]:
        """Map six logical variables to their PrusaSlicer settings."""
        fan_speed = str(self.fan_speed)
        return {
            "top_solid_layers": str(self.top_solid_layers),
            "top_solid_infill_speed": _format_number(
                self.print_speed
            ),
            "top_infill_extrusion_width": _format_number(
                self.extrusion_width
            ),
            "extrusion_multiplier": _format_number(
                self.extrusion_multiplier
            ),
            "temperature": str(self.temperature),
            "min_fan_speed": fan_speed,
            "max_fan_speed": fan_speed,
            "bridge_fan_speed": fan_speed,
        }

    def as_record(self) -> dict[str, str]:
        """Return the stable logical names stored beside measurements."""
        return {
            "top_solid_layers": str(self.top_solid_layers),
            "print_speed": _format_number(self.print_speed),
            "extrusion_width": _format_number(self.extrusion_width),
            "extrusion_multiplier": _format_number(
                self.extrusion_multiplier
            ),
            "temperature": str(self.temperature),
            "fan_speed": str(self.fan_speed),
        }

    @staticmethod
    def _validate_int(
        name: str,
        value: int,
        minimum: int,
        maximum: int,
    ) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer.")
        if not minimum <= value <= maximum:
            raise ValueError(
                f"{name} must be between {minimum} and {maximum}, "
                f"got {value}."
            )

    @staticmethod
    def _validate_float(
        name: str,
        value: float,
        minimum: float,
        maximum: float,
    ) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be numeric.")
        if not math.isfinite(float(value)):
            raise ValueError(f"{name} must be finite.")
        if not minimum <= float(value) <= maximum:
            raise ValueError(
                f"{name} must be between {minimum} and {maximum}, "
                f"got {value}."
            )


class SlicerProfileGenerator:
    """Create one traceable profile while preserving the full base profile."""

    def __init__(self, output_directory: str | Path) -> None:
        self.output_directory = Path(output_directory)

    def generate(
        self,
        base_profile_path: str | Path,
        parameters: PrintParameters,
        *,
        output_filename: str | None = None,
    ) -> Path:
        base_path = Path(base_profile_path)
        if not base_path.is_file():
            raise ValueError(f"Slicer profile not found: {base_path}")

        overrides = {
            **parameters.as_profile_overrides(),
            **FIXED_PROFILE_OVERRIDES,
        }
        profile_text = self._replace_settings(
            base_path.read_text(encoding="utf-8"),
            overrides,
        )

        self.output_directory.mkdir(parents=True, exist_ok=True)
        if output_filename is None:
            timestamp = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%S"
            )
            profile_id = uuid.uuid4().hex[:8]
            output_filename = (
                f"cycle_profile_{timestamp}_{profile_id}.ini"
            )
        else:
            requested_path = Path(output_filename)
            if (
                requested_path.name != output_filename
                or requested_path.suffix != ".ini"
            ):
                raise ValueError(
                    "output_filename must be a plain .ini filename."
                )

        output_path = self.output_directory / output_filename
        output_path.write_text(profile_text, encoding="utf-8")
        return output_path

    @staticmethod
    def _replace_settings(
        profile_text: str,
        overrides: Mapping[str, str],
    ) -> str:
        remaining = set(overrides)
        replaced: set[str] = set()
        output_lines: list[str] = []

        for raw_line in profile_text.splitlines(keepends=True):
            stripped = raw_line.strip()
            if (
                not stripped
                or stripped.startswith(("#", ";"))
                or "=" not in raw_line
            ):
                output_lines.append(raw_line)
                continue

            name = raw_line.split("=", maxsplit=1)[0].strip()
            if name not in overrides:
                output_lines.append(raw_line)
                continue

            if name in replaced:
                raise ValueError(
                    f"Slicer profile contains duplicate setting {name!r}."
                )

            newline = "\n" if raw_line.endswith("\n") else ""
            output_lines.append(f"{name} = {overrides[name]}{newline}")
            replaced.add(name)
            remaining.discard(name)

        if remaining:
            missing_text = ", ".join(sorted(remaining))
            raise ValueError(
                "Full slicer base profile is missing settings that must be "
                f"controlled: {missing_text}."
            )

        return "".join(output_lines)
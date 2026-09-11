from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = PROJECT_ROOT / "local_archive"
LEGACY_PATHS = (
    "config/experiment_plans/experiment_plan_20.csv",
    "config/slicer_profile_flat.ini",
    "config/slicer_profile_meins.ini",
    "data/gcode/output.gcode",
    "data/gcode/Oberflachenmessung_Testkorper_MK2_0.4n_0.2mm_PLA_MINIIS_19m.bgcode",
    "docs/END_TO_END_SINGLE_CYCLE.md",
    "docs/OPTIMIZER_FAILURE_POLICY.md",
    "docs/OPTIMIZER_FLEXIBLE_BOUNDS.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_1.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_2.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_3.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_4.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_5.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_6.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_7.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_8.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_10.md",
    "docs/OPTIMIZER_FRAMEWORK_STEP_11.md",
    "tests/test_bayesian_optimizer.py",
)


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "List or recoverably archive obsolete committed project files."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move the listed files to ignored local_archive/ storage.",
    )
    parsed = parser.parse_args(arguments)

    existing = tuple(
        relative_path
        for relative_path in LEGACY_PATHS
        if (PROJECT_ROOT / relative_path).is_file()
    )
    if not existing:
        print("No listed legacy files are present.")
        return 0

    print("Legacy files selected for archival:")
    for relative_path in existing:
        print(f"- {relative_path}")

    if not parsed.apply:
        print("Dry run only. Repeat with --apply to move these exact files.")
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_directory = ARCHIVE_ROOT / f"repository_cleanup_{timestamp}"
    for relative_path in existing:
        source = PROJECT_ROOT / relative_path
        destination = archive_directory / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))

    print(f"Archived {len(existing)} files under {archive_directory}.")
    print("The files are recoverable there; review git status before commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

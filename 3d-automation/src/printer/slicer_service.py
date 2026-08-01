from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class SlicerService:
    def __init__(
        self,
        slicer_path: str | Path,
        *,
        timeout_seconds: float = 10 * 60,
    ) -> None:
        self.slicer_path = Path(slicer_path)
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        return (
            self.slicer_path.is_file()
            and os.access(self.slicer_path, os.X_OK)
        )

    def send_stl_to_slicer(
        self,
        stl_file_path: str | Path,
        profile: str | Path,
        gcode_file_path: str | Path,
    ) -> bool:
        stl_path = Path(stl_file_path)
        profile_path = Path(profile)
        gcode_path = Path(gcode_file_path)

        if not self.is_available():
            LOGGER.error(
                "PrusaSlicer is missing or not executable: %s",
                self.slicer_path,
            )
            return False

        if not stl_path.is_file():
            LOGGER.error("STL file not found: %s", stl_path)
            return False

        if not profile_path.is_file():
            LOGGER.error("Slicer profile not found: %s", profile_path)
            return False

        gcode_path.parent.mkdir(parents=True, exist_ok=True)
        gcode_path.unlink(missing_ok=True)

        command = [
            str(self.slicer_path),
            "-g",
            "--load",
            str(profile_path),
            "--center",
            "90,45",
            str(stl_path),
            "--output",
            str(gcode_path),
        ]

        try:
            completed_process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            LOGGER.exception("PrusaSlicer could not be executed.")
            return False

        if completed_process.returncode != 0:
            LOGGER.error(
                "Slicing failed with return code %s. stderr: %s",
                completed_process.returncode,
                completed_process.stderr.strip(),
            )
            return False

        if not gcode_path.is_file() or gcode_path.stat().st_size == 0:
            LOGGER.error(
                "PrusaSlicer returned success but did not create "
                "a non-empty G-code file: %s",
                gcode_path,
            )
            return False

        LOGGER.info(
            "Slicing completed: %s (%s bytes).",
            gcode_path,
            gcode_path.stat().st_size,
        )
        return True

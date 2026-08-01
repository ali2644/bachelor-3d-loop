from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from orchestrator import (
    CycleResult,
    CycleStage,
    CycleStatus,
)
from results.csv_cycle_recorder import (
    CsvCycleRecorder,
    read_profile_parameters,
)


class CsvCycleRecorderTest(unittest.TestCase):
    def test_records_parameters_and_measurements_in_stable_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            csv_path = root / "cycles.csv"
            now = datetime.now(timezone.utc)
            recorder = CsvCycleRecorder(
                csv_path,
                parameter_names=("layer_height", "temperature"),
            )
            result = CycleResult(
                cycle_id="cycle-1",
                mode="full",
                status=CycleStatus.COMPLETED,
                stage=CycleStage.COMPLETED,
                started_at=now,
                finished_at=now,
                duration_seconds=12.5,
                stl_path=root / "part.stl",
                profile_path=root / "profile.ini",
                gcode_path=root / "output.gcode",
                profile_sha256="abc123",
                print_parameters={
                    "layer_height": "0.2",
                    "temperature": "210",
                },
                measurements={"Ra": 4.152, "Rz": 22.5},
                printer_states=("PRINTING", "FINISHED"),
            )

            recorder.record(result)

            with csv_path.open(
                "r",
                encoding="utf-8",
                newline="",
            ) as stream:
                rows = list(csv.DictReader(stream))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["parameter_layer_height"], "0.2")
            self.assertEqual(rows[0]["parameter_temperature"], "210")
            self.assertEqual(rows[0]["Ra_um"], "4.152")
            self.assertEqual(rows[0]["Rz_um"], "22.5")
            self.assertEqual(
                rows[0]["printer_states"],
                "PRINTING -> FINISHED",
            )

    def test_reads_selected_values_from_sectionless_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            profile_path = Path(temporary_directory) / "profile.ini"
            profile_path.write_text(
                "# comment\n"
                "layer_height = 0.2\n"
                "temperature = 210\n"
                "unrelated = value\n",
                encoding="utf-8",
            )

            values = read_profile_parameters(
                profile_path,
                ("layer_height", "temperature"),
            )

            self.assertEqual(
                values,
                {
                    "layer_height": "0.2",
                    "temperature": "210",
                },
            )


if __name__ == "__main__":
    unittest.main()

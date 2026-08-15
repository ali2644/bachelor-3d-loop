from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from experiments.experiment_plan import load_experiment_plan
from printer.print_parameters import PrintParameters


FIELD_NAMES = (
    "cycle_number",
    "top_solid_layers",
    "print_speed",
    "extrusion_width",
    "extrusion_multiplier",
    "temperature",
    "fan_speed",
)


def valid_rows() -> list[dict[str, object]]:
    return [
        {
            "cycle_number": cycle_number,
            "top_solid_layers": 2 + (cycle_number - 1) % 4,
            "print_speed": round(50 + (120 - 50) * (cycle_number - 1) / 19),
            "extrusion_width": round(0.38 + (0.50 - 0.38) * (cycle_number - 1) / 19,3,),
            "extrusion_multiplier": 0.90 + 0.01 * (cycle_number - 1),
            "temperature": 195 + 2 * (cycle_number - 1),
            "fan_speed": 5 * (cycle_number - 1),
        }
        for cycle_number in range(1, 21)
    ]


class ExperimentPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.plan_path = (
            Path(self.temporary_directory.name) / "experiment_plan.csv"
        )

    def write_plan(
        self,
        rows: list[dict[str, object]],
        field_names: tuple[str, ...] = FIELD_NAMES,
    ) -> None:
        with self.plan_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=field_names,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)

    def test_loads_twenty_numbered_validated_entries(self) -> None:
        self.write_plan(valid_rows())

        plan = load_experiment_plan(self.plan_path)

        self.assertEqual(len(plan), 20)
        self.assertEqual(
            [entry.cycle_number for entry in plan],
            list(range(1, 21)),
        )
        self.assertEqual(
            plan[0].parameters,
            PrintParameters(
                top_solid_layers=2,
                print_speed=50,
                extrusion_width=0.38,
                extrusion_multiplier=0.90,
                temperature=195,
                fan_speed=0,
            ),
        )

    def test_rejects_missing_and_duplicate_cycle_number(self) -> None:
        rows = valid_rows()
        rows[-1]["cycle_number"] = 19
        self.write_plan(rows)

        with self.assertRaisesRegex(
            ValueError,
            r"duplicate: 19; missing: 20",
        ):
            load_experiment_plan(self.plan_path)

    def test_rejects_out_of_range_parameter_with_csv_line_number(self) -> None:
        rows = valid_rows()
        rows[4]["temperature"] = 236
        self.write_plan(rows)

        with self.assertRaisesRegex(
            ValueError,
            r"row 6: temperature must be between 195 and 235",
        ):
            load_experiment_plan(self.plan_path)

    def test_rejects_missing_required_column(self) -> None:
        rows = valid_rows()
        field_names = tuple(
            name for name in FIELD_NAMES if name != "fan_speed"
        )
        self.write_plan(rows, field_names)

        with self.assertRaisesRegex(
            ValueError,
            r"missing: fan_speed",
        ):
            load_experiment_plan(self.plan_path)

    def test_rejects_duplicate_parameter_sets(self) -> None:
        rows = valid_rows()
        for field_name in FIELD_NAMES[1:]:
            rows[-1][field_name] = rows[0][field_name]
        self.write_plan(rows)

        with self.assertRaisesRegex(
            ValueError,
            r"duplicate parameter sets: cycles 1 and 20",
        ):
            load_experiment_plan(self.plan_path)


if __name__ == "__main__":
    unittest.main()
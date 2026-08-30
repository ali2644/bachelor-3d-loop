from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from optimizer.bayesian_optimizer import (
    BayesianOptimizer,
    read_optimization_history,
)


FIELD_NAMES = (
    "cycle_id",
    "status",
    "error",
    "Ra_um",
    "parameter_top_solid_layers",
    "parameter_print_speed",
    "parameter_extrusion_width",
    "parameter_extrusion_multiplier",
    "parameter_temperature",
    "parameter_fan_speed",
)


def result_row(
    cycle_number: int,
    *,
    status: str = "completed",
    error: str = "",
    ra: str = "5.0",
    top_solid_layers: str = "5",
) -> dict[str, str]:
    return {
        "cycle_id": f"cycle-{cycle_number}",
        "status": status,
        "error": error,
        "Ra_um": ra,
        "parameter_top_solid_layers": top_solid_layers,
        "parameter_print_speed": str(55 + cycle_number * 8),
        "parameter_extrusion_width": str(0.39 + cycle_number * 0.01),
        "parameter_extrusion_multiplier": str(0.95 + cycle_number * 0.02),
        "parameter_temperature": str(200 + cycle_number * 4),
        "parameter_fan_speed": str(10 + cycle_number * 12),
    }


class BayesianOptimizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def write_results(
        self,
        rows: list[dict[str, str]],
        filename: str = "results.csv",
    ) -> Path:
        path = self.root / filename
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELD_NAMES)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_history_trains_only_on_successful_measurements(self) -> None:
        path = self.write_results(
            [
                result_row(1, ra="4.2"),
                result_row(2, error="QS infrastructure failure", ra="100"),
                result_row(3, status="failed", ra=""),
                result_row(4, top_solid_layers="4", ra="6.0"),
            ]
        )

        history = read_optimization_history((path,))

        self.assertEqual(len(history.observations), 2)
        self.assertEqual(history.observations[0].objective_value, 4.2)
        self.assertEqual(history.observations[1].parameters.top_solid_layers, 4)
        self.assertEqual(len(history.completed_parameters), 3)
        self.assertEqual(history.total_rows, 4)
        self.assertEqual(history.skipped_rows, 2)

    def test_empty_history_starts_from_valid_center_point(self) -> None:
        suggestion = BayesianOptimizer(
            candidate_count=64,
            n_restarts_optimizer=0,
        ).suggest((self.root / "missing.csv",))

        self.assertEqual(suggestion.strategy, "warm_start")
        self.assertEqual(
            suggestion.parameters.as_record(),
            {
                "top_solid_layers": "5",
                "print_speed": "70",
                "extrusion_width": "0.44",
                "extrusion_multiplier": "1.125",
                "temperature": "225",
                "fan_speed": "55",
            },
        )

    def test_bayesian_suggestion_is_deterministic_and_not_duplicate(self) -> None:
        rows = [
            result_row(index, ra=str(10.0 - index))
            for index in range(1, 6)
        ]
        path = self.write_results(rows)
        optimizer = BayesianOptimizer(
            seed=17,
            minimum_observations=5,
            candidate_count=256,
            n_restarts_optimizer=0,
        )

        first = optimizer.suggest((path,))
        second = optimizer.suggest((path,))

        self.assertEqual(first.strategy, "bayesian_ei")
        self.assertEqual(first.parameters, second.parameters)
        completed_records = {
            tuple(
                row[name]
                for name in (
                    "parameter_top_solid_layers",
                    "parameter_print_speed",
                    "parameter_extrusion_width",
                    "parameter_extrusion_multiplier",
                    "parameter_temperature",
                    "parameter_fan_speed",
                )
            )
            for row in rows
        }
        self.assertNotIn(
            tuple(first.parameters.as_record().values()),
            completed_records,
        )

    def test_reads_supervisor_parameter_names_and_response(self) -> None:
        path = self.root / "supervisor.csv"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "top_solid_layers",
                    "top_solid_infill_speed",
                    "extrusion_width",
                    "extrusion_multiplier",
                    "temperature",
                    "min_fan_speed",
                    "response",
                ),
            )
            writer.writeheader()
            writer.writerow(
                {
                    "top_solid_layers": "5",
                    "top_solid_infill_speed": "80",
                    "extrusion_width": "0.42",
                    "extrusion_multiplier": "1.05",
                    "temperature": "215",
                    "min_fan_speed": "60",
                    "response": "3.75",
                }
            )

        history = read_optimization_history((path,))

        self.assertEqual(len(history.observations), 1)
        self.assertEqual(history.observations[0].objective_value, 3.75)
        self.assertEqual(
            history.observations[0].parameters.print_speed,
            80,
        )


if __name__ == "__main__":
    unittest.main()

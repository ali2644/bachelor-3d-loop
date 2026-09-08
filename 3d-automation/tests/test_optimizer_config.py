from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from optimizer.config import (
    OptimizerConfigError,
    load_optimizer_config,
)


def valid_config() -> dict[str, object]:
    return {
        "schema_version": 1,
        "experiment_name": "test_run",
        "total_runs": 100,
        "seed": 42,
        "objective": "Ra_um",
        "warm_start": {
            "method": "lhs",
            "sample_count": 10,
        },
        "strategy": {
            "name": "BO",
            "options": {"acquisition": "ei"},
        },
        "parameters": [
            {"name": "print_speed", "lower": 50, "upper": 90},
            {
                "name": "extrusion_width",
                "lower": 0.38,
                "upper": 0.50,
            },
            {
                "name": "extrusion_multiplier",
                "lower": 1.05,
                "upper": 1.20,
            },
            {"name": "temperature", "lower": 215, "upper": 235},
            {"name": "fan_speed", "lower": 30, "upper": 80},
        ],
        "fixed_parameters": {"top_solid_layers": 5},
        "paths": {
            "stl": "part.stl",
            "base_profile": "base.ini",
            "output_directory": "runs/test_run",
            "history_csvs": ["history.csv"],
        },
    }


class OptimizerConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def write_config(self, config: dict[str, object]) -> Path:
        path = self.root / "optimizer.json"
        path.write_text(
            json.dumps(config),
            encoding="utf-8",
        )
        return path

    def test_loads_normalizes_and_resolves_valid_config(self) -> None:
        config = load_optimizer_config(self.write_config(valid_config()))

        self.assertEqual(config.strategy.name, "bayesian")
        self.assertEqual(config.strategy.options["candidate_count"], 4096)
        self.assertEqual(config.warm_start.method, "lhs")
        self.assertEqual(config.warm_start.sample_count, 10)
        self.assertEqual(config.main_batch_size, 1)
        self.assertEqual(
            config.variable_names,
            (
                "print_speed",
                "extrusion_width",
                "extrusion_multiplier",
                "temperature",
                "fan_speed",
            ),
        )
        self.assertEqual(config.paths.stl, (self.root / "part.stl").resolve())
        self.assertEqual(
            config.paths.output_directory,
            (self.root / "runs/test_run").resolve(),
        )

    def test_rejects_qbc_for_current_project_scope(self) -> None:
        raw_config = valid_config()
        raw_config["strategy"] = {"name": "QBC", "options": {}}

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "QBC is intentionally excluded",
        ):
            load_optimizer_config(self.write_config(raw_config))

    def test_accepts_safe_objective_expression(self) -> None:
        raw_config = valid_config()
        raw_config["objective"] = (
            "5 + print_time_minutes * Ra_um + Rz_um"
        )

        config = load_optimizer_config(self.write_config(raw_config))

        self.assertEqual(
            config.objective,
            "5 + print_time_minutes * Ra_um + Rz_um",
        )

    def test_rejects_unsafe_objective_expression(self) -> None:
        raw_config = valid_config()
        raw_config["objective"] = "__import__('os').system('echo unsafe')"

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "Invalid objective",
        ):
            load_optimizer_config(self.write_config(raw_config))

    def test_accepts_every_strategy_in_the_current_scope(self) -> None:
        strategies = {
            "bayesian": "bayesian",
            "pso": "pso",
            "de": "differential_evolution",
            "random": "random",
            "sobol": "sobol",
        }
        for supplied_name, expected_name in strategies.items():
            with self.subTest(strategy=supplied_name):
                raw_config = valid_config()
                raw_config["strategy"] = {
                    "name": supplied_name,
                    "options": {},
                }

                config = load_optimizer_config(
                    self.write_config(raw_config)
                )

                self.assertEqual(config.strategy.name, expected_name)
                expected_batch_size = (
                    1 if expected_name == "bayesian" else 10
                )
                self.assertEqual(
                    config.main_batch_size,
                    expected_batch_size,
                )

    def test_accepts_experiment_selected_bounds_outside_old_envelope(
        self,
    ) -> None:
        raw_config = valid_config()
        parameters = raw_config["parameters"]
        assert isinstance(parameters, list)
        parameters[0] = {
            "name": "print_speed",
            "lower": 20,
            "upper": 180,
        }

        config = load_optimizer_config(self.write_config(raw_config))

        speed = next(
            parameter
            for parameter in config.parameters
            if parameter.name == "print_speed"
        )
        self.assertEqual(speed.lower, 20.0)
        self.assertEqual(speed.upper, 180.0)

    def test_rejects_parameter_missing_from_both_sections(self) -> None:
        raw_config = valid_config()
        parameters = raw_config["parameters"]
        assert isinstance(parameters, list)
        parameters.pop()

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "Missing: fan_speed",
        ):
            load_optimizer_config(self.write_config(raw_config))

    def test_accepts_top_layers_as_integer_optimization_variable(self) -> None:
        raw_config = valid_config()
        parameters = raw_config["parameters"]
        fixed_parameters = raw_config["fixed_parameters"]
        assert isinstance(parameters, list)
        assert isinstance(fixed_parameters, dict)
        parameters.append(
            {"name": "top_solid_layers", "lower": 2, "upper": 5}
        )
        fixed_parameters.pop("top_solid_layers")

        config = load_optimizer_config(self.write_config(raw_config))

        self.assertIn("top_solid_layers", config.variable_names)
        self.assertNotIn("top_solid_layers", config.fixed_parameters)

    def test_rejects_values_outside_intrinsic_parameter_domain(self) -> None:
        raw_config = valid_config()
        parameters = raw_config["parameters"]
        assert isinstance(parameters, list)
        parameters[-1] = {
            "name": "fan_speed",
            "lower": 0,
            "upper": 101,
        }

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "must be at most 100",
        ):
            load_optimizer_config(self.write_config(raw_config))

    def test_de_requires_complete_population_batches(self) -> None:
        raw_config = valid_config()
        raw_config["total_runs"] = 95
        raw_config["strategy"] = {
            "name": "de",
            "options": {
                "differential_weight": 0.8,
                "crossover_probability": 0.9,
            },
        }

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "must be a complete strategy batch",
        ):
            load_optimizer_config(self.write_config(raw_config))

    def test_random_also_requires_complete_sampling_batches(self) -> None:
        raw_config = valid_config()
        raw_config["total_runs"] = 95
        raw_config["strategy"] = {"name": "random", "options": {}}

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "must be a complete strategy batch",
        ):
            load_optimizer_config(self.write_config(raw_config))

    def test_input_files_are_checked_only_when_requested(self) -> None:
        config = load_optimizer_config(self.write_config(valid_config()))

        with self.assertRaisesRegex(
            OptimizerConfigError,
            "Configured input files do not exist",
        ):
            config.validate_input_files()


if __name__ == "__main__":
    unittest.main()

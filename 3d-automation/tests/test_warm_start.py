from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from optimizer.config import load_optimizer_config
from optimizer.experiment_store import ExperimentStore
from optimizer.warm_start import (
    WarmStartError,
    WarmStartGenerator,
)


def config_payload(
    output_directory: Path,
    *,
    method: str = "lhs",
    seed: int = 42,
    sample_count: int = 10,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "experiment_name": "warm_start_test",
        "total_runs": 20,
        "seed": seed,
        "objective": "Ra_um",
        "warm_start": {
            "method": method,
            "sample_count": sample_count,
        },
        "strategy": {"name": "bayesian", "options": {}},
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
            "output_directory": str(output_directory),
            "history_csvs": [],
        },
    }


class WarmStartGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def load_config(
        self,
        *,
        method: str = "lhs",
        seed: int = 42,
        sample_count: int = 10,
        output_name: str = "experiment",
    ):
        output_directory = self.root / output_name
        path = self.root / f"{output_name}.json"
        path.write_text(
            json.dumps(
                config_payload(
                    output_directory,
                    method=method,
                    seed=seed,
                    sample_count=sample_count,
                )
            ),
            encoding="utf-8",
        )
        return load_optimizer_config(path)

    def test_all_supported_methods_generate_unique_valid_points(self) -> None:
        for method in ("lhs", "random", "sobol"):
            with self.subTest(method=method):
                config = self.load_config(
                    method=method,
                    output_name=method,
                )
                plan = WarmStartGenerator(config).generate()

                self.assertEqual(plan.method, method)
                self.assertEqual(plan.sample_count, 10)
                records = [
                    tuple(point.numeric_parameters().values())
                    for point in plan.points
                ]
                self.assertEqual(len(records), len(set(records)))
                for point in plan.points:
                    parameters = point.parameters
                    self.assertEqual(parameters.top_solid_layers, 5)
                    self.assertGreaterEqual(parameters.print_speed, 50)
                    self.assertLessEqual(parameters.print_speed, 90)
                    self.assertIsInstance(parameters.temperature, int)
                    self.assertIsInstance(parameters.fan_speed, int)

    def test_same_seed_reproduces_exact_plan(self) -> None:
        first_config = self.load_config(output_name="first")
        second_config = self.load_config(output_name="second")

        first = WarmStartGenerator(first_config).generate()
        second = WarmStartGenerator(second_config).generate()

        first_points = [point.numeric_parameters() for point in first.points]
        second_points = [point.numeric_parameters() for point in second.points]
        self.assertEqual(first_points, second_points)

    def test_different_seed_changes_plan(self) -> None:
        first = WarmStartGenerator(
            self.load_config(seed=42, output_name="first")
        ).generate()
        second = WarmStartGenerator(
            self.load_config(seed=43, output_name="second")
        ).generate()

        self.assertNotEqual(
            [point.numeric_parameters() for point in first.points],
            [point.numeric_parameters() for point in second.points],
        )

    def test_only_configured_variables_change(self) -> None:
        raw_config = config_payload(
            self.root / "subset_experiment",
            sample_count=5,
        )
        raw_config["parameters"] = [
            {"name": "extrusion_width", "lower": 0.40, "upper": 0.44}
        ]
        raw_config["fixed_parameters"] = {
            "top_solid_layers": 5,
            "print_speed": 70,
            "extrusion_multiplier": 1.10,
            "temperature": 220,
            "fan_speed": 55,
        }
        config_path = self.root / "subset.json"
        config_path.write_text(json.dumps(raw_config), encoding="utf-8")
        config = load_optimizer_config(config_path)

        plan = WarmStartGenerator(config).generate()

        self.assertEqual(plan.variable_names, ("extrusion_width",))
        self.assertEqual(
            {point.parameters.print_speed for point in plan.points},
            {70.0},
        )
        self.assertEqual(
            {point.parameters.temperature for point in plan.points},
            {220},
        )
        self.assertEqual(
            len({point.parameters.extrusion_width for point in plan.points}),
            5,
        )

    def test_top_solid_layers_can_be_sampled_as_integer_variable(self) -> None:
        raw_config = config_payload(
            self.root / "variable_layers",
            sample_count=6,
        )
        parameters = raw_config["parameters"]
        fixed_parameters = raw_config["fixed_parameters"]
        assert isinstance(parameters, list)
        assert isinstance(fixed_parameters, dict)
        parameters.insert(
            0,
            {"name": "top_solid_layers", "lower": 2, "upper": 8},
        )
        fixed_parameters.pop("top_solid_layers")
        path = self.root / "variable_layers.json"
        path.write_text(json.dumps(raw_config), encoding="utf-8")

        config = load_optimizer_config(path)
        plan = WarmStartGenerator(config).generate()
        layer_values = {
            point.parameters.top_solid_layers for point in plan.points
        }

        self.assertEqual(plan.variable_names[0], "top_solid_layers")
        self.assertTrue(layer_values.issubset(set(range(2, 9))))
        self.assertGreater(len(layer_values), 1)

    def test_rejects_more_samples_than_quantized_space(self) -> None:
        raw_config = config_payload(
            self.root / "tiny_experiment",
            sample_count=3,
        )
        raw_config["parameters"] = [
            {"name": "fan_speed", "lower": 30, "upper": 31}
        ]
        raw_config["fixed_parameters"] = {
            "top_solid_layers": 5,
            "print_speed": 70,
            "extrusion_width": 0.42,
            "extrusion_multiplier": 1.10,
            "temperature": 220,
        }
        config_path = self.root / "tiny.json"
        config_path.write_text(json.dumps(raw_config), encoding="utf-8")
        config = load_optimizer_config(config_path)

        with self.assertRaisesRegex(
            WarmStartError,
            "at most 2 different quantized parameter sets",
        ):
            WarmStartGenerator(config).generate()

    def test_next_point_is_persisted_before_hardware(self) -> None:
        config = self.load_config(sample_count=5)
        generator = WarmStartGenerator(config)
        plan = generator.generate()
        store = ExperimentStore.create(config)

        record = generator.propose_next(store)
        reopened = ExperimentStore.open(
            config.paths.output_directory,
            expected_config=config,
        )

        self.assertEqual(record.status, "proposed")
        self.assertEqual(record.run_number, 1)
        self.assertEqual(
            dict(record.parameters),
            plan.point_for_run(1).numeric_parameters(),
        )
        resumed = reopened.load_resume_run(from_run=1)
        self.assertIsNotNone(resumed)
        assert resumed is not None
        self.assertEqual(resumed.parameters, record.parameters)

    def test_existing_proposal_is_returned_not_replaced(self) -> None:
        config = self.load_config(sample_count=5)
        generator = WarmStartGenerator(config)
        store = ExperimentStore.create(config)

        first = generator.propose_next(store)
        second = generator.propose_next(store)

        self.assertEqual(first, second)
        self.assertEqual(first.run_number, 1)

    def test_completed_run_advances_to_next_plan_point(self) -> None:
        config = self.load_config(sample_count=5)
        generator = WarmStartGenerator(config)
        plan = generator.generate()
        store = ExperimentStore.create(config)
        first = generator.propose_next(store)
        store.mark_run_started(first.run_number)
        store.mark_run_completed(
            first.run_number,
            objective_value=4.2,
            ra_um=4.2,
            rz_um=20.0,
        )

        second = generator.propose_next(store)

        self.assertEqual(second.run_number, 2)
        self.assertEqual(
            dict(second.parameters),
            plan.point_for_run(2).numeric_parameters(),
        )


if __name__ == "__main__":
    unittest.main()

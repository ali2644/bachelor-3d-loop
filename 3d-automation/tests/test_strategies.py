from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

from optimizer.config import load_optimizer_config
from optimizer.experiment_store import StrategyCheckpoint
from optimizer.strategies import (
    BayesianStrategy,
    DifferentialEvolutionStrategy,
    Observation,
    PsoStrategy,
    RandomStrategy,
    SobolStrategy,
    StrategyError,
    build_strategy,
)
from optimizer.warm_start import WarmStartGenerator


def config_payload(
    output_directory: Path,
    strategy: str,
) -> dict[str, object]:
    options: dict[str, object]
    if strategy == "bayesian":
        options = {
            "acquisition": "ei",
            "candidate_count": 64,
            "n_restarts_optimizer": 0,
        }
    else:
        options = {}
    return {
        "schema_version": 1,
        "experiment_name": f"strategy_{strategy}",
        "total_runs": 12,
        "seed": 42,
        "objective": "Ra_um",
        "warm_start": {"method": "lhs", "sample_count": 4},
        "strategy": {"name": strategy, "options": options},
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


class StrategyAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def config(self, strategy: str):
        path = self.root / f"{strategy}.json"
        path.write_text(
            json.dumps(config_payload(self.root / strategy, strategy)),
            encoding="utf-8",
        )
        return load_optimizer_config(path)

    def warm_start_observations(self, config) -> tuple[Observation, ...]:
        plan = WarmStartGenerator(config).generate()
        return tuple(
            Observation(
                run_number=point.index,
                parameters=point.numeric_parameters(),
                objective_value=float(10 - point.index),
                strategy=config.strategy.name,
                optimizer_iteration=None,
            )
            for point in plan.points
        )

    @staticmethod
    def checkpoint(batch) -> StrategyCheckpoint:
        timestamp = datetime.now(timezone.utc).isoformat()
        return StrategyCheckpoint(
            schema_version=1,
            strategy=batch.strategy,
            iteration=batch.iteration,
            last_completed_run=4,
            state=MappingProxyType(dict(batch.checkpoint_state)),
            saved_at=timestamp,
        )

    @staticmethod
    def completed_batch_observations(
        batch,
        *,
        first_run_number: int = 5,
    ) -> tuple[Observation, ...]:
        return tuple(
            Observation(
                run_number=first_run_number + proposal.candidate_index,
                parameters=proposal.parameters,
                objective_value=float(5 - proposal.candidate_index),
                strategy=batch.strategy,
                optimizer_iteration=batch.iteration,
            )
            for proposal in batch.proposals
        )

    def test_factory_builds_every_configured_strategy(self) -> None:
        expected_types = {
            "bayesian": BayesianStrategy,
            "pso": PsoStrategy,
            "differential_evolution": DifferentialEvolutionStrategy,
            "random": RandomStrategy,
            "sobol": SobolStrategy,
        }
        for name, expected_type in expected_types.items():
            with self.subTest(strategy=name):
                strategy = build_strategy(self.config(name))
                self.assertIsInstance(strategy, expected_type)

    def test_every_strategy_proposes_valid_unique_json_state(self) -> None:
        expected_counts = {
            "bayesian": 1,
            "pso": 4,
            "differential_evolution": 4,
            "random": 4,
            "sobol": 4,
        }
        for name, expected_count in expected_counts.items():
            with self.subTest(strategy=name):
                config = self.config(name)
                observations = self.warm_start_observations(config)
                batch = build_strategy(config).propose(observations)

                self.assertEqual(batch.strategy, name)
                self.assertEqual(batch.iteration, 0)
                self.assertEqual(len(batch.proposals), expected_count)
                parameter_sets = [
                    tuple(proposal.parameters.values())
                    for proposal in batch.proposals
                ]
                self.assertEqual(
                    len(parameter_sets),
                    len(set(parameter_sets)),
                )
                json.dumps(batch.as_dict(), allow_nan=False)

    def test_pso_and_de_advance_after_complete_batch(self) -> None:
        for name in ("pso", "differential_evolution"):
            with self.subTest(strategy=name):
                config = self.config(name)
                warm_start = self.warm_start_observations(config)
                strategy = build_strategy(config)
                first_batch = strategy.propose(warm_start)
                completed = self.completed_batch_observations(first_batch)

                second_batch = strategy.propose(
                    (*warm_start, *completed),
                    self.checkpoint(first_batch),
                )

                self.assertEqual(second_batch.iteration, 1)
                self.assertEqual(len(second_batch.proposals), 4)
                json.dumps(second_batch.as_dict(), allow_nan=False)

    def test_strategy_refuses_to_advance_with_missing_batch_result(self) -> None:
        config = self.config("pso")
        warm_start = self.warm_start_observations(config)
        strategy = build_strategy(config)
        first_batch = strategy.propose(warm_start)
        incomplete = self.completed_batch_observations(first_batch)[:-1]

        with self.assertRaisesRegex(
            StrategyError,
            "requires 4 completed results, but 3 are available",
        ):
            strategy.propose(
                (*warm_start, *incomplete),
                self.checkpoint(first_batch),
            )

    def test_same_seed_and_history_reproduce_first_batch(self) -> None:
        for name in (
            "bayesian",
            "pso",
            "differential_evolution",
            "random",
            "sobol",
        ):
            with self.subTest(strategy=name):
                config = self.config(name)
                observations = self.warm_start_observations(config)

                first = build_strategy(config).propose(observations)
                second = build_strategy(config).propose(observations)

                self.assertEqual(first.as_dict(), second.as_dict())


if __name__ == "__main__":
    unittest.main()

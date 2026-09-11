from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from optimizer.config import load_optimizer_config
from optimizer.experiment_store import ExperimentStoreError
from optimizer.framework_runner import (
    FRAMEWORK_BATCH_KEY,
    FailurePolicy,
    FrameworkRunner,
    FrameworkRunnerError,
    RunExecutorError,
    SyntheticSurfaceExecutor,
)
from optimizer.strategies import observations_from_store


def config_payload(
    output_directory: Path,
    strategy: str,
    *,
    total_runs: int,
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
        "experiment_name": f"runner_{strategy}",
        "total_runs": total_runs,
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


class FailOnceExecutor:
    def __init__(self, wrapped: SyntheticSurfaceExecutor) -> None:
        self.wrapped = wrapped
        self.failed = False

    def execute(self, run):
        if not self.failed:
            self.failed = True
            raise RunExecutorError(
                "simulated connection loss",
                retryable=True,
                failed_stage="simulation",
            )
        return self.wrapped.execute(run)


class AlwaysComparableFailureExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, run):
        self.calls.append(run)
        raise RunExecutorError(
            "simulated comparable failure",
            retryable=True,
            failed_stage="measurement_penalty",
        )


class FrameworkRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def config(
        self,
        strategy: str,
        *,
        total_runs: int,
        label: str = "experiment",
    ):
        config_path = self.root / f"{label}_{strategy}.json"
        output_directory = self.root / label / strategy
        config_path.write_text(
            json.dumps(
                config_payload(
                    output_directory,
                    strategy,
                    total_runs=total_runs,
                )
            ),
            encoding="utf-8",
        )
        return load_optimizer_config(config_path)

    def runner(self, config) -> FrameworkRunner:
        return FrameworkRunner.create(
            config,
            SyntheticSurfaceExecutor(config),
        )

    def test_every_strategy_completes_a_small_simulation(self) -> None:
        totals = {
            "bayesian": 5,
            "pso": 8,
            "differential_evolution": 8,
            "random": 8,
            "sobol": 8,
        }
        for strategy, total_runs in totals.items():
            with self.subTest(strategy=strategy):
                config = self.config(
                    strategy,
                    total_runs=total_runs,
                    label=f"all_{strategy}",
                )
                runner = self.runner(config)

                completed = runner.run()

                self.assertEqual(len(completed), total_runs)
                self.assertEqual(runner.store.state.status, "completed")
                results_path = runner.store.directory / "results.csv"
                with results_path.open(
                    "r",
                    encoding="utf-8",
                    newline="",
                ) as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(len(rows), total_runs)

    def test_bayesian_framework_supports_six_variable_parameters(self) -> None:
        output_directory = self.root / "six_variables" / "bayesian"
        payload = config_payload(
            output_directory,
            "bayesian",
            total_runs=5,
        )
        parameters = payload["parameters"]
        fixed_parameters = payload["fixed_parameters"]
        assert isinstance(parameters, list)
        assert isinstance(fixed_parameters, dict)
        parameters.insert(
            0,
            {"name": "top_solid_layers", "lower": 2, "upper": 8},
        )
        parameters[1] = {
            "name": "print_speed",
            "lower": 20,
            "upper": 180,
        }
        fixed_parameters.pop("top_solid_layers")
        path = self.root / "six_variables.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        config = load_optimizer_config(path)

        runner = self.runner(config)
        completed = runner.run()

        self.assertEqual(len(completed), 5)
        self.assertEqual(runner.store.state.status, "completed")
        self.assertTrue(
            all(
                2 <= int(record.parameters["top_solid_layers"]) <= 8
                for record in completed
            )
        )

    def test_objective_expression_uses_all_recorded_metrics(self) -> None:
        output_directory = self.root / "formula" / "bayesian"
        payload = config_payload(
            output_directory,
            "bayesian",
            total_runs=5,
        )
        payload["objective"] = (
            "5 + print_time_minutes * Ra_um + Rz_um"
        )
        path = self.root / "formula.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        config = load_optimizer_config(path)

        completed = self.runner(config).run(max_runs=1)[0]

        assert completed.ra_um is not None
        assert completed.rz_um is not None
        assert completed.print_time_seconds is not None
        expected = (
            5
            + (completed.print_time_seconds / 60.0) * completed.ra_um
            + completed.rz_um
        )
        self.assertAlmostEqual(completed.objective_value, expected)

    def test_batch_is_checkpointed_before_first_main_run(self) -> None:
        config = self.config("pso", total_runs=8)
        runner = self.runner(config)
        runner.run(max_runs=4)

        proposed = runner.prepare_next_run()
        checkpoint = runner.store.load_latest_strategy_checkpoint("pso")

        self.assertIsNotNone(proposed)
        self.assertIsNotNone(checkpoint)
        assert proposed is not None
        assert checkpoint is not None
        self.assertEqual(proposed.run_number, 5)
        self.assertEqual(proposed.status, "proposed")
        self.assertEqual(checkpoint.last_completed_run, 4)
        batch = checkpoint.state[FRAMEWORK_BATCH_KEY]
        self.assertIsInstance(batch, dict)
        assert isinstance(batch, dict)
        self.assertEqual(len(batch["proposals"]), 4)
        self.assertEqual(
            proposed.parameters,
            batch["proposals"][0]["parameters"],
        )

    def test_resume_continues_saved_pso_batch_and_state(self) -> None:
        config = self.config("pso", total_runs=12)
        first_runner = self.runner(config)
        first_runner.run(max_runs=6)
        checkpoint_before = (
            first_runner.store.load_latest_strategy_checkpoint("pso")
        )
        assert checkpoint_before is not None
        saved_batch = checkpoint_before.state[FRAMEWORK_BATCH_KEY]
        assert isinstance(saved_batch, dict)

        resumed = FrameworkRunner.resume(
            config,
            SyntheticSurfaceExecutor(config),
            from_run=7,
        )
        resumed.run()

        self.assertEqual(resumed.store.state.status, "completed")
        for offset, expected in enumerate(saved_batch["proposals"]):
            record = resumed.store.load_run(5 + offset)
            self.assertEqual(record.parameters, expected["parameters"])
        checkpoint_after = resumed.store.load_latest_strategy_checkpoint(
            "pso"
        )
        assert checkpoint_after is not None
        self.assertEqual(checkpoint_after.iteration, 1)

    def test_running_run_is_not_repeated_automatically(self) -> None:
        config = self.config("bayesian", total_runs=5)
        runner = self.runner(config)
        runner.run(max_runs=4)
        proposed = runner.prepare_next_run()
        assert proposed is not None
        runner.store.mark_run_started(proposed.run_number)

        resumed = FrameworkRunner.resume(
            config,
            SyntheticSurfaceExecutor(config),
            from_run=5,
        )

        with self.assertRaisesRegex(
            FrameworkRunnerError,
            "still marked running",
        ):
            resumed.execute_next()

    def test_retry_requires_explicit_permission_and_keeps_parameters(
        self,
    ) -> None:
        config = self.config("bayesian", total_runs=5)
        executor = FailOnceExecutor(SyntheticSurfaceExecutor(config))
        runner = FrameworkRunner.create(config, executor)

        with self.assertRaisesRegex(FrameworkRunnerError, "attempt 1/2"):
            runner.run(max_runs=1)
        failed = runner.store.load_run(1)

        with self.assertRaisesRegex(FrameworkRunnerError, "retry_failed"):
            runner.run(max_runs=1)
        completed = runner.run(max_runs=1, retry_failed=True)[0]

        self.assertEqual(completed.attempt_number, 2)
        self.assertEqual(completed.parameters, failed.parameters)
        self.assertEqual(completed.status, "completed")

    def test_automatic_retry_succeeds_with_same_parameters(self) -> None:
        config = self.config("bayesian", total_runs=5, label="auto_retry")
        executor = FailOnceExecutor(SyntheticSurfaceExecutor(config))
        runner = FrameworkRunner.create(config, executor)

        completed = runner.run(max_runs=1, automatic_retry=True)[0]

        self.assertEqual(completed.attempt_number, 2)
        history = list(
            (runner.store.directory / "attempt_history").glob("*.json")
        )
        self.assertEqual(len(history), 1)

    def test_automatic_retry_resumes_an_already_saved_first_failure(
        self,
    ) -> None:
        config = self.config(
            "bayesian",
            total_runs=5,
            label="saved_auto_retry",
        )
        first = FrameworkRunner.create(
            config,
            AlwaysComparableFailureExecutor(),
        )
        with self.assertRaises(FrameworkRunnerError):
            first.run(max_runs=1)
        failed = first.store.load_run(1)

        resumed = FrameworkRunner.resume(
            config,
            SyntheticSurfaceExecutor(config),
            from_run=1,
        )
        completed = resumed.run(max_runs=1, automatic_retry=True)[0]

        self.assertEqual(completed.attempt_number, 2)
        self.assertEqual(completed.parameters, failed.parameters)
        self.assertFalse(completed.is_penalty)
        self.assertFalse(completed.is_ignored)

    def test_second_failure_can_be_excluded_from_optimizer(self) -> None:
        config = self.config("bayesian", total_runs=5, label="ignored")
        executor = AlwaysComparableFailureExecutor()
        runner = FrameworkRunner.create(
            config,
            executor,
            failure_policy=FailurePolicy(
                use_penalty_for_optimizer=False,
            ),
        )

        completed = runner.run(max_runs=1, automatic_retry=True)[0]

        self.assertTrue(completed.is_ignored)
        self.assertIsNone(completed.objective_value)
        self.assertEqual(len(observations_from_store(runner.store)), 0)
        self.assertEqual(len(executor.calls), 2)

    def test_three_failed_parameter_sets_stop_automatic_run(self) -> None:
        config = self.config("bayesian", total_runs=5, label="three_failed")
        executor = AlwaysComparableFailureExecutor()
        runner = FrameworkRunner.create(
            config,
            executor,
            failure_policy=FailurePolicy(use_penalty_for_optimizer=True),
        )

        completed = runner.run(max_runs=5, automatic_retry=True)

        self.assertEqual(len(completed), 3)
        self.assertEqual(len(executor.calls), 6)
        self.assertEqual(runner.store.state.status, "blocked")
        self.assertEqual(
            runner.store.state.consecutive_failed_parameter_sets,
            3,
        )
        self.assertEqual(len(observations_from_store(runner.store)), 3)

    def test_resume_refuses_wrong_from_run(self) -> None:
        config = self.config("bayesian", total_runs=5)
        runner = self.runner(config)
        runner.run(max_runs=2)

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "safe resume point is run 3",
        ):
            FrameworkRunner.resume(
                config,
                SyntheticSurfaceExecutor(config),
                from_run=4,
            )

    def test_unsupported_history_is_rejected_before_directory_creation(
        self,
    ) -> None:
        output_directory = self.root / "with_history" / "bayesian"
        payload = config_payload(
            output_directory,
            "bayesian",
            total_runs=5,
        )
        paths = payload["paths"]
        assert isinstance(paths, dict)
        paths["history_csvs"] = ["history.csv"]
        config_path = self.root / "with_history.json"
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        config = load_optimizer_config(config_path)

        with self.assertRaisesRegex(
            FrameworkRunnerError,
            "history_csvs import is not implemented",
        ):
            FrameworkRunner.create(
                config,
                SyntheticSurfaceExecutor(config),
            )

        self.assertFalse(output_directory.exists())


if __name__ == "__main__":
    unittest.main()

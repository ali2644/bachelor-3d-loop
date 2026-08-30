from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from optimizer.config import load_optimizer_config
from optimizer.experiment_store import (
    ExperimentStore,
    ExperimentStoreError,
)


def config_payload(output_directory: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "experiment_name": "store_test",
        "total_runs": 20,
        "seed": 42,
        "objective": "Ra_um",
        "warm_start": {"method": "lhs", "sample_count": 5},
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


def proposal(print_speed: float = 70.04) -> dict[str, int | float]:
    return {
        "print_speed": print_speed,
        "extrusion_width": 0.4214,
        "extrusion_multiplier": 1.0746,
        "temperature": 220.4,
        "fan_speed": 54.7,
        "top_solid_layers": 5,
    }


class ExperimentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.config_path = self.root / "optimizer.json"
        self.output_directory = self.root / "runs" / "store_test"
        self.config_path.write_text(
            json.dumps(config_payload(self.output_directory)),
            encoding="utf-8",
        )
        self.config = load_optimizer_config(self.config_path)

    def test_create_writes_snapshot_state_and_directories(self) -> None:
        store = ExperimentStore.create(self.config)

        self.assertEqual(store.state.status, "ready")
        self.assertEqual(store.state.completed_runs, 0)
        self.assertTrue(
            (self.output_directory / "config_snapshot.json").is_file()
        )
        self.assertTrue((self.output_directory / "run_state.json").is_file())
        for child in (
            "runs",
            "optimizer_state",
            "generated_profiles",
            "gcode",
            "logs",
        ):
            self.assertTrue((self.output_directory / child).is_dir())

    def test_saved_proposal_is_loaded_after_reopen(self) -> None:
        store = ExperimentStore.create(self.config)
        saved = store.propose_run(
            proposal(),
            strategy="BO",
            optimizer_iteration=0,
        )

        reopened = ExperimentStore.open(
            self.output_directory,
            expected_config=self.config,
        )
        resumed = reopened.load_resume_run(from_run=1)

        self.assertIsNotNone(resumed)
        assert resumed is not None
        self.assertEqual(resumed.parameters, saved.parameters)
        self.assertEqual(resumed.status, "proposed")
        self.assertEqual(resumed.parameters["print_speed"], 70.0)
        self.assertEqual(resumed.parameters["temperature"], 220)
        self.assertEqual(resumed.parameters["fan_speed"], 55)

    def test_retry_keeps_parameters_and_increments_attempt(self) -> None:
        store = ExperimentStore.create(self.config)
        first = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(first.run_number)
        failed = store.mark_attempt_failed(
            first.run_number,
            error="Printer status unavailable",
            failed_stage="waiting_for_print",
            maximum_attempts=2,
            penalty_value=100.0,
            use_penalty_for_optimizer=True,
            maximum_consecutive_failed_parameter_sets=3,
        )

        retried = store.prepare_retry(
            first.run_number,
            maximum_attempts=2,
        )

        self.assertEqual(failed.status, "retryable_failed")
        self.assertEqual(retried.status, "proposed")
        self.assertEqual(retried.attempt_number, 2)
        self.assertEqual(retried.soft_failure_count, 1)
        self.assertEqual(retried.parameters, first.parameters)
        self.assertIsNone(retried.error)
        self.assertEqual(store.next_run_number(), 1)

    def test_second_comparable_failure_completes_with_penalty(self) -> None:
        store = ExperimentStore.create(self.config)
        first = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(first.run_number)
        store.mark_attempt_failed(
            first.run_number,
            error="first measurement failure",
            failed_stage="measurement_penalty",
            maximum_attempts=2,
            penalty_value=100.0,
            use_penalty_for_optimizer=True,
            maximum_consecutive_failed_parameter_sets=3,
        )
        store.prepare_retry(first.run_number, maximum_attempts=2)
        store.mark_run_started(first.run_number)

        completed = store.mark_attempt_failed(
            first.run_number,
            error="second measurement failure",
            failed_stage="measurement_penalty",
            maximum_attempts=2,
            penalty_value=100.0,
            use_penalty_for_optimizer=True,
            maximum_consecutive_failed_parameter_sets=3,
        )

        self.assertEqual(completed.status, "completed")
        self.assertTrue(completed.is_penalty)
        self.assertEqual(completed.objective_value, 100.0)
        self.assertIsNone(completed.ra_um)
        self.assertIsNone(completed.rz_um)
        self.assertEqual(completed.soft_failure_count, 2)
        self.assertEqual(store.state.consecutive_penalty_runs, 1)
        self.assertEqual(store.next_run_number(), 2)

    def test_third_consecutive_penalty_pauses_until_acknowledged(self) -> None:
        store = ExperimentStore.create(self.config)

        for run_number in range(1, 4):
            run = store.propose_run(proposal(60 + run_number), strategy="bayesian")
            store.mark_run_started(run.run_number)
            store.mark_attempt_failed(
                run.run_number,
                error="first failure",
                failed_stage="measurement_penalty",
                maximum_attempts=2,
                penalty_value=100.0,
                use_penalty_for_optimizer=True,
                maximum_consecutive_failed_parameter_sets=3,
            )
            store.prepare_retry(run.run_number, maximum_attempts=2)
            store.mark_run_started(run.run_number)
            store.mark_attempt_failed(
                run.run_number,
                error="second failure",
                failed_stage="measurement_penalty",
                maximum_attempts=2,
                penalty_value=100.0,
                use_penalty_for_optimizer=True,
                maximum_consecutive_failed_parameter_sets=3,
            )

        self.assertEqual(store.state.status, "blocked")
        self.assertEqual(store.state.consecutive_penalty_runs, 3)
        self.assertEqual(store.state.consecutive_failed_parameter_sets, 3)
        self.assertEqual(store.state.resume_run_number, 4)
        self.assertIn(
            "3 consecutive failed parameter sets",
            store.state.pause_reason or "",
        )

        store.acknowledge_penalty_pause(4)

        self.assertEqual(store.state.status, "ready")
        self.assertIsNone(store.state.pause_reason)
        self.assertEqual(store.next_run_number(), 4)

    def test_measured_result_resets_consecutive_penalty_counter(self) -> None:
        store = ExperimentStore.create(self.config)
        for run_number in range(1, 3):
            run = store.propose_run(proposal(60 + run_number), strategy="bayesian")
            store.mark_run_started(run.run_number)
            store.mark_attempt_failed(
                run.run_number,
                error="first failure",
                failed_stage="measurement_penalty",
                maximum_attempts=1,
                penalty_value=100.0,
                use_penalty_for_optimizer=True,
                maximum_consecutive_failed_parameter_sets=3,
            )
        measured = store.propose_run(proposal(70), strategy="bayesian")
        store.mark_run_started(measured.run_number)
        store.mark_run_completed(
            measured.run_number,
            objective_value=4.2,
            ra_um=4.2,
            rz_um=21.0,
        )

        self.assertEqual(store.state.consecutive_penalty_runs, 0)
        self.assertEqual(store.state.consecutive_failed_parameter_sets, 0)
        self.assertEqual(store.state.status, "ready")

    def test_second_failure_can_be_ignored_without_optimizer_value(self) -> None:
        store = ExperimentStore.create(self.config)
        run = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(run.run_number)
        completed = store.mark_attempt_failed(
            run.run_number,
            error="second failure",
            failed_stage="measurement_penalty",
            maximum_attempts=1,
            penalty_value=100.0,
            use_penalty_for_optimizer=False,
            maximum_consecutive_failed_parameter_sets=3,
        )

        self.assertTrue(completed.is_ignored)
        self.assertFalse(completed.is_penalty)
        self.assertIsNone(completed.objective_value)
        self.assertEqual(store.state.consecutive_ignored_runs, 1)
        self.assertEqual(store.state.consecutive_failed_parameter_sets, 1)

    def test_failure_observation_mode_is_persisted_and_immutable(self) -> None:
        store = ExperimentStore.create(self.config)

        self.assertEqual(
            store.configure_failure_observation_mode("penalty"),
            "penalty",
        )
        reopened = ExperimentStore.open(self.output_directory)
        self.assertEqual(reopened.state.failure_observation_mode, "penalty")
        with self.assertRaisesRegex(ExperimentStoreError, "changing it"):
            reopened.configure_failure_observation_mode("ignore")

    def test_manual_stop_never_creates_penalty(self) -> None:
        store = ExperimentStore.create(self.config)
        run = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(run.run_number)

        stopped = store.mark_manual_stop(
            run.run_number,
            error="robot collision",
            failed_stage="robot_handling",
        )

        self.assertEqual(stopped.status, "terminal_failed")
        self.assertFalse(stopped.is_penalty)
        self.assertIsNone(stopped.objective_value)
        resumed = store.prepare_manual_resume(run.run_number)
        self.assertEqual(resumed.attempt_number, 2)
        self.assertEqual(resumed.soft_failure_count, 0)
        self.assertEqual(resumed.parameters, run.parameters)

    def test_legacy_measurement_failure_can_be_retried_as_attempt_two(
        self,
    ) -> None:
        """Upgrade the already-saved step-8 measurement failure safely."""
        store = ExperimentStore.create(self.config)
        original = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(original.run_number)
        store.mark_manual_stop(
            original.run_number,
            error="legacy QS measurement failure",
            failed_stage="measurement_penalty",
        )

        run_path = self.output_directory / "runs" / "run_0001.json"
        legacy_run = json.loads(run_path.read_text(encoding="utf-8"))
        legacy_run.pop("is_penalty")
        legacy_run.pop("soft_failure_count")
        run_path.write_text(json.dumps(legacy_run), encoding="utf-8")

        state_path = self.output_directory / "run_state.json"
        legacy_state = json.loads(state_path.read_text(encoding="utf-8"))
        legacy_state.pop("consecutive_penalty_runs")
        legacy_state.pop("pause_reason")
        legacy_state.pop("resume_run_number")
        state_path.write_text(json.dumps(legacy_state), encoding="utf-8")

        reopened = ExperimentStore.open(self.output_directory)
        retried = reopened.prepare_retry(1, maximum_attempts=2)

        self.assertEqual(retried.status, "proposed")
        self.assertEqual(retried.attempt_number, 2)
        self.assertEqual(retried.soft_failure_count, 1)
        self.assertEqual(retried.parameters, original.parameters)
        self.assertEqual(reopened.state.consecutive_penalty_runs, 0)

    def test_completed_run_advances_to_next_run(self) -> None:
        store = ExperimentStore.create(self.config)
        run = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(run.run_number)
        completed = store.mark_run_completed(
            run.run_number,
            objective_value=4.12,
            ra_um=4.12,
            rz_um=20.7,
            cycle_id="cycle-1",
        )

        self.assertEqual(completed.status, "completed")
        self.assertEqual(store.next_run_number(), 2)
        self.assertEqual(store.state.completed_runs, 1)
        self.assertEqual(store.state.status, "ready")

    def test_running_run_is_not_silently_replaced(self) -> None:
        store = ExperimentStore.create(self.config)
        run = store.propose_run(proposal(), strategy="bayesian")
        store.mark_run_started(run.run_number)

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "already has a saved proposal",
        ):
            store.propose_run(proposal(80), strategy="bayesian")

        resumed = store.load_resume_run()
        self.assertIsNotNone(resumed)
        assert resumed is not None
        self.assertEqual(resumed.run_number, 1)
        self.assertEqual(resumed.status, "running")

    def test_open_repairs_summary_after_interrupted_summary_write(self) -> None:
        store = ExperimentStore.create(self.config)
        store.propose_run(proposal(), strategy="bayesian")
        state_path = self.output_directory / "run_state.json"
        stale_state = json.loads(state_path.read_text(encoding="utf-8"))
        stale_state["status"] = "ready"
        stale_state["current_run_number"] = None
        state_path.write_text(
            json.dumps(stale_state),
            encoding="utf-8",
        )

        reopened = ExperimentStore.open(self.output_directory)

        self.assertEqual(reopened.state.status, "running")
        self.assertEqual(reopened.state.current_run_number, 1)

    def test_resume_cannot_skip_first_unfinished_run(self) -> None:
        store = ExperimentStore.create(self.config)
        store.propose_run(proposal(), strategy="bayesian")

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "safe resume point is run 1",
        ):
            store.load_resume_run(from_run=2)

    def test_strategy_checkpoints_are_immutable_and_reloaded(self) -> None:
        store = ExperimentStore.create(self.config)
        store.save_strategy_checkpoint(
            strategy="bayesian",
            iteration=0,
            last_completed_run=0,
            state={"kernel": {"length_scale": [0.3, 0.7]}},
        )

        checkpoint = store.load_latest_strategy_checkpoint("BO")

        self.assertIsNotNone(checkpoint)
        assert checkpoint is not None
        self.assertEqual(checkpoint.iteration, 0)
        self.assertEqual(checkpoint.last_completed_run, 0)
        self.assertEqual(
            checkpoint.state["kernel"],
            {"length_scale": [0.3, 0.7]},
        )
        with self.assertRaisesRegex(
            ExperimentStoreError,
            "checkpoint already exists",
        ):
            store.save_strategy_checkpoint(
                strategy="bayesian",
                iteration=0,
                last_completed_run=0,
                state={"different": True},
            )

    def test_checkpoint_cannot_claim_unpersisted_completed_runs(self) -> None:
        store = ExperimentStore.create(self.config)

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "greater than the number of persisted completed runs",
        ):
            store.save_strategy_checkpoint(
                strategy="bayesian",
                iteration=0,
                last_completed_run=1,
                state={},
            )

    def test_resume_refuses_changed_configuration(self) -> None:
        ExperimentStore.create(self.config)
        changed_payload = config_payload(self.output_directory)
        changed_payload["seed"] = 99
        changed_path = self.root / "changed.json"
        changed_path.write_text(
            json.dumps(changed_payload),
            encoding="utf-8",
        )
        changed_config = load_optimizer_config(changed_path)

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "differs from the saved experiment configuration",
        ):
            ExperimentStore.open(
                self.output_directory,
                expected_config=changed_config,
            )

    def test_existing_output_directory_is_not_overwritten(self) -> None:
        self.output_directory.mkdir(parents=True)
        sentinel = self.output_directory / "keep.txt"
        sentinel.write_text("user data", encoding="utf-8")

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "refusing to overwrite",
        ):
            ExperimentStore.create(self.config)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "user data")


if __name__ == "__main__":
    unittest.main()

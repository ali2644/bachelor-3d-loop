from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from optimizer.config import load_optimizer_config
from optimizer.experiment_store import ExperimentStore, ExperimentStoreError
from optimizer.hardware_cli import (
    HardwareCliError,
    parse_arguments,
    run_hardware_command,
)
from orchestrator import (
    CycleExecutionError,
    CycleResult,
    CycleStage,
    CycleStatus,
)


def config_payload(output_directory: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "experiment_name": output_directory.name,
        "total_runs": 5,
        "seed": 42,
        "objective": "Ra_um",
        "warm_start": {"method": "lhs", "sample_count": 4},
        "strategy": {
            "name": "bayesian",
            "options": {
                "acquisition": "ei",
                "candidate_count": 64,
                "n_restarts_optimizer": 0,
            },
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
            "base_profile": "slicer_profile.ini",
            "output_directory": str(output_directory),
            "history_csvs": [],
        },
    }


class FakeOrchestrator:
    def __init__(self, cycle_errors=None) -> None:
        self.preflight_requests = []
        self.cycle_requests = []
        self.cycle_errors = list(cycle_errors or [])

    def run_preflight(self, request, *, include_printer=True) -> None:
        self.preflight_requests.append(request)

    def run_single_print_cycle(self, request):
        self.cycle_requests.append(request)
        result_error = (
            self.cycle_errors.pop(0) if self.cycle_errors else None
        )
        now = datetime.now(timezone.utc)
        return CycleResult(
            cycle_id=f"cycle-{len(self.cycle_requests)}",
            mode="full",
            status=CycleStatus.COMPLETED,
            stage=CycleStage.COMPLETED,
            started_at=now,
            finished_at=now,
            duration_seconds=1.0,
            stl_path=request.stl_path,
            profile_path=request.profile_path,
            gcode_path=request.gcode_path,
            profile_sha256="test-sha256",
            print_parameters=request.print_parameters,
            print_time_seconds=615.25,
            measurements={"Ra": 4.25, "Rz": 21.5},
            printer_states=("PRINTING", "FINISHED"),
            error=result_error,
        )


class CapturingBuilder:
    def __init__(
        self,
        *,
        fail_preflight: bool = False,
        cycle_errors=None,
    ) -> None:
        self.results_paths: list[Path] = []
        self.camera_directories: list[str | None] = []
        self.orchestrators: list[FakeOrchestrator] = []
        self.fail_preflight = fail_preflight
        self.cycle_errors = list(cycle_errors or [])

    def __call__(self, results_csv: Path) -> FakeOrchestrator:
        self.results_paths.append(results_csv)
        self.camera_directories.append(
            os.environ.get("CAMERA_DOWNLOAD_DIR")
        )
        orchestrator = FakeOrchestrator(self.cycle_errors)
        if self.fail_preflight:
            def fail(request, *, include_printer=True) -> None:
                orchestrator.preflight_requests.append(request)
                raise CycleExecutionError(
                    CycleStage.PREFLIGHT,
                    "simulated robot connection timeout",
                )

            orchestrator.run_preflight = fail
        self.orchestrators.append(orchestrator)
        return orchestrator


class HardwareCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        (self.root / "part.stl").write_text(
            "solid part\nendsolid part\n",
            encoding="utf-8",
        )
        (self.root / "slicer_profile.ini").write_text(
            "\n".join(
                (
                    "top_solid_layers = 5",
                    "top_solid_infill_speed = 80",
                    "top_infill_extrusion_width = 0.42",
                    "extrusion_multiplier = 1.0",
                    "temperature = 220",
                    "min_fan_speed = 80",
                    "max_fan_speed = 80",
                    "bridge_fan_speed = 80",
                    "skirts = 0",
                    "brim_width = 0",
                    "top_solid_min_thickness = 0",
                    "slowdown_below_layer_time = 0",
                    "enable_dynamic_fan_speeds = 0",
                    "",
                )
            ),
            encoding="utf-8",
        )

    def config_path(self, label: str) -> tuple[Path, Path]:
        output_directory = self.root / "runs" / label
        path = self.root / f"{label}.json"
        path.write_text(
            json.dumps(config_payload(output_directory)),
            encoding="utf-8",
        )
        return path, output_directory

    def arguments(self, config_path: Path, *options: str):
        return parse_arguments([str(config_path), *options])

    def test_hardware_confirmation_is_required_before_any_state_write(
        self,
    ) -> None:
        config_path, output_directory = self.config_path("no_confirmation")
        arguments = self.arguments(config_path, "--resume")

        with self.assertRaisesRegex(
            HardwareCliError,
            "requires --confirm-hardware",
        ):
            run_hardware_command(
                arguments,
                orchestrator_builder=CapturingBuilder(),
            )

        self.assertFalse(output_directory.exists())

    def test_new_preflight_persists_proposal_without_running_cycle(
        self,
    ) -> None:
        config_path, output_directory = self.config_path("preflight")
        builder = CapturingBuilder()
        previous_camera_directory = os.environ.get("CAMERA_DOWNLOAD_DIR")

        result = run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=builder,
        )

        self.assertEqual(result["mode"], "optimizer_hardware_preflight")
        self.assertEqual(result["run_number"], 1)
        self.assertFalse(result["hardware_started"])
        self.assertIsNotNone(result["preflight_receipt"])
        self.assertEqual(len(builder.orchestrators), 1)
        self.assertEqual(len(builder.orchestrators[0].preflight_requests), 1)
        self.assertEqual(builder.orchestrators[0].cycle_requests, [])
        store = ExperimentStore.open(output_directory)
        self.assertEqual(store.load_run(1).status, "proposed")
        self.assertEqual(
            builder.results_paths[0],
            output_directory / "hardware_cycles.csv",
        )
        self.assertEqual(
            builder.camera_directories[0],
            str(output_directory / "images"),
        )
        self.assertEqual(
            os.environ.get("CAMERA_DOWNLOAD_DIR"),
            previous_camera_directory,
        )
        self.assertTrue(
            (output_directory / "logs/optimizer_hardware.log").is_file()
        )
        self.assertTrue(
            (
                output_directory
                / "logs/preflight_run_0001_attempt_01.json"
            ).is_file()
        )

    def test_ignore_failure_result_is_persisted_at_experiment_start(
        self,
    ) -> None:
        config_path, output_directory = self.config_path("ignore_mode")

        run_hardware_command(
            self.arguments(
                config_path,
                "--new",
                "--failure-result",
                "ignore",
                "--preflight-only",
            ),
            orchestrator_builder=CapturingBuilder(),
        )

        store = ExperimentStore.open(output_directory)
        self.assertEqual(store.state.failure_observation_mode, "ignore")

    def test_failed_preflight_does_not_consume_physical_attempt(self) -> None:
        config_path, output_directory = self.config_path("preflight_failure")

        with self.assertRaisesRegex(
            RuntimeError,
            "simulated robot connection timeout",
        ):
            run_hardware_command(
                self.arguments(config_path, "--new", "--preflight-only"),
                orchestrator_builder=CapturingBuilder(fail_preflight=True),
            )

        failed = ExperimentStore.open(output_directory).load_run(1)
        self.assertEqual(failed.status, "retryable_failed")
        self.assertEqual(failed.attempt_number, 1)
        self.assertEqual(failed.soft_failure_count, 0)
        self.assertIsNone(failed.started_at)

        result = run_hardware_command(
            self.arguments(
                config_path,
                "--resume",
                "--from-run",
                "1",
                "--retry-failed",
                "--preflight-only",
            ),
            orchestrator_builder=CapturingBuilder(),
        )

        self.assertEqual(result["attempt_number"], 1)
        retried = ExperimentStore.open(output_directory).load_run(1)
        self.assertEqual(retried.status, "proposed")
        self.assertEqual(retried.attempt_number, 1)

    def test_confirmed_resume_executes_only_one_run_by_default(self) -> None:
        config_path, output_directory = self.config_path("resume_one")
        builder = CapturingBuilder()
        run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=builder,
        )

        result = run_hardware_command(
            self.arguments(
                config_path,
                "--resume",
                "--from-run",
                "1",
                "--confirm-hardware",
            ),
            orchestrator_builder=builder,
        )

        self.assertEqual(result["completed_in_this_call"], 1)
        self.assertEqual(result["completed_total"], 1)
        self.assertEqual(result["next_run_number"], 2)
        self.assertEqual(
            result["last_completed_result"]["print_time_seconds"],
            615.25,
        )
        self.assertEqual(len(builder.orchestrators[-1].cycle_requests), 1)
        store = ExperimentStore.open(output_directory)
        completed = store.load_run(1)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.ra_um, 4.25)

    def test_automatic_batch_retries_once_and_continues(self) -> None:
        config_path, output_directory = self.config_path("automatic_batch")
        run_hardware_command(
            self.arguments(
                config_path,
                "--new",
                "--preflight-only",
                "--failure-result",
                "penalty",
            ),
            orchestrator_builder=CapturingBuilder(),
        )
        builder = CapturingBuilder(
            cycle_errors=["simulated measurement failure", None, None]
        )

        result = run_hardware_command(
            self.arguments(
                config_path,
                "--resume",
                "--from-run",
                "1",
                "--max-runs",
                "2",
                "--automatic-retry",
                "--confirm-hardware",
            ),
            orchestrator_builder=builder,
        )

        self.assertEqual(result["completed_in_this_call"], 2)
        self.assertEqual(result["failure_observation_mode"], "penalty")
        self.assertEqual(len(builder.orchestrators[0].cycle_requests), 3)
        store = ExperimentStore.open(output_directory)
        self.assertEqual(store.load_run(1).attempt_number, 2)
        self.assertEqual(store.load_run(1).ra_um, 4.25)
        self.assertEqual(store.load_run(2).attempt_number, 1)
        self.assertTrue(
            (
                output_directory
                / "logs/preflight_run_0001_attempt_02.json"
            ).is_file()
        )

    def test_automatic_batch_requires_one_persisted_failure_choice(
        self,
    ) -> None:
        config_path, _ = self.config_path("automatic_choice")
        run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=CapturingBuilder(),
        )

        with self.assertRaisesRegex(
            HardwareCliError,
            "--failure-result penalty",
        ):
            run_hardware_command(
                self.arguments(
                    config_path,
                    "--resume",
                    "--automatic-retry",
                    "--confirm-hardware",
                ),
                orchestrator_builder=CapturingBuilder(),
            )

    def test_preflight_rejects_unnecessary_confirmation(self) -> None:
        config_path, output_directory = self.config_path("bad_preflight")
        arguments = self.arguments(
            config_path,
            "--new",
            "--preflight-only",
            "--confirm-hardware",
        )

        with self.assertRaisesRegex(
            HardwareCliError,
            "Remove --confirm-hardware",
        ):
            run_hardware_command(
                arguments,
                orchestrator_builder=CapturingBuilder(),
            )

        self.assertFalse(output_directory.exists())

    def test_new_physical_run_must_start_with_preflight(self) -> None:
        config_path, output_directory = self.config_path("new_without_check")

        with self.assertRaisesRegex(
            HardwareCliError,
            "must first run with --new --preflight-only",
        ):
            run_hardware_command(
                self.arguments(
                    config_path,
                    "--new",
                    "--confirm-hardware",
                ),
                orchestrator_builder=CapturingBuilder(),
            )

        self.assertFalse(output_directory.exists())

    def test_first_run_requires_matching_preflight_receipt(self) -> None:
        config_path, output_directory = self.config_path("missing_receipt")
        config = load_optimizer_config(config_path)
        ExperimentStore.create(config)

        with self.assertRaisesRegex(
            HardwareCliError,
            "preflight receipt is missing",
        ):
            run_hardware_command(
                self.arguments(
                    config_path,
                    "--resume",
                    "--from-run",
                    "1",
                    "--confirm-hardware",
                ),
                orchestrator_builder=CapturingBuilder(),
            )

        store = ExperimentStore.open(output_directory)
        self.assertEqual(store.load_run(1).status, "proposed")

    def test_resume_refuses_skipping_the_safe_run(self) -> None:
        config_path, _ = self.config_path("skip_run")
        builder = CapturingBuilder()
        run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=builder,
        )

        with self.assertRaisesRegex(
            ExperimentStoreError,
            "safe resume point is run 1",
        ):
            run_hardware_command(
                self.arguments(
                    config_path,
                    "--resume",
                    "--from-run",
                    "2",
                    "--preflight-only",
                ),
                orchestrator_builder=builder,
            )

    def test_manual_intervention_resume_reuses_same_parameters(self) -> None:
        config_path, output_directory = self.config_path("manual_resume")
        builder = CapturingBuilder()
        run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=builder,
        )
        store = ExperimentStore.open(output_directory)
        original = store.load_run(1)
        store.mark_run_started(1)
        store.mark_manual_stop(
            1,
            error="simulated robot collision",
            failed_stage="robot_handling",
        )

        result = run_hardware_command(
            self.arguments(
                config_path,
                "--resume",
                "--from-run",
                "1",
                "--resume-after-manual-intervention",
                "--preflight-only",
            ),
            orchestrator_builder=builder,
        )

        resumed = ExperimentStore.open(output_directory).load_run(1)
        self.assertEqual(result["attempt_number"], 2)
        self.assertEqual(resumed.status, "proposed")
        self.assertEqual(resumed.parameters, original.parameters)
        self.assertEqual(resumed.soft_failure_count, 0)
        self.assertTrue(
            (
                output_directory
                / "logs/preflight_run_0001_attempt_02.json"
            ).is_file()
        )

    def test_interrupted_running_run_can_be_recovered_after_check(self) -> None:
        config_path, output_directory = self.config_path("interrupted")
        builder = CapturingBuilder()
        run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=builder,
        )
        store = ExperimentStore.open(output_directory)
        original = store.load_run(1)
        store.mark_run_started(1)

        result = run_hardware_command(
            self.arguments(
                config_path,
                "--resume",
                "--from-run",
                "1",
                "--resume-interrupted-run",
                "--preflight-only",
            ),
            orchestrator_builder=builder,
        )

        resumed = ExperimentStore.open(output_directory).load_run(1)
        self.assertEqual(result["attempt_number"], 2)
        self.assertEqual(resumed.status, "proposed")
        self.assertEqual(resumed.parameters, original.parameters)
        history = list((output_directory / "attempt_history").glob("*.json"))
        self.assertEqual(len(history), 1)

    def test_penalty_pause_acknowledgement_preflights_run_four(self) -> None:
        config_path, output_directory = self.config_path("penalty_pause")
        builder = CapturingBuilder()
        run_hardware_command(
            self.arguments(config_path, "--new", "--preflight-only"),
            orchestrator_builder=builder,
        )
        store = ExperimentStore.open(output_directory)
        parameters = dict(store.load_run(1).parameters)
        for run_number in range(1, 4):
            if run_number > 1:
                store.propose_run(parameters, strategy="bayesian")
            store.mark_run_started(run_number)
            store.mark_attempt_failed(
                run_number,
                error="simulated repeated failure",
                failed_stage="measurement_penalty",
                maximum_attempts=1,
                penalty_value=100.0,
                use_penalty_for_optimizer=True,
                maximum_consecutive_failed_parameter_sets=3,
            )

        self.assertEqual(store.state.status, "blocked")
        self.assertEqual(store.state.resume_run_number, 4)

        result = run_hardware_command(
            self.arguments(
                config_path,
                "--resume",
                "--from-run",
                "4",
                "--acknowledge-penalty-streak",
                "--preflight-only",
            ),
            orchestrator_builder=builder,
        )

        reopened = ExperimentStore.open(output_directory)
        self.assertEqual(result["run_number"], 4)
        self.assertEqual(reopened.load_run(4).status, "proposed")
        self.assertIsNone(reopened.state.pause_reason)


if __name__ == "__main__":
    unittest.main()

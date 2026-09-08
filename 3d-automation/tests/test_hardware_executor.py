from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from optimizer.config import load_optimizer_config
from optimizer.framework_runner import FrameworkRunner, FrameworkRunnerError
from optimizer.hardware_executor import OrchestratorRunExecutor
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
    def __init__(
        self,
        *,
        failure_stage: CycleStage | None = None,
        result_error: str | None = None,
        measurements: dict[str, float] | None = None,
    ) -> None:
        self.failure_stage = failure_stage
        self.result_error = result_error
        self.measurements = (
            {"Ra": 4.152, "Rz": 22.5}
            if measurements is None
            else measurements
        )
        self.preflight_requests = []
        self.cycle_requests = []

    def run_preflight(self, request, *, include_printer=True) -> None:
        self.preflight_requests.append(request)
        if self.failure_stage == CycleStage.PREFLIGHT:
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                "simulated preflight failure",
            )

    def run_single_print_cycle(self, request):
        self.cycle_requests.append(request)
        if self.failure_stage is not None:
            raise CycleExecutionError(
                self.failure_stage,
                "simulated cycle failure",
            )
        now = datetime.now(timezone.utc)
        return CycleResult(
            cycle_id="physical-cycle-1",
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
            measurements=self.measurements,
            printer_states=("PRINTING", "FINISHED"),
            error=self.result_error,
        )


class HardwareExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.stl_path = self.root / "part.stl"
        self.profile_path = self.root / "slicer_profile.ini"
        self.stl_path.write_text(
            "solid part\nendsolid part\n",
            encoding="utf-8",
        )
        self.profile_path.write_text(
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

    def config(self, label: str):
        output_directory = self.root / "runs" / label
        config_path = self.root / f"{label}.json"
        config_path.write_text(
            json.dumps(config_payload(output_directory)),
            encoding="utf-8",
        )
        return load_optimizer_config(config_path)

    def executor(self, config, orchestrator) -> OrchestratorRunExecutor:
        return OrchestratorRunExecutor(config, orchestrator)

    def test_maps_saved_parameters_paths_and_measurements(self) -> None:
        config = self.config("successful_mapping")
        orchestrator = FakeOrchestrator()
        runner = FrameworkRunner.create(
            config,
            self.executor(config, orchestrator),
        )

        completed = runner.run(max_runs=1)[0]

        self.assertEqual(completed.ra_um, 4.152)
        self.assertEqual(completed.rz_um, 22.5)
        self.assertEqual(completed.print_time_seconds, 615.25)
        self.assertEqual(completed.cycle_id, "physical-cycle-1")
        self.assertEqual(len(orchestrator.cycle_requests), 1)
        request = orchestrator.cycle_requests[0]
        self.assertEqual(
            request.profile_path.name,
            "run_0001_attempt_01_profile.ini",
        )
        self.assertEqual(
            request.gcode_path.name,
            "run_0001_attempt_01.gcode",
        )
        self.assertEqual(
            request.profile_path.parent,
            config.paths.output_directory / "generated_profiles",
        )
        self.assertEqual(
            request.gcode_path.parent,
            config.paths.output_directory / "gcode",
        )
        self.assertEqual(
            float(request.print_parameters["print_speed"]),
            completed.parameters["print_speed"],
        )
        profile_values = _profile_values(request.profile_path)
        self.assertEqual(
            float(profile_values["top_solid_infill_speed"]),
            completed.parameters["print_speed"],
        )
        self.assertEqual(
            float(profile_values["top_infill_extrusion_width"]),
            completed.parameters["extrusion_width"],
        )

    def test_preflight_builds_request_without_starting_cycle(self) -> None:
        config = self.config("preflight_only")
        orchestrator = FakeOrchestrator()
        executor = self.executor(config, orchestrator)
        runner = FrameworkRunner.create(config, executor)
        proposed = runner.prepare_next_run()
        assert proposed is not None

        request = executor.preflight(proposed)

        self.assertEqual(len(orchestrator.preflight_requests), 1)
        self.assertEqual(orchestrator.cycle_requests, [])
        self.assertTrue(request.profile_path.is_file())
        self.assertEqual(runner.store.load_run(1).status, "proposed")

    def test_pre_print_failures_are_explicitly_retryable(self) -> None:
        for stage in (CycleStage.PREFLIGHT, CycleStage.SLICING):
            with self.subTest(stage=stage):
                config = self.config(f"retryable_{stage.value}")
                orchestrator = FakeOrchestrator(failure_stage=stage)
                runner = FrameworkRunner.create(
                    config,
                    self.executor(config, orchestrator),
                )

                with self.assertRaisesRegex(
                    FrameworkRunnerError,
                    "before a physical attempt",
                ):
                    runner.run(max_runs=1)

                failed = runner.store.load_run(1)
                self.assertEqual(failed.status, "retryable_failed")
                self.assertEqual(failed.failed_stage, stage.value)
                self.assertEqual(failed.attempt_number, 1)
                self.assertEqual(failed.soft_failure_count, 0)
                self.assertIsNone(failed.started_at)
                self.assertIsNone(failed.objective_value)

    def test_failures_after_possible_print_start_are_blocked(self) -> None:
        for stage in (
            CycleStage.UPLOADING,
            CycleStage.CAMERA_CAPTURE,
            CycleStage.ROBOT_HANDLING,
            CycleStage.RECORDING,
        ):
            with self.subTest(stage=stage):
                config = self.config(f"blocked_{stage.value}")
                orchestrator = FakeOrchestrator(failure_stage=stage)
                runner = FrameworkRunner.create(
                    config,
                    self.executor(config, orchestrator),
                )

                with self.assertRaisesRegex(
                    FrameworkRunnerError,
                    "requires manual intervention",
                ):
                    runner.run(max_runs=1)

                failed = runner.store.load_run(1)
                self.assertEqual(failed.status, "terminal_failed")
                self.assertEqual(failed.failed_stage, stage.value)
                self.assertIsNone(failed.objective_value)

    def test_waiting_for_print_failure_uses_bounded_retry(self) -> None:
        config = self.config("waiting_retry")
        orchestrator = FakeOrchestrator(
            failure_stage=CycleStage.WAITING_FOR_PRINT
        )
        runner = FrameworkRunner.create(
            config,
            self.executor(config, orchestrator),
        )

        with self.assertRaisesRegex(FrameworkRunnerError, "attempt 1/2"):
            runner.run(max_runs=1)

        failed = runner.store.load_run(1)
        self.assertEqual(failed.status, "retryable_failed")
        self.assertEqual(failed.soft_failure_count, 1)
        self.assertEqual(failed.failed_stage, "waiting_for_print")

    def test_penalty_measurement_is_not_optimizer_training_data(self) -> None:
        config = self.config("penalty_result")
        orchestrator = FakeOrchestrator(
            result_error="QS measurement failed; penalty values were used.",
            measurements={"Ra": 100.0, "Rz": 100.0},
        )
        runner = FrameworkRunner.create(
            config,
            self.executor(config, orchestrator),
        )

        with self.assertRaisesRegex(
            FrameworkRunnerError,
            "attempt 1/2",
        ):
            runner.run(max_runs=1)

        failed = runner.store.load_run(1)
        self.assertEqual(failed.status, "retryable_failed")
        self.assertEqual(failed.failed_stage, "measurement_penalty")
        self.assertEqual(failed.soft_failure_count, 1)
        self.assertIsNone(failed.objective_value)
        self.assertIsNone(failed.ra_um)

    def test_invalid_measurement_is_blocked_without_objective(self) -> None:
        config = self.config("invalid_result")
        orchestrator = FakeOrchestrator(measurements={"Ra": float("nan")})
        runner = FrameworkRunner.create(
            config,
            self.executor(config, orchestrator),
        )

        with self.assertRaisesRegex(
            FrameworkRunnerError,
            "attempt 1/2",
        ):
            runner.run(max_runs=1)

        failed = runner.store.load_run(1)
        self.assertEqual(failed.status, "retryable_failed")
        self.assertEqual(failed.failed_stage, "result_validation")
        self.assertEqual(failed.soft_failure_count, 1)
        self.assertIsNone(failed.objective_value)

    def test_recovered_final_push_still_requires_manual_stop(self) -> None:
        config = self.config("handling_recovery")
        orchestrator = FakeOrchestrator(
            result_error=(
                "Final push was aborted by collision detection. Recovery "
                "completed and QS measurement was skipped."
            )
        )
        runner = FrameworkRunner.create(
            config,
            self.executor(config, orchestrator),
        )

        with self.assertRaisesRegex(
            FrameworkRunnerError,
            "requires manual intervention",
        ):
            runner.run(max_runs=1)

        failed = runner.store.load_run(1)
        self.assertEqual(failed.status, "terminal_failed")
        self.assertEqual(failed.failed_stage, "robot_handling")
        self.assertFalse(failed.is_penalty)
        self.assertIsNone(failed.objective_value)


def _profile_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line:
            continue
        name, value = raw_line.split("=", maxsplit=1)
        values[name.strip()] = value.strip()
    return values


if __name__ == "__main__":
    unittest.main()

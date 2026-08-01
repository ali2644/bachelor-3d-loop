from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from orchestrator import (
    CycleExecutionError,
    CycleRequest,
    CycleStage,
    CycleStatus,
    PrintOrchestrator,
)


class FakeSlicer:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def is_available(self) -> bool:
        self.calls.append("slicer.available")
        return True

    def send_stl_to_slicer(
        self,
        stl_path: Path,
        profile_path: Path,
        gcode_path: Path,
    ) -> bool:
        self.calls.append("slicer.slice")
        gcode_path.write_text("G28\n", encoding="utf-8")
        return True


class FakePrinter:
    def __init__(
        self,
        calls: list[str],
        states: list[str | None],
    ) -> None:
        self.calls = calls
        self.states = iter(states)

    def wait_until_connected(self) -> bool:
        self.calls.append("printer.connected")
        return True

    def upload_gcode(
        self,
        gcode_path: Path,
        *,
        start_after_upload: bool = False,
    ) -> bool:
        self.calls.append(
            f"printer.upload:start_after={start_after_upload}"
        )
        return gcode_path.is_file()

    def start_print_job(self) -> bool:
        self.calls.append("printer.start")
        return True

    def get_printer_state(self) -> str | None:
        state = next(self.states)
        self.calls.append(f"printer.state:{state}")
        return state


class FakeRobot:
    def __init__(
        self,
        calls: list[str],
        *,
        fail_during_prepare: bool = False,
    ) -> None:
        self.calls = calls
        self.fail_during_prepare = fail_during_prepare

    def __enter__(self) -> "FakeRobot":
        self.calls.append("robot.enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.calls.append("robot.exit")

    def initialize(self) -> None:
        self.calls.append("robot.initialize")

    def check_connection(self) -> None:
        self.calls.append("robot.check")

    def prepare_part_for_measurement(self) -> None:
        self.calls.append("robot.prepare")
        if self.fail_during_prepare:
            raise RuntimeError("simulated movement failure")

    def complete_part_handling_after_measurement(self) -> None:
        self.calls.append("robot.complete")


class FakeQualityStation:
    def __init__(
        self,
        calls: list[str],
        *,
        fail_during_measurement: bool = False,
    ) -> None:
        self.calls = calls
        self.fail_during_measurement = fail_during_measurement

    def health(self) -> bool:
        self.calls.append("qs.health")
        return True

    def measure(self) -> dict[str, float]:
        self.calls.append("qs.measure")
        if self.fail_during_measurement:
            raise RuntimeError("simulated measurement failure")
        return {"Ra": 4.152, "Rz": 22.5}


class FakeRecorder:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.results = []

    def record(self, result) -> None:
        self.calls.append(f"recorder:{result.status.value}")
        self.results.append(result)


class PrintOrchestratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        root = Path(self.temporary_directory.name)
        self.stl_path = root / "part.stl"
        self.profile_path = root / "profile.ini"
        self.gcode_path = root / "output.gcode"

        self.stl_path.write_text("solid part\nendsolid\n", encoding="utf-8")
        self.profile_path.write_text(
            "layer_height = 0.2\n",
            encoding="utf-8",
        )
        self.request = CycleRequest(
            stl_path=self.stl_path,
            profile_path=self.profile_path,
            gcode_path=self.gcode_path,
            print_parameters={"layer_height": "0.2"},
        )

    def create_orchestrator(
        self,
        calls: list[str],
        states: list[str | None],
        *,
        fail_robot: bool = False,
        fail_measurement: bool = False,
        max_status_errors: int = 5,
    ) -> tuple[PrintOrchestrator, FakeRecorder]:
        recorder = FakeRecorder(calls)
        orchestrator = PrintOrchestrator(
            FakeSlicer(calls),
            FakePrinter(calls, states),
            lambda: FakeRobot(
                calls,
                fail_during_prepare=fail_robot,
            ),
            FakeQualityStation(
                calls,
                fail_during_measurement=fail_measurement,
            ),
            recorder,
            print_poll_interval_seconds=0,
            print_start_timeout_seconds=5,
            print_timeout_seconds=5,
            max_consecutive_status_errors=max_status_errors,
            cooling_time_seconds=0,
        )
        return orchestrator, recorder

    def test_full_cycle_ignores_stale_finished_then_completes(self) -> None:
        calls: list[str] = []
        orchestrator, recorder = self.create_orchestrator(
            calls,
            ["IDLE", "FINISHED", "PRINTING", "FINISHED"],
        )

        result = orchestrator.run_single_print_cycle(self.request)

        self.assertEqual(result.status, CycleStatus.COMPLETED)
        self.assertEqual(result.measurements["Ra"], 4.152)
        self.assertEqual(
            result.printer_states,
            ("FINISHED", "PRINTING", "FINISHED"),
        )
        self.assertLess(
            calls.index("printer.state:FINISHED"),
            calls.index("printer.state:PRINTING"),
        )
        self.assertLess(
            calls.index("printer.state:PRINTING"),
            calls.index("robot.prepare"),
        )
        self.assertLess(
            calls.index("robot.prepare"),
            calls.index("qs.measure"),
        )
        self.assertLess(
            calls.index("qs.measure"),
            calls.index("robot.complete"),
        )
        self.assertEqual(recorder.results[-1].status, CycleStatus.COMPLETED)
        self.assertIn("printer.upload:start_after=True", calls)
        self.assertNotIn("printer.start", calls)

    def test_robot_failure_aborts_before_measurement(self) -> None:
        calls: list[str] = []
        orchestrator, recorder = self.create_orchestrator(
            calls,
            ["IDLE", "PRINTING", "FINISHED"],
            fail_robot=True,
        )

        with self.assertRaises(CycleExecutionError) as context:
            orchestrator.run_single_print_cycle(self.request)

        self.assertEqual(
            context.exception.stage,
            CycleStage.ROBOT_HANDLING,
        )
        self.assertNotIn("qs.measure", calls)
        self.assertNotIn("robot.complete", calls)
        self.assertIn("robot.exit", calls)
        self.assertEqual(recorder.results[-1].status, CycleStatus.FAILED)
        self.assertEqual(
            recorder.results[-1].stage,
            CycleStage.ROBOT_HANDLING,
        )

    def test_repeated_missing_printer_status_aborts_before_robot(self) -> None:
        calls: list[str] = []
        orchestrator, recorder = self.create_orchestrator(
            calls,
            ["IDLE", None, None],
            max_status_errors=2,
        )

        with self.assertRaises(CycleExecutionError) as context:
            orchestrator.run_single_print_cycle(self.request)

        self.assertEqual(
            context.exception.stage,
            CycleStage.WAITING_FOR_PRINT,
        )
        self.assertNotIn("robot.initialize", calls)
        self.assertNotIn("robot.prepare", calls)
        self.assertNotIn("qs.measure", calls)
        self.assertEqual(recorder.results[-1].status, CycleStatus.FAILED)

    def test_robot_qs_mode_does_not_call_printer_or_slicer(self) -> None:
        calls: list[str] = []
        orchestrator, _ = self.create_orchestrator(
            calls,
            [],
        )

        result = orchestrator.run_handling_and_measurement_cycle(
            self.request
        )

        self.assertEqual(result.status, CycleStatus.COMPLETED)
        self.assertNotIn("printer.connected", calls)
        self.assertNotIn("printer.upload:start_after=True", calls)
        self.assertNotIn("printer.start", calls)
        self.assertNotIn("slicer.slice", calls)
        self.assertIn("robot.check", calls)
        self.assertIn("robot.prepare", calls)
        self.assertIn("qs.measure", calls)
        self.assertIn("robot.complete", calls)
        self.assertLess(
            calls.index("robot.prepare"),
            calls.index("qs.measure"),
        )
        self.assertLess(
            calls.index("qs.measure"),
            calls.index("robot.complete"),
        )

    def test_measurement_failure_stops_robot_under_probe(self) -> None:
        calls: list[str] = []
        orchestrator, recorder = self.create_orchestrator(
            calls,
            [],
            fail_measurement=True,
        )

        with self.assertRaises(CycleExecutionError) as context:
            orchestrator.run_handling_and_measurement_cycle(self.request)

        self.assertEqual(context.exception.stage, CycleStage.MEASURING)
        self.assertIn("robot.prepare", calls)
        self.assertIn("qs.measure", calls)
        self.assertNotIn("robot.complete", calls)
        self.assertIn("robot.exit", calls)
        self.assertEqual(recorder.results[-1].status, CycleStatus.FAILED)
        self.assertEqual(
            recorder.results[-1].stage,
            CycleStage.MEASURING,
        )


if __name__ == "__main__":
    unittest.main()
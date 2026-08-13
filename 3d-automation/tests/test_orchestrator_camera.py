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
        states: list[str],
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
        return True

    def start_print_job(self) -> bool:
        self.calls.append("printer.start")
        return True

    def get_printer_state(self) -> str:
        state = next(self.states)
        self.calls.append(f"printer.state:{state}")
        return state


class FakeRobot:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def __enter__(self) -> "FakeRobot":
        self.calls.append("robot.enter")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.calls.append("robot.exit")

    def check_connection(self) -> None:
        self.calls.append("robot.check")

    def initialize(self) -> None:
        self.calls.append("robot.initialize")

    def prepare_part_for_measurement(self) -> None:
        self.calls.append("robot.prepare")

    def complete_part_handling_after_measurement(self) -> None:
        self.calls.append("robot.complete")


class FakeQualityStation:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def health(self) -> bool:
        self.calls.append("qs.health")
        return True

    def measure(self) -> dict[str, float]:
        self.calls.append("qs.measure")
        return {"Ra": 4.152, "Rz": 22.5}


class FakeCamera:
    def __init__(
        self,
        calls: list[str],
        *,
        fail_capture: bool = False,
    ) -> None:
        self.calls = calls
        self.fail_capture = fail_capture

    def health(self) -> bool:
        self.calls.append("camera.health")
        return True

    def capture_still(self, cycle_id: str) -> str:
        self.calls.append("camera.capture")
        if self.fail_capture:
            raise RuntimeError("simulated camera failure")
        return f"{cycle_id}.jpg"


class FakeRecorder:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.results = []

    def record(self, result) -> None:
        self.calls.append(f"recorder:{result.status.value}")
        self.results.append(result)


class CameraOrchestratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        root = Path(self.temporary_directory.name)
        self.stl_path = root / "part.stl"
        self.profile_path = root / "profile.ini"
        self.gcode_path = root / "output.gcode"

        self.stl_path.write_text(
            "solid part\nendsolid\n",
            encoding="utf-8",
        )
        self.profile_path.write_text(
            "layer_height = 0.2\n",
            encoding="utf-8",
        )

        self.request = CycleRequest(
            stl_path=self.stl_path,
            profile_path=self.profile_path,
            gcode_path=self.gcode_path,
        )

    def create_orchestrator(
        self,
        calls: list[str],
        states: list[str],
        *,
        fail_camera_capture: bool = False,
    ) -> tuple[PrintOrchestrator, FakeRecorder]:
        recorder = FakeRecorder(calls)

        orchestrator = PrintOrchestrator(
            FakeSlicer(calls),
            FakePrinter(calls, states),
            lambda: FakeRobot(calls),
            FakeQualityStation(calls),
            recorder,
            FakeCamera(
                calls,
                fail_capture=fail_camera_capture,
            ),
            print_poll_interval_seconds=0,
            print_start_timeout_seconds=5,
            print_timeout_seconds=5,
            cooling_time_seconds=0,
        )

        return orchestrator, recorder

    def test_camera_runs_after_finished_and_before_robot_handling(
        self,
    ) -> None:
        calls: list[str] = []
        orchestrator, _ = self.create_orchestrator(
            calls,
            ["IDLE", "PRINTING", "FINISHED"],
        )

        result = orchestrator.run_single_print_cycle(
            self.request
        )

        self.assertEqual(
            result.status,
            CycleStatus.COMPLETED,
        )
        self.assertIn("camera.health", calls)
        self.assertIn("camera.capture", calls)
        self.assertLess(
            calls.index("printer.state:FINISHED"),
            calls.index("camera.capture"),
        )
        self.assertLess(
            calls.index("camera.capture"),
            calls.index("robot.initialize"),
        )

    def test_camera_failure_aborts_before_robot_handling(
        self,
    ) -> None:
        calls: list[str] = []
        orchestrator, recorder = self.create_orchestrator(
            calls,
            ["IDLE", "PRINTING", "FINISHED"],
            fail_camera_capture=True,
        )

        with self.assertRaises(
            CycleExecutionError
        ) as context:
            orchestrator.run_single_print_cycle(
                self.request
            )

        self.assertEqual(
            context.exception.stage,
            CycleStage.CAMERA_CAPTURE,
        )
        self.assertNotIn("robot.initialize", calls)
        self.assertNotIn("robot.prepare", calls)
        self.assertEqual(
            recorder.results[-1].status,
            CycleStatus.FAILED,
        )
        self.assertEqual(
            recorder.results[-1].stage,
            CycleStage.CAMERA_CAPTURE,
        )

    def test_robot_qs_mode_does_not_use_camera(
        self,
    ) -> None:
        calls: list[str] = []
        orchestrator, _ = self.create_orchestrator(
            calls,
            [],
        )

        result = (
            orchestrator.run_handling_and_measurement_cycle(
                self.request
            )
        )

        self.assertEqual(
            result.status,
            CycleStatus.COMPLETED,
        )
        self.assertNotIn("camera.health", calls)
        self.assertNotIn("camera.capture", calls)


if __name__ == "__main__":
    unittest.main()

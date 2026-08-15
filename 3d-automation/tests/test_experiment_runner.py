from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.experiment_plan import ExperimentPlanEntry
from experiments.experiment_runner import ExperimentRunner
from orchestrator import CycleExecutionError, CycleStage
from printer.print_parameters import PrintParameters


def plan_entry(
    cycle_number: int,
    *,
    print_speed: float,
) -> ExperimentPlanEntry:
    return ExperimentPlanEntry(
        cycle_number=cycle_number,
        parameters=PrintParameters(
            top_solid_layers=2 + (cycle_number - 1) % 4,
            print_speed=print_speed,
            extrusion_width=0.40,
            extrusion_multiplier=1.00,
            temperature=210,
            fan_speed=80,
        ),
    )


class FakeProfileGenerator:
    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory
        self.calls: list[tuple[Path, PrintParameters, str | None]] = []

    def generate(
        self,
        base_profile_path: str | Path,
        parameters: PrintParameters,
        *,
        output_filename: str | None = None,
    ) -> Path:
        base_path = Path(base_profile_path)
        self.calls.append((base_path, parameters, output_filename))
        self.output_directory.mkdir(parents=True, exist_ok=True)
        output_path = self.output_directory / str(output_filename)
        output_path.write_text("generated profile\n", encoding="utf-8")
        return output_path


class FakeOrchestrator:
    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.fail_on_call = fail_on_call
        self.requests = []

    def run_single_print_cycle(self, request):
        self.requests.append(request)
        if len(self.requests) == self.fail_on_call:
            raise CycleExecutionError(
                CycleStage.SLICING,
                "simulated failure",
            )
        return request


class ExperimentRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.stl_path = self.root / "part.stl"
        self.base_profile_path = self.root / "slicer_profile.ini"
        self.stl_path.write_text(
            "solid part\nendsolid\n",
            encoding="utf-8",
        )
        self.base_profile_path.write_text(
            "base profile\n",
            encoding="utf-8",
        )

    def create_runner(
        self,
        *,
        fail_on_call: int | None = None,
    ) -> tuple[ExperimentRunner, FakeOrchestrator, FakeProfileGenerator]:
        orchestrator = FakeOrchestrator(fail_on_call=fail_on_call)
        profile_generator = FakeProfileGenerator(
            self.root / "generated_profiles"
        )
        runner = ExperimentRunner(
            orchestrator,
            profile_generator,
            self.root / "gcode",
        )
        return runner, orchestrator, profile_generator

    def test_prepares_and_runs_one_unique_request_per_plan_entry(self) -> None:
        runner, orchestrator, profile_generator = self.create_runner()
        plan = (
            plan_entry(2, print_speed=120),
            plan_entry(1, print_speed=75),
        )

        results = runner.run(
            plan,
            stl_path=self.stl_path,
            base_profile_path=self.base_profile_path,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(len(orchestrator.requests), 2)
        self.assertEqual(
            [request.gcode_path.name for request in orchestrator.requests],
            ["cycle_001.gcode", "cycle_002.gcode"],
        )
        self.assertEqual(
            [request.profile_path.name for request in orchestrator.requests],
            ["cycle_001_profile.ini", "cycle_002_profile.ini"],
        )
        self.assertEqual(
            [
                request.print_parameters["print_speed"]
                for request in orchestrator.requests
            ],
            ["75", "120"],
        )
        self.assertEqual(
            [call[2] for call in profile_generator.calls],
            ["cycle_001_profile.ini", "cycle_002_profile.ini"],
        )

    def test_stops_before_next_entry_when_a_cycle_fails(self) -> None:
        runner, orchestrator, profile_generator = self.create_runner(
            fail_on_call=2
        )
        plan = tuple(
            plan_entry(cycle_number, print_speed=50 + cycle_number)
            for cycle_number in range(1, 4)
        )

        with self.assertRaises(CycleExecutionError) as context:
            runner.run(
                plan,
                stl_path=self.stl_path,
                base_profile_path=self.base_profile_path,
            )

        self.assertEqual(context.exception.stage, CycleStage.SLICING)
        self.assertEqual(len(orchestrator.requests), 2)
        self.assertEqual(len(profile_generator.calls), 2)
        self.assertEqual(
            orchestrator.requests[-1].gcode_path.name,
            "cycle_002.gcode",
        )

    def test_rejects_missing_input_before_generating_or_running(self) -> None:
        runner, orchestrator, profile_generator = self.create_runner()

        with self.assertRaisesRegex(ValueError, "STL file not found"):
            runner.run(
                (plan_entry(1, print_speed=75),),
                stl_path=self.root / "missing.stl",
                base_profile_path=self.base_profile_path,
            )

        self.assertEqual(profile_generator.calls, [])
        self.assertEqual(orchestrator.requests, [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import main as main_module


class FakeResult:
    def __init__(self, cycle_id: str) -> None:
        self.cycle_id = cycle_id

    def as_dict(self) -> dict[str, str]:
        return {"cycle_id": self.cycle_id}


class MainTest(unittest.TestCase):
    def test_experiment_mode_defaults_to_first_two_plan_entries(self) -> None:
        arguments = main_module.parse_arguments(["--mode", "experiment"])

        self.assertEqual(arguments.mode, "experiment")
        self.assertEqual(arguments.experiment_start_cycle, 1)
        self.assertEqual(arguments.experiment_cycles, 2)
        self.assertEqual(
            arguments.experiment_plan,
            main_module.EXPERIMENT_PLAN_PATH,
        )
        self.assertEqual(
            arguments.experiment_plan.name,
            "experiment_plan_100.csv",
        )

    def test_rejects_experiment_cycle_count_outside_one_to_hundred(
        self,
    ) -> None:
        for invalid_value in ("0", "101", "not-a-number"):
            with self.subTest(invalid_value=invalid_value):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main_module.parse_arguments(
                            [
                                "--mode",
                                "experiment",
                                "--experiment-cycles",
                                invalid_value,
                            ]
                        )

    def test_rejects_experiment_start_cycle_outside_one_to_hundred(
        self,
    ) -> None:
        for invalid_value in ("0", "101", "not-a-number"):
            with self.subTest(invalid_value=invalid_value):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        main_module.parse_arguments(
                            [
                                "--mode",
                                "experiment",
                                "--experiment-start-cycle",
                                invalid_value,
                            ]
                        )

    @patch("main.ExperimentRunner")
    @patch("main.SlicerProfileGenerator")
    @patch("main.build_orchestrator")
    @patch("main.load_experiment_plan")
    @patch("main.generate_experiment_plan")
    def test_run_experiment_passes_only_requested_plan_entries(
        self,
        generate_experiment_plan: Mock,
        load_experiment_plan: Mock,
        build_orchestrator: Mock,
        profile_generator_class: Mock,
        runner_class: Mock,
    ) -> None:
        entries = tuple(object() for _ in range(100))
        load_experiment_plan.return_value = entries

        expected_results = (
            FakeResult("cycle-1"),
            FakeResult("cycle-2"),
        )
        runner_class.return_value.run.return_value = expected_results

        arguments = main_module.parse_arguments(
            [
                "--mode",
                "experiment",
                "--experiment-cycles",
                "2",
            ]
        )

        generate_experiment_plan.return_value = Mock(
            path=arguments.experiment_plan.resolve(),
            archive_path=arguments.experiment_plan.resolve(),
            seed=12345,
        )

        results = main_module.run_experiment(arguments)

        self.assertEqual(results, expected_results)

        generate_experiment_plan.assert_called_once_with(
            arguments.experiment_plan.resolve(),
            sample_count=main_module.MAX_EXPERIMENT_CYCLES,
            seed=None,
        )
        load_experiment_plan.assert_called_once_with(
            arguments.experiment_plan.resolve(),
            expected_cycle_count=main_module.MAX_EXPERIMENT_CYCLES,
        )
        build_orchestrator.assert_called_once_with(
            arguments.results_csv.resolve()
        )
        runner_class.return_value.run.assert_called_once_with(
            entries[:2],
            stl_path=arguments.stl.resolve(),
            base_profile_path=arguments.profile.resolve(),
        )

    @patch("main.ExperimentRunner")
    @patch("main.SlicerProfileGenerator")
    @patch("main.build_orchestrator")
    @patch("main.load_experiment_plan")
    @patch("main.generate_experiment_plan")
    def test_run_experiment_can_resume_from_requested_cycle(
        self,
        generate_experiment_plan: Mock,
        load_experiment_plan: Mock,
        build_orchestrator: Mock,
        profile_generator_class: Mock,
        runner_class: Mock,
    ) -> None:
        entries = tuple(object() for _ in range(100))
        load_experiment_plan.return_value = entries
        runner_class.return_value.run.return_value = ()

        with tempfile.TemporaryDirectory() as temporary_directory:
            experiment_plan = (
                Path(temporary_directory) / "experiment_plan_100.csv"
            )
            experiment_plan.touch()

            arguments = main_module.parse_arguments(
                [
                    "--mode",
                    "experiment",
                    "--experiment-plan",
                    str(experiment_plan),
                    "--experiment-start-cycle",
                    "49",
                    "--experiment-cycles",
                    "100",
                    "--reuse-experiment-plan",
                ]
            )

            results = main_module.run_experiment(arguments)

        self.assertEqual(results, ())
        generate_experiment_plan.assert_not_called()

        load_experiment_plan.assert_called_once_with(
            experiment_plan.resolve(),
            expected_cycle_count=main_module.MAX_EXPERIMENT_CYCLES,
        )
        build_orchestrator.assert_called_once_with(
            arguments.results_csv.resolve()
        )
        runner_class.return_value.run.assert_called_once_with(
            entries[48:100],
            stl_path=arguments.stl.resolve(),
            base_profile_path=arguments.profile.resolve(),
        )

    def test_experiment_rejects_start_cycle_after_end_cycle(self) -> None:
        arguments = main_module.parse_arguments(
            [
                "--mode",
                "experiment",
                "--experiment-start-cycle",
                "10",
                "--experiment-cycles",
                "9",
                "--reuse-experiment-plan",
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "must not be greater",
        ):
            main_module.run_experiment(arguments)

    @patch("main.build_orchestrator")
    @patch("main.load_experiment_plan")
    def test_experiment_rejects_single_cycle_parameter_overrides(
        self,
        load_experiment_plan: Mock,
        build_orchestrator: Mock,
    ) -> None:
        arguments = main_module.parse_arguments(
            [
                "--mode",
                "experiment",
                "--temperature",
                "210",
            ]
        )

        with self.assertRaisesRegex(
            ValueError,
            "parameters come from the CSV plan",
        ):
            main_module.run_experiment(arguments)

        load_experiment_plan.assert_not_called()
        build_orchestrator.assert_not_called()

    @patch("main.build_orchestrator")
    @patch("main.build_single_cycle_request")
    def test_full_mode_still_runs_one_single_cycle(
        self,
        build_single_cycle_request: Mock,
        build_orchestrator: Mock,
    ) -> None:
        request = object()
        result = FakeResult("single-cycle")
        orchestrator = build_orchestrator.return_value
        orchestrator.run_single_print_cycle.return_value = result
        build_single_cycle_request.return_value = request

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main_module.main(["--mode", "full"])

        self.assertEqual(exit_code, 0)
        orchestrator.run_single_print_cycle.assert_called_once_with(request)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"cycle_id": "single-cycle"},
        )

    @patch("main.build_single_cycle_request")
    @patch("main.run_experiment")
    def test_experiment_mode_does_not_build_single_cycle_request(
        self,
        run_experiment: Mock,
        build_single_cycle_request: Mock,
    ) -> None:
        run_experiment.return_value = (
            FakeResult("cycle-1"),
            FakeResult("cycle-2"),
        )

        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main_module.main(
                [
                    "--mode",
                    "experiment",
                    "--experiment-cycles",
                    "2",
                ]
            )

        self.assertEqual(exit_code, 0)
        build_single_cycle_request.assert_not_called()
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "mode": "experiment",
                "completed_cycles": 2,
                "results": [
                    {"cycle_id": "cycle-1"},
                    {"cycle_id": "cycle-2"},
                ],
            },
        )


if __name__ == "__main__":
    unittest.main()
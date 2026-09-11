from __future__ import annotations

import argparse
import json
import logging
import os
from push import send_push_notification
from functools import partial
from pathlib import Path
from typing import Sequence

from experiments.experiment_plan import (
    generate_experiment_plan,
    load_experiment_plan,
)
from experiments.experiment_runner import ExperimentRunner
from orchestrator import (
    CycleExecutionError,
    CycleRequest,
    CycleResult,
    PrintOrchestrator,
)
from printer.print_parameters import (
    PrintParameters,
    SlicerProfileGenerator,
)


LOGGER = logging.getLogger(__name__)
PROJECT_DIR = Path(__file__).resolve().parents[1]
EXPERIMENT_PLAN_PATH = (
    PROJECT_DIR
    / "config/experiment_plans/experiment_plan_100.csv"
)
MAX_EXPERIMENT_CYCLES = 100

########################################################################
class NtfyHandler(logging.Handler):
    def emit(self, record):
        try:
            # Drop everything below WARNING
            if record.levelno < logging.WARNING:
                return
            
            # If it's a WARNING, only proceed if it mentions a penalty value
            if record.levelno == logging.WARNING and "completed with measurement penalty" not in record.getMessage().lower():
                return

            send_push_notification(
                title=f"{record.levelname} | {record.name}",
                message=self.format(record),
                priority=5 if record.levelno >= logging.ERROR else 4,
            )

        except Exception:
            # never let notification failures break the application
            pass

########################################################################
def experiment_cycle_count(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "experiment cycles must be an integer."
        ) from error

    if not 1 <= value <= MAX_EXPERIMENT_CYCLES:
        raise argparse.ArgumentTypeError(
            "experiment cycles must be between "
            f"1 and {MAX_EXPERIMENT_CYCLES}."
        )
    return value


def parse_arguments(
    arguments: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one bounded 3D-print automation cycle or a "
            "reproducible experiment plan."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("preflight", "robot-qs", "full", "experiment"),
        default="preflight",
        help=(
            "preflight performs no robot movement; robot-qs uses an "
            "existing printed part; full also slices and prints; "
            "experiment runs entries from a CSV plan."
        ),
    )
    parser.add_argument(
        "--stl",
        type=Path,
        default=(
            PROJECT_DIR
            / "data/models/15x15_V2_rounded.stl"
        ),
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=PROJECT_DIR / "config/slicer_profile.ini",
        help=(
            "Full, working PrusaSlicer profile used as the unchanged base."
        ),
    )
    parser.add_argument(
        "--generated-profiles-dir",
        type=Path,
        default=PROJECT_DIR / "data/generated_profiles",
        help="Directory for the generated profile of each cycle.",
    )
    parser.add_argument(
        "--gcode",
        type=Path,
        default=PROJECT_DIR / "data/gcode/output.gcode",
        help=(
            "G-code output for a single cycle. In experiment mode, "
            "cycle_NNN.gcode files are written to its parent directory."
        ),
    )
    parser.add_argument(
        "--results-csv",
        type=Path,
        default=(
            PROJECT_DIR
            / "data/results/parameter_optimization_cycles.csv"
        ),
    )
    parser.add_argument(
        "--experiment-plan",
        type=Path,
        default=EXPERIMENT_PLAN_PATH,
        help="CSV file containing the 100 validated parameter sets.",
    )
    parser.add_argument(
        "--experiment-cycles",
        type=experiment_cycle_count,
        default=2,
        help=(
            "Last plan entry to run (1-100). Defaults to 2 for "
            "the first consecutive-cycle hardware test."
        ),
    )
    parser.add_argument(
        "--experiment-start-cycle",
        type=experiment_cycle_count,
        default=1,
        help=(
            "First plan entry to run (1-100). Defaults to 1. "
            "Use this together with --reuse-experiment-plan when "
            "continuing an interrupted experiment."
        ),
    )
    parser.add_argument(
        "--reuse-experiment-plan",
        action="store_true",
        help=(
            "Reuse the existing 100-entry experiment CSV instead of "
            "generating a new plan. Use this when an interrupted "
            "hardware run must keep the same parameter plan."
        ),
    )
    parser.add_argument(
        "--experiment-plan-seed",
        type=int,
        help=(
            "Optional seed for reproducible automatic experiment-plan "
            "generation."
        ),
    )
    parser.add_argument(
        "--top-solid-layers",
        type=int,
        help="Top solid layers are currently fixed at 5.",
    )
    parser.add_argument(
        "--print-speed",
        type=float,
        help=(
            "Top solid infill speed in mm/s (50-90). "
            "Defaults to the base profile."
        ),
    )
    parser.add_argument(
        "--extrusion-width",
        type=float,
        help=(
            "Top infill extrusion width in mm (0.38-0.50). "
            "Defaults to the base profile."
        ),
    )
    parser.add_argument(
        "--extrusion-multiplier",
        type=float,
        help=(
            "Extrusion multiplier (1.05-1.20). "
            "Defaults to the base profile."
        ),
    )
    parser.add_argument(
        "--temperature",
        type=int,
        help=(
            "PLA print temperature in degrees Celsius (215-235). "
            "Defaults to the base profile."
        ),
    )
    parser.add_argument(
        "--fan-speed",
        type=int,
        help=(
            "Fixed part-cooling fan speed in percent (30-80). "
            "Defaults to max_fan_speed from the base profile."
        ),
    )
    return parser.parse_args(arguments)


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set."
        )
    return value


def build_orchestrator(
    results_csv: Path,
) -> PrintOrchestrator:
    from printer.prusalink_service import PrusaLinkService
    from printer.slicer_service import SlicerService
    from qs.qs_api_client import QualityStationClient
    from camera.camera_client import CameraClient
    from results.csv_cycle_recorder import CsvCycleRecorder
    from robot.robot_service import RobotService

    printer_ip = os.getenv("PRINTER_IP", "10.8.170.57")
    robot_ip = os.getenv("ROBOT_IP", "10.8.170.41")
    api_key = required_environment("PRUSALINK_API_KEY")
    qs_base_url = required_environment("QS_BASE_URL")
    camera_base_url = os.getenv("CAMERA_BASE_URL", qs_base_url) #qs url ist default weil beide auf dem gleichen raspberry laufen

    slicer_path = Path(
        os.getenv(
            "PRUSASLICER_PATH",
            str(
                Path.home()
                / "apps/prusaslicer/"
                "PrusaSlicer-2.9.1-x86_64.AppImage"
            ),
        )
    )

    printer_service = PrusaLinkService(
        printer_ip,
        api_key,
        remote_gcode_path=os.getenv(
            "REMOTE_GCODE_PATH",
            "FOLDER/demo.gcode",
        ),
    )
    slicer_service = SlicerService(slicer_path)
    quality_station = QualityStationClient(qs_base_url)
    camera_service = CameraClient(
        camera_base_url,
        download_directory=Path(
            os.getenv(
                "CAMERA_DOWNLOAD_DIR",
                str(
                    PROJECT_DIR
                    / "data/camera_images"
                ),
            )
        ),
    )
    cycle_recorder = CsvCycleRecorder(results_csv)

    return PrintOrchestrator(
        slicer_service,
        printer_service,
        partial(RobotService, robot_ip),
        quality_station,
        cycle_recorder,
        camera_service,
        print_poll_interval_seconds=float(
            os.getenv("PRINT_POLL_SECONDS", "15")
        ),
        print_start_timeout_seconds=float(
            os.getenv("PRINT_START_TIMEOUT_SECONDS", "180")
        ),
        print_timeout_seconds=float(
            os.getenv("PRINT_TIMEOUT_SECONDS", str(8 * 60 * 60))
        ),
        max_consecutive_status_errors=int(
            os.getenv("MAX_STATUS_ERRORS", "5")
        ),
        cooling_time_seconds=float(
            os.getenv("PART_COOLING_SECONDS", "0")#60
        ),
    )



def build_single_cycle_request(
    arguments: argparse.Namespace,
) -> CycleRequest:
    base_profile_path = arguments.profile.resolve()
    print_parameters = PrintParameters.from_profile(
        base_profile_path,
        top_solid_layers=arguments.top_solid_layers,
        print_speed=arguments.print_speed,
        extrusion_width=arguments.extrusion_width,
        extrusion_multiplier=arguments.extrusion_multiplier,
        temperature=arguments.temperature,
        fan_speed=arguments.fan_speed,
    )
    generated_profile_path = SlicerProfileGenerator(
        arguments.generated_profiles_dir.resolve()
    ).generate(
        base_profile_path,
        print_parameters,
    )
    LOGGER.info(
        "Generated cycle profile %s with parameters %s.",
        generated_profile_path,
        print_parameters.as_record(),
    )

    return CycleRequest(
        stl_path=arguments.stl.resolve(),
        profile_path=generated_profile_path,
        gcode_path=arguments.gcode.resolve(),
        print_parameters=print_parameters.as_record(),
    )


def run_experiment(
    arguments: argparse.Namespace,
) -> tuple[CycleResult, ...]:
    parameter_overrides = {
        "--top-solid-layers": arguments.top_solid_layers,
        "--print-speed": arguments.print_speed,
        "--extrusion-width": arguments.extrusion_width,
        "--extrusion-multiplier": arguments.extrusion_multiplier,
        "--temperature": arguments.temperature,
        "--fan-speed": arguments.fan_speed,
    }
    supplied_overrides = [
        name
        for name, value in parameter_overrides.items()
        if value is not None
    ]
    if supplied_overrides:
        raise ValueError(
            "Experiment parameters come from the CSV plan; remove CLI "
            f"overrides: {', '.join(supplied_overrides)}."
        )

    start_cycle = arguments.experiment_start_cycle
    end_cycle = arguments.experiment_cycles

    if start_cycle > end_cycle:
        raise ValueError(
            "--experiment-start-cycle must not be greater than "
            "--experiment-cycles."
        )

    experiment_plan_path = arguments.experiment_plan.resolve()
    if arguments.reuse_experiment_plan:
        if arguments.experiment_plan_seed is not None:
            raise ValueError(
                "--experiment-plan-seed cannot be combined with "
                "--reuse-experiment-plan."
            )
        if not experiment_plan_path.is_file():
            raise ValueError(
                "Cannot reuse missing experiment plan: "
                f"{experiment_plan_path}"
            )
        LOGGER.info(
            "Reusing existing experiment plan %s.",
            experiment_plan_path,
        )
    else:
        generated_plan = generate_experiment_plan(
            experiment_plan_path,
            sample_count=MAX_EXPERIMENT_CYCLES,
            seed=arguments.experiment_plan_seed,
        )
        LOGGER.info(
            "Generated new experiment plan %s with seed %s; archived "
            "copy: %s.",
            generated_plan.path,
            generated_plan.seed,
            generated_plan.archive_path,
        )

    complete_plan = load_experiment_plan(
        experiment_plan_path,
        expected_cycle_count=MAX_EXPERIMENT_CYCLES,
    )

    selected_plan = complete_plan[start_cycle - 1:end_cycle]

    LOGGER.info(
        "Loaded %s valid plan entries; running entries %s through %s "
        "(%s cycles).",
        len(complete_plan),
        start_cycle,
        end_cycle,
        len(selected_plan),
    )

    orchestrator = build_orchestrator(arguments.results_csv.resolve())
    runner = ExperimentRunner(
        orchestrator,
        SlicerProfileGenerator(
            arguments.generated_profiles_dir.resolve()
        ),
        arguments.gcode.resolve().parent,
    )
    return runner.run(
        selected_plan,
        stl_path=arguments.stl.resolve(),
        base_profile_path=arguments.profile.resolve(),
    )


def main(arguments: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    #######################################################################
    ntfy_handler = NtfyHandler()
    ntfy_handler.setLevel(logging.WARNING)

    ntfy_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
    )
    #######################################################################
    logging.getLogger().addHandler(ntfy_handler)

    parsed_arguments = parse_arguments(arguments)

    try:
        if parsed_arguments.mode == "experiment":
            results = run_experiment(parsed_arguments)
            print(
                json.dumps(
                    {
                        "mode": "experiment",
                        "completed_cycles": len(results),
                        "results": [
                            result.as_dict()
                            for result in results
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0

        request = build_single_cycle_request(parsed_arguments)
        orchestrator = build_orchestrator(
            parsed_arguments.results_csv.resolve()
        )

        if parsed_arguments.mode == "preflight":
            orchestrator.run_preflight(request)
            LOGGER.info(
                "Preflight passed. No robot movement was performed."
            )
            return 0

        if parsed_arguments.mode == "robot-qs":
            result = orchestrator.run_handling_and_measurement_cycle(
                request
            )
        else:
            result = orchestrator.run_single_print_cycle(request)

    except (CycleExecutionError, RuntimeError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1

    print(
        json.dumps(
            result.as_dict(),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
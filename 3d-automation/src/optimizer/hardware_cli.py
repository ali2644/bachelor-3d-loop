from __future__ import annotations

import argparse
import json
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Protocol, Sequence

from optimizer.config import load_optimizer_config
from optimizer.experiment_store import ExperimentStore, RunRecord
from optimizer.framework_runner import (
    FailurePolicy,
    FrameworkRunner,
    RunExecutorError,
)
from optimizer.hardware_executor import OrchestratorRunExecutor
from orchestrator import CycleRequest


LOGGER = logging.getLogger(__name__)
INITIAL_PREFLIGHT_FILENAME = "initial_hardware_preflight.json"


class HardwareCliError(RuntimeError):
    """Raised when a hardware CLI request is unsafe or inconsistent."""


class OrchestratorBuilder(Protocol):
    def __call__(self, results_csv: Path): ...


def positive_integer(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "value must be an integer."
        ) from error
    if value < 1:
        raise argparse.ArgumentTypeError("value must be at least 1.")
    return value


def parse_arguments(
    arguments: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run or preflight the resumable optimizer framework against "
            "the existing physical PrintOrchestrator."
        )
    )
    parser.add_argument("config", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--new",
        action="store_true",
        help="Create a new experiment without overwriting an existing one.",
    )
    mode.add_argument(
        "--resume",
        action="store_true",
        help="Open the exact configured experiment directory.",
    )
    parser.add_argument("--from-run", type=positive_integer)
    parser.add_argument(
        "--max-runs",
        type=positive_integer,
        default=1,
        help=(
            "Maximum completed parameter sets in this process (default: 1). "
            "An automatic retry may add one physical cycle."
        ),
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry one saved retryable failure with identical parameters.",
    )
    parser.add_argument(
        "--automatic-retry",
        action="store_true",
        help=(
            "Automatically repeat a safely retryable physical failure once "
            "and continue the batch."
        ),
    )
    parser.add_argument(
        "--failure-result",
        choices=("penalty", "ignore"),
        help=(
            "Persist the experiment-wide decision after two failed "
            "attempts: use objective penalty 100 or exclude the set from "
            "optimizer observations."
        ),
    )
    parser.add_argument(
        "--resume-after-manual-intervention",
        action="store_true",
        help=(
            "After inspecting and correcting the plant, prepare the same "
            "terminally stopped run again. Requires --preflight-only."
        ),
    )
    parser.add_argument(
        "--resume-interrupted-run",
        action="store_true",
        help=(
            "After confirming that no old process is still controlling the "
            "plant, archive a run left in 'running' state and prepare the "
            "same parameters again. Requires --from-run and --preflight-only."
        ),
    )
    parser.add_argument(
        "--acknowledge-failure-streak",
        "--acknowledge-penalty-streak",
        dest="acknowledge_penalty_streak",
        action="store_true",
        help=(
            "Acknowledge the safety pause after three consecutive failed "
            "parameter sets and preflight the saved resume run."
        ),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help=(
            "Persist the next proposal and check services without starting "
            "a print or moving the robot."
        ),
    )
    parser.add_argument(
        "--confirm-hardware",
        action="store_true",
        help=(
            "Required acknowledgement for a physical print-measure run. "
            "It has no effect in preflight-only mode."
        ),
    )
    return parser.parse_args(arguments)


def run_hardware_command(
    arguments: argparse.Namespace,
    *,
    orchestrator_builder: OrchestratorBuilder | None = None,
) -> dict[str, object]:
    _validate_request(arguments)
    config = load_optimizer_config(arguments.config)
    if config.paths.history_csvs:
        raise HardwareCliError(
            "history_csvs import is not implemented yet; remove those "
            "paths before creating a hardware experiment."
        )

    builder = (
        _load_project_orchestrator_builder()
        if orchestrator_builder is None
        else orchestrator_builder
    )
    images_directory = config.paths.output_directory / "images"
    cycle_results_csv = (
        config.paths.output_directory / "hardware_cycles.csv"
    )
    with _camera_download_directory(images_directory):
        orchestrator = builder(cycle_results_csv)
    executor = OrchestratorRunExecutor(config, orchestrator)

    if arguments.new:
        store = ExperimentStore.create(config)
    else:
        store = ExperimentStore.open(
            config.paths.output_directory,
            expected_config=config,
        )
        if arguments.acknowledge_penalty_streak:
            assert arguments.from_run is not None
            store.acknowledge_penalty_pause(arguments.from_run)
        if arguments.resume_interrupted_run:
            assert arguments.from_run is not None
            interrupted = store.load_resume_run(arguments.from_run)
            if interrupted is None or interrupted.status != "running":
                raise HardwareCliError(
                    "The selected run is not saved with status 'running'."
                )
            store.mark_manual_stop(
                interrupted.run_number,
                error=(
                    "Operator confirmed that the previous program process "
                    "was interrupted and the plant was inspected manually."
                ),
                failed_stage="process_interrupted",
                cycle_id=interrupted.cycle_id,
            )
            store.prepare_manual_resume(interrupted.run_number)
        elif arguments.resume_after_manual_intervention:
            assert arguments.from_run is not None
            stopped = store.load_resume_run(arguments.from_run)
            if stopped is None:
                raise HardwareCliError(
                    "There is no stopped run to resume manually."
                )
            store.prepare_manual_resume(stopped.run_number)
        elif arguments.from_run is not None:
            next_run = store.next_run_number()
            if next_run is None:
                raise HardwareCliError(
                    "The experiment is complete; there is no run to resume."
                )
            store.load_resume_run(arguments.from_run)

    if arguments.failure_result is not None:
        failure_mode = store.configure_failure_observation_mode(
            arguments.failure_result
        )
    else:
        failure_mode = store.state.failure_observation_mode
    if arguments.automatic_retry and failure_mode is None:
        raise HardwareCliError(
            "Choose the experiment-wide failure result once with "
            "--failure-result penalty or --failure-result ignore."
        )
    effective_failure_mode = failure_mode or "penalty"

    with _experiment_file_logging(store.directory):
        images_directory.mkdir(exist_ok=True)
        runner = FrameworkRunner(
            config,
            store,
            executor,
            failure_policy=FailurePolicy(
                use_penalty_for_optimizer=(
                    effective_failure_mode == "penalty"
                )
            ),
        )
        if arguments.preflight_only:
            proposed = runner.prepare_next_run(
                retry_failed=arguments.retry_failed
            )
            if proposed is None:
                return _completed_summary(runner)
            try:
                request = executor.preflight(proposed)
            except RunExecutorError as error:
                store.mark_preflight_failed(
                    proposed.run_number,
                    error=str(error),
                    failed_stage=error.failed_stage,
                )
                raise
            receipt_path = _save_preflight_receipt(
                store,
                proposed,
                request,
            )
            return {
                "mode": "optimizer_hardware_preflight",
                "experiment_directory": str(store.directory),
                "run_number": proposed.run_number,
                "attempt_number": proposed.attempt_number,
                "run_status": proposed.status,
                "parameters": dict(proposed.parameters),
                "profile_path": str(request.profile_path),
                "gcode_path": str(request.gcode_path),
                "preflight_receipt": str(receipt_path),
                "hardware_started": False,
            }

        if arguments.automatic_retry:
            completed = runner.run(
                max_runs=arguments.max_runs,
                automatic_retry=True,
                before_execute=lambda run: _ensure_preflight_receipt(
                    store,
                    executor,
                    run,
                ),
            )
        else:
            proposed = runner.prepare_next_run(
                retry_failed=arguments.retry_failed
            )
            if proposed is None:
                return _completed_summary(runner)
            _require_preflight_receipt(store, proposed)
            completed = runner.run(
                max_runs=arguments.max_runs,
                retry_failed=arguments.retry_failed,
            )
        return {
            "mode": "optimizer_hardware",
            "experiment_directory": str(store.directory),
            "completed_in_this_call": len(completed),
            "completed_total": store.state.completed_runs,
            "last_completed_result": (
                None
                if not completed
                else {
                    "run_number": completed[-1].run_number,
                    "attempt_number": completed[-1].attempt_number,
                    "objective_value": completed[-1].objective_value,
                    "Ra_um": completed[-1].ra_um,
                    "Rz_um": completed[-1].rz_um,
                    "print_time_seconds": (
                        completed[-1].print_time_seconds
                    ),
                    "is_penalty": completed[-1].is_penalty,
                    "is_ignored": completed[-1].is_ignored,
                }
            ),
            "next_run_number": store.next_run_number(),
            "status": store.state.status,
            "consecutive_penalty_runs": (
                store.state.consecutive_penalty_runs
            ),
            "consecutive_ignored_runs": (
                store.state.consecutive_ignored_runs
            ),
            "consecutive_failed_parameter_sets": (
                store.state.consecutive_failed_parameter_sets
            ),
            "failure_observation_mode": (
                store.state.failure_observation_mode
            ),
            "pause_reason": store.state.pause_reason,
            "resume_run_number": store.state.resume_run_number,
            "results_csv": str(store.directory / "results.csv"),
            "hardware_cycles_csv": str(cycle_results_csv),
            "images_directory": str(images_directory),
        }


def _validate_request(arguments: argparse.Namespace) -> None:
    if arguments.from_run is not None and not arguments.resume:
        raise HardwareCliError(
            "--from-run can only be used together with --resume."
        )
    if arguments.retry_failed and not arguments.resume:
        raise HardwareCliError(
            "--retry-failed can only be used together with --resume."
        )
    if arguments.automatic_retry and not arguments.resume:
        raise HardwareCliError(
            "--automatic-retry can only be used together with --resume."
        )
    if arguments.automatic_retry and arguments.retry_failed:
        raise HardwareCliError(
            "--automatic-retry already handles the saved retry; remove "
            "--retry-failed."
        )
    if arguments.automatic_retry and arguments.preflight_only:
        raise HardwareCliError(
            "--automatic-retry starts physical cycles and cannot be used "
            "with --preflight-only."
        )
    if arguments.resume_after_manual_intervention and not arguments.resume:
        raise HardwareCliError(
            "--resume-after-manual-intervention requires --resume."
        )
    if arguments.resume_interrupted_run and not arguments.resume:
        raise HardwareCliError(
            "--resume-interrupted-run requires --resume."
        )
    if arguments.acknowledge_penalty_streak and not arguments.resume:
        raise HardwareCliError(
            "--acknowledge-penalty-streak requires --resume."
        )
    resolution_flags = sum(
        bool(value)
        for value in (
            arguments.retry_failed,
            arguments.resume_after_manual_intervention,
            arguments.resume_interrupted_run,
            arguments.acknowledge_penalty_streak,
        )
    )
    if resolution_flags > 1:
        raise HardwareCliError(
            "Use only one of --retry-failed, "
            "--resume-after-manual-intervention, "
            "--resume-interrupted-run or "
            "--acknowledge-penalty-streak."
        )
    if (
        arguments.resume_after_manual_intervention
        or arguments.resume_interrupted_run
        or arguments.acknowledge_penalty_streak
    ) and arguments.from_run is None:
        raise HardwareCliError(
            "Manual resume and penalty-pause acknowledgement require "
            "--from-run X."
        )
    if (
        arguments.resume_after_manual_intervention
        or arguments.resume_interrupted_run
        or arguments.acknowledge_penalty_streak
    ) and not arguments.preflight_only:
        raise HardwareCliError(
            "Manual resume and penalty-pause acknowledgement must first "
            "run with --preflight-only."
        )
    if arguments.preflight_only and arguments.confirm_hardware:
        raise HardwareCliError(
            "Remove --confirm-hardware from a preflight-only command."
        )
    if arguments.new and not arguments.preflight_only:
        raise HardwareCliError(
            "A new physical experiment must first run with --new "
            "--preflight-only. Start it afterwards with --resume and "
            "--confirm-hardware."
        )
    if not arguments.preflight_only and not arguments.confirm_hardware:
        raise HardwareCliError(
            "A physical optimizer run requires --confirm-hardware."
        )


def _completed_summary(runner: FrameworkRunner) -> dict[str, object]:
    return {
        "mode": "optimizer_hardware_preflight",
        "experiment_directory": str(runner.store.directory),
        "completed_total": runner.store.state.completed_runs,
        "next_run_number": None,
        "status": "completed",
        "hardware_started": False,
    }


def _save_preflight_receipt(
    store: ExperimentStore,
    run: RunRecord,
    request: CycleRequest,
) -> Path:
    path = _preflight_receipt_path(store, run)
    payload = {
        "schema_version": 1,
        "experiment_id": store.state.experiment_id,
        "run_number": run.run_number,
        "attempt_number": run.attempt_number,
        "parameters": dict(run.parameters),
        "profile_path": str(request.profile_path),
        "gcode_path": str(request.gcode_path),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write_json(path, payload)
    return path


def _ensure_preflight_receipt(
    store: ExperimentStore,
    executor: OrchestratorRunExecutor,
    run: RunRecord,
) -> None:
    """Validate an existing receipt or create one before each batch attempt."""
    path = _preflight_receipt_path(store, run)
    if path.is_file():
        _require_preflight_receipt(store, run)
        return
    request = executor.preflight(run)
    _save_preflight_receipt(store, run, request)


def _require_preflight_receipt(
    store: ExperimentStore,
    run: RunRecord,
) -> None:
    path = _preflight_receipt_path(store, run)
    if not path.is_file() and run.run_number == 1 and run.attempt_number == 1:
        legacy_path = (
            store.directory / "logs" / INITIAL_PREFLIGHT_FILENAME
        )
        if legacy_path.is_file():
            path = legacy_path
    try:
        raw_value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HardwareCliError(
            "Initial hardware preflight receipt is missing. Run the same "
            "experiment with --resume --preflight-only first."
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise HardwareCliError(
            "Initial hardware preflight receipt cannot be read."
        ) from error
    if not isinstance(raw_value, Mapping):
        raise HardwareCliError(
            "Initial hardware preflight receipt must be a JSON object."
        )
    expected = {
        "experiment_id": store.state.experiment_id,
        "run_number": run.run_number,
        "attempt_number": run.attempt_number,
        "parameters": dict(run.parameters),
    }
    for name, expected_value in expected.items():
        if raw_value.get(name) != expected_value:
            raise HardwareCliError(
                "Initial hardware preflight receipt does not match the "
                f"current {name}. Run preflight again."
            )


def _preflight_receipt_path(store: ExperimentStore, run: RunRecord) -> Path:
    return (
        store.directory
        / "logs"
        / (
            f"preflight_run_{run.run_number:04d}_"
            f"attempt_{run.attempt_number:02d}.json"
        )
    )


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    temporary_path = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("x", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_project_orchestrator_builder() -> OrchestratorBuilder:
    from main import build_orchestrator

    return build_orchestrator


@contextmanager
def _camera_download_directory(path: Path) -> Iterator[None]:
    variable_name = "CAMERA_DOWNLOAD_DIR"
    previous_value = os.environ.get(variable_name)
    os.environ[variable_name] = str(path)
    try:
        yield
    finally:
        if previous_value is None:
            os.environ.pop(variable_name, None)
        else:
            os.environ[variable_name] = previous_value


@contextmanager
def _experiment_file_logging(directory: Path) -> Iterator[None]:
    log_path = directory / "logs" / "optimizer_hardware.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        handler.close()


def main(arguments: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        parsed = parse_arguments(arguments)
        result = run_hardware_command(parsed)
    except (RuntimeError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

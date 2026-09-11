from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from optimizer.config import OptimizerConfig, load_optimizer_config
from optimizer.experiment_store import (
    ExperimentStore,
    RunRecord,
    StrategyCheckpoint,
)
from optimizer.objective import (
    ObjectiveExpressionError,
    evaluate_objective_expression,
)
from optimizer.strategies import (
    ProposalBatch,
    StrategyProposal,
    build_strategy,
    observations_from_store,
)
from optimizer.warm_start import WarmStartGenerator


LOGGER = logging.getLogger(__name__)
RESULTS_FILENAME = "results.csv"
FRAMEWORK_BATCH_KEY = "framework_batch"


class FrameworkRunnerError(RuntimeError):
    """Raised when the framework cannot continue without risking state."""


class RunExecutorError(RuntimeError):
    """A classified execution error that may be persisted safely."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        failed_stage: str | None = None,
        cycle_id: str | None = None,
        consumes_attempt: bool = True,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.failed_stage = failed_stage
        self.cycle_id = cycle_id
        self.consumes_attempt = consumes_attempt


@dataclass(frozen=True)
class FailurePolicy:
    """Bound physical retries and stop persistent error sequences."""

    maximum_attempts_per_run: int = 2
    penalty_value: float = 100.0
    use_penalty_for_optimizer: bool = True
    maximum_consecutive_failed_parameter_sets: int = 3

    def __post_init__(self) -> None:
        _positive_integer(
            self.maximum_attempts_per_run,
            "maximum_attempts_per_run",
        )
        _positive_integer(
            self.maximum_consecutive_failed_parameter_sets,
            "maximum_consecutive_failed_parameter_sets",
        )
        _finite_number(self.penalty_value, "penalty_value")
        if not isinstance(self.use_penalty_for_optimizer, bool):
            raise FrameworkRunnerError(
                "use_penalty_for_optimizer must be boolean."
            )


@dataclass(frozen=True)
class ExecutionResult:
    """Measurements returned by one simulator or physical executor."""

    ra_um: float
    rz_um: float | None = None
    cycle_id: str | None = None
    print_time_seconds: float | None = None


class RunExecutor(Protocol):
    def execute(self, run: RunRecord) -> ExecutionResult: ...


class SyntheticSurfaceExecutor:
    """Deterministic test process that never contacts project hardware."""

    TARGET = {
        "top_solid_layers": 0.50,
        "print_speed": 0.35,
        "extrusion_width": 0.60,
        "extrusion_multiplier": 0.45,
        "temperature": 0.55,
        "fan_speed": 0.65,
    }

    def __init__(self, config: OptimizerConfig) -> None:
        self.config = config

    def execute(self, run: RunRecord) -> ExecutionResult:
        squared_distances: list[float] = []
        for variable in self.config.parameters:
            raw_value = float(run.parameters[variable.name])
            unit_value = (raw_value - float(variable.lower)) / (
                float(variable.upper) - float(variable.lower)
            )
            target = self.TARGET[variable.name]
            squared_distances.append((unit_value - target) ** 2)

        ra_um = 2.0 + 18.0 * sum(squared_distances) / len(
            squared_distances
        )
        ra_um = round(ra_um, 6)
        print_time_seconds = round(
            1200.0 * 70.0 / float(run.parameters["print_speed"]),
            6,
        )
        return ExecutionResult(
            ra_um=ra_um,
            rz_um=round(ra_um * 5.2, 6),
            print_time_seconds=print_time_seconds,
            cycle_id=(
                f"simulation-run-{run.run_number:04d}-"
                f"attempt-{run.attempt_number}"
            ),
        )


class FrameworkRunner:
    """Persist, execute and resume one configured optimization experiment."""

    def __init__(
        self,
        config: OptimizerConfig,
        store: ExperimentStore,
        executor: RunExecutor,
        *,
        failure_policy: FailurePolicy | None = None,
    ) -> None:
        _validate_step_five_config(config)
        self.config = config
        self.store = store
        self.executor = executor
        self.failure_policy = failure_policy or FailurePolicy()
        self.warm_start = WarmStartGenerator(config)
        self.strategy = build_strategy(config)

    @classmethod
    def create(
        cls,
        config: OptimizerConfig,
        executor: RunExecutor,
        *,
        failure_policy: FailurePolicy | None = None,
    ) -> "FrameworkRunner":
        _validate_step_five_config(config)
        return cls(
            config,
            ExperimentStore.create(config),
            executor,
            failure_policy=failure_policy,
        )

    @classmethod
    def resume(
        cls,
        config: OptimizerConfig,
        executor: RunExecutor,
        *,
        from_run: int | None = None,
        failure_policy: FailurePolicy | None = None,
    ) -> "FrameworkRunner":
        store = ExperimentStore.open(
            config.paths.output_directory,
            expected_config=config,
        )
        runner = cls(
            config,
            store,
            executor,
            failure_policy=failure_policy,
        )
        if from_run is not None:
            next_run = store.next_run_number()
            if next_run is None:
                raise FrameworkRunnerError(
                    "The experiment is complete; there is no run to resume."
                )
            store.load_resume_run(from_run)
        return runner

    def prepare_next_run(
        self,
        *,
        retry_failed: bool = False,
    ) -> RunRecord | None:
        """Return the persisted next proposal without executing it."""
        if self.store.state.pause_reason is not None:
            raise FrameworkRunnerError(self.store.state.pause_reason)
        next_run_number = self.store.next_run_number()
        if next_run_number is None:
            return None

        existing = self.store.load_resume_run(next_run_number)
        if existing is not None:
            return self._prepare_existing(
                existing,
                retry_failed=retry_failed,
            )

        if next_run_number <= self.config.warm_start.sample_count:
            return self.warm_start.propose_next(self.store)
        return self._prepare_main_strategy_run()

    def execute_next(
        self,
        *,
        retry_failed: bool = False,
        before_execute: Callable[[RunRecord], None] | None = None,
    ) -> RunRecord | None:
        """Execute exactly one persisted proposal and save its result."""
        proposed = self.prepare_next_run(retry_failed=retry_failed)
        if proposed is None:
            return None
        if before_execute is not None:
            try:
                before_execute(proposed)
            except RunExecutorError as error:
                self.store.mark_preflight_failed(
                    proposed.run_number,
                    error=str(error),
                    failed_stage=error.failed_stage,
                )
                raise FrameworkRunnerError(
                    f"Run {proposed.run_number} failed during preflight. "
                    "No physical attempt was consumed and unattended "
                    "execution was stopped."
                ) from error
        started = self.store.mark_run_started(proposed.run_number)
        try:
            result = self.executor.execute(started)
        except RunExecutorError as error:
            if error.retryable:
                if not error.consumes_attempt:
                    self.store.mark_preflight_failed(
                        started.run_number,
                        error=str(error),
                        failed_stage=error.failed_stage,
                    )
                    raise FrameworkRunnerError(
                        f"Run {started.run_number} failed before a physical "
                        "attempt was consumed. The same attempt remains "
                        "available after the cause is fixed."
                    ) from error
                failed = self.store.mark_attempt_failed(
                    started.run_number,
                    error=str(error),
                    failed_stage=error.failed_stage,
                    maximum_attempts=(
                        self.failure_policy.maximum_attempts_per_run
                    ),
                    penalty_value=self.failure_policy.penalty_value,
                    use_penalty_for_optimizer=(
                        self.failure_policy.use_penalty_for_optimizer
                    ),
                    maximum_consecutive_failed_parameter_sets=(
                        self.failure_policy.maximum_consecutive_failed_parameter_sets
                    ),
                    cycle_id=error.cycle_id,
                )
                if failed.status == "completed":
                    self.export_results_csv()
                    return failed
                raise FrameworkRunnerError(
                    f"Run {started.run_number} failed on comparable attempt "
                    f"{failed.soft_failure_count}/"
                    f"{self.failure_policy.maximum_attempts_per_run}. "
                    "The same parameters are saved for one retry."
                ) from error

            self.store.mark_manual_stop(
                started.run_number,
                error=str(error),
                failed_stage=error.failed_stage,
                cycle_id=error.cycle_id,
            )
            raise FrameworkRunnerError(
                f"Run {started.run_number} requires manual intervention. "
                "No optimizer observation was stored."
            ) from error

        ra_um = _finite_number(result.ra_um, "ExecutionResult.ra_um")
        rz_um = _finite_optional_number(
            result.rz_um,
            "ExecutionResult.rz_um",
        )
        print_time_seconds = _finite_optional_number(
            result.print_time_seconds,
            "ExecutionResult.print_time_seconds",
        )
        try:
            objective_value = evaluate_objective_expression(
                self.config.objective,
                ra_um=ra_um,
                rz_um=rz_um,
                print_time_seconds=print_time_seconds,
            )
        except ObjectiveExpressionError as error:
            self.store.mark_manual_stop(
                started.run_number,
                error=f"Objective evaluation failed: {error}",
                failed_stage="objective_evaluation",
                cycle_id=result.cycle_id,
            )
            raise FrameworkRunnerError(
                f"Run {started.run_number} produced measurements, but its "
                f"objective could not be evaluated: {error}"
            ) from error
        completed = self.store.mark_run_completed(
            started.run_number,
            objective_value=objective_value,
            ra_um=ra_um,
            rz_um=rz_um,
            print_time_seconds=print_time_seconds,
            cycle_id=result.cycle_id,
        )
        self.export_results_csv()
        return completed

    def run(
        self,
        *,
        max_runs: int | None = None,
        retry_failed: bool = False,
        automatic_retry: bool = False,
        before_execute: Callable[[RunRecord], None] | None = None,
    ) -> tuple[RunRecord, ...]:
        """Execute a bounded number of runs or finish the experiment."""
        if max_runs is not None:
            _positive_integer(max_runs, "max_runs")

        completed: list[RunRecord] = []
        retry_next = retry_failed
        while max_runs is None or len(completed) < max_runs:
            try:
                result = self.execute_next(
                    retry_failed=retry_next,
                    before_execute=before_execute,
                )
            except FrameworkRunnerError:
                retry_record = self._automatic_retry_candidate()
                if not automatic_retry or retry_record is None:
                    raise
                LOGGER.warning(
                    "Run %s failed on attempt %s/%s. Automatically "
                    "repeating the identical parameters once.",
                    retry_record.run_number,
                    retry_record.soft_failure_count,
                    self.failure_policy.maximum_attempts_per_run,
                )
                retry_next = True
                continue
            if result is None:
                break
            completed.append(result)
            if self.store.state.pause_reason is not None:
                break
            retry_next = False
        return tuple(completed)

    def _automatic_retry_candidate(self) -> RunRecord | None:
        """Return only a consumed, safe, retryable first attempt."""
        run_number = self.store.next_run_number()
        if run_number is None:
            return None
        record = self.store.load_resume_run(run_number)
        if record is None or record.status != "retryable_failed":
            return None
        if record.started_at is None:
            return None
        if (
            record.soft_failure_count
            >= self.failure_policy.maximum_attempts_per_run
        ):
            return None
        return record

    def export_results_csv(self) -> Path:
        """Rebuild the readable CSV from authoritative completed run JSON."""
        path = self.store.directory / RESULTS_FILENAME
        temporary_path = path.with_name(
            f".{path.name}.{uuid.uuid4().hex}.tmp"
        )
        fieldnames = [
            "run_number",
            "attempt_number",
            "strategy",
            "optimizer_iteration",
            "top_solid_layers",
            "print_speed",
            "extrusion_width",
            "extrusion_multiplier",
            "temperature",
            "fan_speed",
            "objective_value",
            "Ra_um",
            "Rz_um",
            "print_time_seconds",
            "observation_kind",
            "is_penalty",
            "is_ignored",
            "soft_failure_count",
            "failed_stage",
            "error",
            "cycle_id",
        ]
        try:
            with temporary_path.open(
                "x",
                encoding="utf-8",
                newline="",
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=fieldnames)
                writer.writeheader()
                for run_number in range(
                    1,
                    self.store.state.completed_runs + 1,
                ):
                    record = self.store.load_run(run_number)
                    writer.writerow(
                        {
                            "run_number": record.run_number,
                            "attempt_number": record.attempt_number,
                            "strategy": record.strategy,
                            "optimizer_iteration": (
                                ""
                                if record.optimizer_iteration is None
                                else record.optimizer_iteration
                            ),
                            **dict(record.parameters),
                            "objective_value": record.objective_value,
                            "Ra_um": record.ra_um,
                            "Rz_um": record.rz_um,
                            "print_time_seconds": (
                                record.print_time_seconds
                            ),
                            "observation_kind": (
                                "ignored_failure"
                                if record.is_ignored
                                else (
                                    "penalty"
                                    if record.is_penalty
                                    else "measured"
                                )
                            ),
                            "is_penalty": record.is_penalty,
                            "is_ignored": record.is_ignored,
                            "soft_failure_count": (
                                record.soft_failure_count
                            ),
                            "failed_stage": record.failed_stage or "",
                            "error": record.error or "",
                            "cycle_id": record.cycle_id or "",
                        }
                    )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return path

    def _prepare_existing(
        self,
        record: RunRecord,
        *,
        retry_failed: bool,
    ) -> RunRecord:
        if record.status == "proposed":
            self._validate_existing_main_proposal(record)
            return record
        if record.status == "retryable_failed":
            if retry_failed:
                return self.store.prepare_retry(
                    record.run_number,
                    maximum_attempts=(
                        self.failure_policy.maximum_attempts_per_run
                    ),
                )
            raise FrameworkRunnerError(
                f"Run {record.run_number} failed retryably. Resume with "
                "retry_failed=True to repeat the saved parameters."
            )
        if record.status == "running":
            raise FrameworkRunnerError(
                f"Run {record.run_number} was still marked running. Check "
                "the real printer and robot state before classifying it."
            )
        if (
            record.status == "terminal_failed"
            and record.failed_stage == "measurement_penalty"
            and retry_failed
        ):
            return self.store.prepare_retry(
                record.run_number,
                maximum_attempts=(
                    self.failure_policy.maximum_attempts_per_run
                ),
            )
        raise FrameworkRunnerError(
            f"Run {record.run_number} has blocking status {record.status!r}."
        )

    def _prepare_main_strategy_run(self) -> RunRecord:
        observations = observations_from_store(self.store)
        checkpoint = self.store.load_latest_strategy_checkpoint(
            self.config.strategy.name
        )
        if checkpoint is None:
            checkpoint = self._create_batch_checkpoint(
                self.strategy.propose(observations)
            )
        else:
            proposals = self._checkpoint_proposals(checkpoint)
            completed = self._completed_iteration_records(
                checkpoint.iteration
            )
            self._validate_completed_prefix(completed, proposals)
            if len(completed) == len(proposals):
                checkpoint = self._create_batch_checkpoint(
                    self.strategy.propose(observations, checkpoint)
                )

        proposals = self._checkpoint_proposals(checkpoint)
        completed = self._completed_iteration_records(checkpoint.iteration)
        self._validate_completed_prefix(completed, proposals)
        candidate_index = len(completed)
        if candidate_index >= len(proposals):
            raise FrameworkRunnerError(
                "The latest strategy batch is already complete, but no new "
                "batch was created."
            )
        proposal = proposals[candidate_index]
        return self.store.propose_run(
            proposal.parameters,
            strategy=checkpoint.strategy,
            optimizer_iteration=checkpoint.iteration,
        )

    def _create_batch_checkpoint(
        self,
        batch: ProposalBatch,
    ) -> StrategyCheckpoint:
        remaining_runs = (
            self.config.total_runs - self.store.state.completed_runs
        )
        if len(batch.proposals) > remaining_runs:
            raise FrameworkRunnerError(
                f"Strategy created {len(batch.proposals)} proposals, but "
                f"only {remaining_runs} experiment runs remain."
            )
        state = {
            **dict(batch.checkpoint_state),
            FRAMEWORK_BATCH_KEY: {
                "iteration": batch.iteration,
                "created_after_completed_runs": (
                    self.store.state.completed_runs
                ),
                "proposals": [
                    proposal.as_dict() for proposal in batch.proposals
                ],
            },
        }
        self.store.save_strategy_checkpoint(
            strategy=batch.strategy,
            iteration=batch.iteration,
            last_completed_run=self.store.state.completed_runs,
            state=state,
        )
        checkpoint = self.store.load_latest_strategy_checkpoint(
            batch.strategy
        )
        if checkpoint is None or checkpoint.iteration != batch.iteration:
            raise FrameworkRunnerError(
                "The newly saved strategy checkpoint could not be reloaded."
            )
        return checkpoint

    def _checkpoint_proposals(
        self,
        checkpoint: StrategyCheckpoint,
    ) -> tuple[StrategyProposal, ...]:
        raw_batch = checkpoint.state.get(FRAMEWORK_BATCH_KEY)
        if not isinstance(raw_batch, Mapping):
            raise FrameworkRunnerError(
                "Strategy checkpoint has no persisted framework batch."
            )
        if raw_batch.get("iteration") != checkpoint.iteration:
            raise FrameworkRunnerError(
                "Persisted framework batch has the wrong iteration."
            )
        raw_proposals = raw_batch.get("proposals")
        if not isinstance(raw_proposals, list) or not raw_proposals:
            raise FrameworkRunnerError(
                "Persisted framework batch has no proposals."
            )
        proposals: list[StrategyProposal] = []
        for expected_index, raw_proposal in enumerate(raw_proposals):
            if not isinstance(raw_proposal, Mapping):
                raise FrameworkRunnerError(
                    "Persisted strategy proposal must be an object."
                )
            if raw_proposal.get("candidate_index") != expected_index:
                raise FrameworkRunnerError(
                    "Persisted strategy candidate indices are not "
                    "continuous."
                )
            parameters = raw_proposal.get("parameters")
            if not isinstance(parameters, Mapping):
                raise FrameworkRunnerError(
                    "Persisted strategy proposal has no parameters."
                )
            proposals.append(
                StrategyProposal(
                    candidate_index=expected_index,
                    parameters=dict(parameters),
                )
            )
        proposal_count = checkpoint.state.get("proposal_count")
        if proposal_count != len(proposals):
            raise FrameworkRunnerError(
                "Checkpoint proposal_count does not match its saved batch."
            )
        return tuple(proposals)

    def _completed_iteration_records(
        self,
        iteration: int,
    ) -> tuple[RunRecord, ...]:
        records: list[RunRecord] = []
        for run_number in range(1, self.store.state.completed_runs + 1):
            record = self.store.load_run(run_number)
            if record.optimizer_iteration == iteration:
                records.append(record)
        return tuple(records)

    @staticmethod
    def _validate_completed_prefix(
        completed: Sequence[RunRecord],
        proposals: Sequence[StrategyProposal],
    ) -> None:
        if len(completed) > len(proposals):
            raise FrameworkRunnerError(
                "More completed runs exist than the saved strategy batch "
                "contains."
            )
        for record, proposal in zip(completed, proposals, strict=False):
            if dict(record.parameters) != dict(proposal.parameters):
                raise FrameworkRunnerError(
                    f"Completed run {record.run_number} does not match its "
                    "persisted strategy proposal."
                )

    def _validate_existing_main_proposal(self, record: RunRecord) -> None:
        if record.optimizer_iteration is None:
            return
        checkpoint = self.store.load_latest_strategy_checkpoint(
            self.config.strategy.name
        )
        if checkpoint is None:
            raise FrameworkRunnerError(
                "A main-strategy run exists without its checkpoint."
            )
        if record.optimizer_iteration != checkpoint.iteration:
            raise FrameworkRunnerError(
                "The unfinished run does not belong to the latest strategy "
                "checkpoint."
            )
        proposals = self._checkpoint_proposals(checkpoint)
        completed = self._completed_iteration_records(checkpoint.iteration)
        self._validate_completed_prefix(completed, proposals)
        candidate_index = len(completed)
        if candidate_index >= len(proposals):
            raise FrameworkRunnerError(
                "The unfinished run is outside the saved strategy batch."
            )
        if dict(record.parameters) != dict(
            proposals[candidate_index].parameters
        ):
            raise FrameworkRunnerError(
                "The unfinished run parameters differ from the saved "
                "strategy proposal."
            )


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise FrameworkRunnerError(f"{label} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise FrameworkRunnerError(
            f"{label} must be a finite number."
        ) from error
    if not math.isfinite(parsed):
        raise FrameworkRunnerError(f"{label} must be a finite number.")
    return parsed


def _validate_step_five_config(config: OptimizerConfig) -> None:
    if config.paths.history_csvs:
        raise FrameworkRunnerError(
            "history_csvs import is not implemented in framework step 5; "
            "remove those paths for the simulation test."
        )


def _finite_optional_number(
    value: object,
    label: str,
) -> float | None:
    return None if value is None else _finite_number(value, label)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FrameworkRunnerError(f"{label} must be an integer of at least 1.")
    return value


def _positive_cli_integer(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "value must be an integer."
        ) from error
    if value < 1:
        raise argparse.ArgumentTypeError("value must be at least 1.")
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run or resume the optimizer framework against the deterministic "
            "step-5 simulator. No project hardware is contacted."
        )
    )
    parser.add_argument("config", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new", action="store_true")
    mode.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--simulate",
        action="store_true",
        required=True,
        help="Required safety acknowledgement for the hardware-free mode.",
    )
    parser.add_argument("--from-run", type=_positive_cli_integer)
    parser.add_argument("--max-runs", type=_positive_cli_integer)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry one persisted retryable failure with identical parameters.",
    )
    parsed = parser.parse_args(arguments)
    if parsed.from_run is not None and not parsed.resume:
        parser.error("--from-run can only be used with --resume.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        config = load_optimizer_config(parsed.config)
        executor = SyntheticSurfaceExecutor(config)
        if parsed.new:
            runner = FrameworkRunner.create(config, executor)
        else:
            runner = FrameworkRunner.resume(
                config,
                executor,
                from_run=parsed.from_run,
            )
        completed = runner.run(
            max_runs=parsed.max_runs,
            retry_failed=parsed.retry_failed,
        )
        next_run = runner.store.next_run_number()
        print(
            json.dumps(
                {
                    "mode": "simulation",
                    "experiment_directory": str(runner.store.directory),
                    "completed_in_this_call": len(completed),
                    "completed_total": runner.store.state.completed_runs,
                    "next_run_number": next_run,
                    "status": runner.store.state.status,
                    "results_csv": str(
                        runner.store.directory / RESULTS_FILENAME
                    ),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except (RuntimeError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

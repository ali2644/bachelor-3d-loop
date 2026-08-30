from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from optimizer.config import (
    PARAMETER_DEFINITIONS,
    STRATEGY_ALIASES,
    OptimizerConfig,
)


EXPERIMENT_STATE_SCHEMA_VERSION = 1
RUN_STATE_SCHEMA_VERSION = 1
STRATEGY_STATE_SCHEMA_VERSION = 1

EXPERIMENT_STATUSES = frozenset(
    {"ready", "running", "blocked", "completed"}
)
RUN_STATUSES = frozenset(
    {
        "proposed",
        "running",
        "completed",
        "retryable_failed",
        "terminal_failed",
    }
)


class ExperimentStoreError(RuntimeError):
    """Raised when persisted experiment state is invalid or unsafe."""


@dataclass(frozen=True)
class ExperimentState:
    schema_version: int
    experiment_id: str
    experiment_name: str
    config_sha256: str
    status: str
    total_runs: int
    completed_runs: int
    consecutive_penalty_runs: int
    consecutive_ignored_runs: int
    consecutive_failed_parameter_sets: int
    failure_observation_mode: str | None
    current_run_number: int | None
    last_error: str | None
    pause_reason: str | None
    resume_run_number: int | None
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "experiment_name": self.experiment_name,
            "config_sha256": self.config_sha256,
            "status": self.status,
            "total_runs": self.total_runs,
            "completed_runs": self.completed_runs,
            "consecutive_penalty_runs": self.consecutive_penalty_runs,
            "consecutive_ignored_runs": self.consecutive_ignored_runs,
            "consecutive_failed_parameter_sets": (
                self.consecutive_failed_parameter_sets
            ),
            "failure_observation_mode": self.failure_observation_mode,
            "current_run_number": self.current_run_number,
            "last_error": self.last_error,
            "pause_reason": self.pause_reason,
            "resume_run_number": self.resume_run_number,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw_value: object) -> "ExperimentState":
        value = _require_mapping(raw_value, "run_state.json")
        state = cls(
            schema_version=_require_int(
                value,
                "schema_version",
                minimum=1,
            ),
            experiment_id=_require_text(value, "experiment_id"),
            experiment_name=_require_text(value, "experiment_name"),
            config_sha256=_require_text(value, "config_sha256"),
            status=_require_text(value, "status"),
            total_runs=_require_int(value, "total_runs", minimum=1),
            completed_runs=_require_int(
                value,
                "completed_runs",
                minimum=0,
            ),
            consecutive_penalty_runs=_optional_int_with_default(
                value,
                "consecutive_penalty_runs",
                default=0,
                minimum=0,
            ),
            consecutive_ignored_runs=_optional_int_with_default(
                value,
                "consecutive_ignored_runs",
                default=0,
                minimum=0,
            ),
            consecutive_failed_parameter_sets=_optional_int_with_default(
                value,
                "consecutive_failed_parameter_sets",
                default=0,
                minimum=0,
            ),
            failure_observation_mode=_optional_text(
                value,
                "failure_observation_mode",
            ),
            current_run_number=_optional_int(
                value,
                "current_run_number",
                minimum=1,
            ),
            last_error=_optional_text(value, "last_error"),
            pause_reason=_optional_text(value, "pause_reason"),
            resume_run_number=_optional_int(
                value,
                "resume_run_number",
                minimum=1,
            ),
            created_at=_require_timestamp(value, "created_at"),
            updated_at=_require_timestamp(value, "updated_at"),
        )
        if state.schema_version != EXPERIMENT_STATE_SCHEMA_VERSION:
            raise ExperimentStoreError(
                "Unsupported experiment-state schema version: "
                f"{state.schema_version}."
            )
        if state.status not in EXPERIMENT_STATUSES:
            raise ExperimentStoreError(
                f"Unknown experiment status {state.status!r}."
            )
        if state.failure_observation_mode not in {None, "penalty", "ignore"}:
            raise ExperimentStoreError(
                "failure_observation_mode must be 'penalty', 'ignore' or "
                "null."
            )
        if state.completed_runs > state.total_runs:
            raise ExperimentStoreError(
                "completed_runs cannot be greater than total_runs."
            )
        if (
            state.current_run_number is not None
            and state.current_run_number > state.total_runs
        ):
            raise ExperimentStoreError(
                "current_run_number cannot be greater than total_runs."
            )
        if (
            state.resume_run_number is not None
            and state.resume_run_number > state.total_runs
        ):
            raise ExperimentStoreError(
                "resume_run_number cannot be greater than total_runs."
            )
        if (state.pause_reason is None) != (state.resume_run_number is None):
            raise ExperimentStoreError(
                "pause_reason and resume_run_number must either both be "
                "set or both be null."
            )
        return state


@dataclass(frozen=True)
class RunRecord:
    schema_version: int
    run_number: int
    attempt_number: int
    status: str
    strategy: str
    optimizer_iteration: int | None
    parameters: Mapping[str, int | float]
    cycle_id: str | None
    objective_value: float | None
    ra_um: float | None
    rz_um: float | None
    is_penalty: bool
    is_ignored: bool
    soft_failure_count: int
    failed_stage: str | None
    error: str | None
    proposed_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_number": self.run_number,
            "attempt_number": self.attempt_number,
            "status": self.status,
            "strategy": self.strategy,
            "optimizer_iteration": self.optimizer_iteration,
            "parameters": dict(self.parameters),
            "cycle_id": self.cycle_id,
            "objective_value": self.objective_value,
            "Ra_um": self.ra_um,
            "Rz_um": self.rz_um,
            "is_penalty": self.is_penalty,
            "is_ignored": self.is_ignored,
            "soft_failure_count": self.soft_failure_count,
            "failed_stage": self.failed_stage,
            "error": self.error,
            "proposed_at": self.proposed_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw_value: object, label: str) -> "RunRecord":
        value = _require_mapping(raw_value, label)
        raw_parameters = _require_mapping(
            value.get("parameters"),
            f"{label}.parameters",
        )
        parameters = {
            name: _json_number(raw_parameter, f"{label}.parameters.{name}")
            for name, raw_parameter in raw_parameters.items()
        }
        objective_value = _optional_number(value, "objective_value")
        ra_um = _optional_number(value, "Ra_um")
        error_text = _optional_text(value, "error")
        failed_stage = _optional_text(value, "failed_stage")
        inferred_penalty = (
            objective_value is not None
            and ra_um is None
            and error_text is not None
        )
        inferred_soft_failures = 0
        if (
            _require_text(value, "status") in {
                "retryable_failed",
                "terminal_failed",
            }
            and failed_stage in {
                "measurement_penalty",
                "waiting_for_print",
                "result_validation",
            }
        ):
            inferred_soft_failures = 1
        if inferred_penalty:
            inferred_soft_failures = 2

        record = cls(
            schema_version=_require_int(
                value,
                "schema_version",
                minimum=1,
            ),
            run_number=_require_int(value, "run_number", minimum=1),
            attempt_number=_require_int(
                value,
                "attempt_number",
                minimum=1,
            ),
            status=_require_text(value, "status"),
            strategy=_require_text(value, "strategy"),
            optimizer_iteration=_optional_int(
                value,
                "optimizer_iteration",
                minimum=0,
            ),
            parameters=MappingProxyType(parameters),
            cycle_id=_optional_text(value, "cycle_id"),
            objective_value=objective_value,
            ra_um=ra_um,
            rz_um=_optional_number(value, "Rz_um"),
            is_penalty=_optional_bool_with_default(
                value,
                "is_penalty",
                default=inferred_penalty,
            ),
            is_ignored=_optional_bool_with_default(
                value,
                "is_ignored",
                default=False,
            ),
            soft_failure_count=_optional_int_with_default(
                value,
                "soft_failure_count",
                default=inferred_soft_failures,
                minimum=0,
            ),
            failed_stage=failed_stage,
            error=error_text,
            proposed_at=_require_timestamp(value, "proposed_at"),
            started_at=_optional_timestamp(value, "started_at"),
            finished_at=_optional_timestamp(value, "finished_at"),
            updated_at=_require_timestamp(value, "updated_at"),
        )
        if record.schema_version != RUN_STATE_SCHEMA_VERSION:
            raise ExperimentStoreError(
                f"Unsupported run-state schema version in {label}: "
                f"{record.schema_version}."
            )
        if record.status not in RUN_STATUSES:
            raise ExperimentStoreError(
                f"Unknown run status {record.status!r} in {label}."
            )
        if record.is_penalty:
            if record.status != "completed":
                raise ExperimentStoreError(
                    f"Penalty run in {label} must be completed."
                )
            if record.objective_value is None:
                raise ExperimentStoreError(
                    f"Penalty run in {label} has no objective value."
                )
            if record.ra_um is not None or record.rz_um is not None:
                raise ExperimentStoreError(
                    f"Penalty run in {label} must not claim measured Ra/Rz."
                )
        if record.is_ignored:
            if record.status != "completed":
                raise ExperimentStoreError(
                    f"Ignored run in {label} must be completed."
                )
            if record.objective_value is not None:
                raise ExperimentStoreError(
                    f"Ignored run in {label} must not have an objective."
                )
            if record.ra_um is not None or record.rz_um is not None:
                raise ExperimentStoreError(
                    f"Ignored run in {label} must not claim measured Ra/Rz."
                )
        if record.is_penalty and record.is_ignored:
            raise ExperimentStoreError(
                f"Run in {label} cannot be both penalty and ignored."
            )
        return record


@dataclass(frozen=True)
class StrategyCheckpoint:
    schema_version: int
    strategy: str
    iteration: int
    last_completed_run: int
    state: Mapping[str, object]
    saved_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "strategy": self.strategy,
            "iteration": self.iteration,
            "last_completed_run": self.last_completed_run,
            "state": dict(self.state),
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(
        cls,
        raw_value: object,
        label: str,
    ) -> "StrategyCheckpoint":
        value = _require_mapping(raw_value, label)
        checkpoint = cls(
            schema_version=_require_int(
                value,
                "schema_version",
                minimum=1,
            ),
            strategy=_require_text(value, "strategy"),
            iteration=_require_int(value, "iteration", minimum=0),
            last_completed_run=_require_int(
                value,
                "last_completed_run",
                minimum=0,
            ),
            state=MappingProxyType(
                dict(_require_mapping(value.get("state"), f"{label}.state"))
            ),
            saved_at=_require_timestamp(value, "saved_at"),
        )
        if checkpoint.schema_version != STRATEGY_STATE_SCHEMA_VERSION:
            raise ExperimentStoreError(
                f"Unsupported strategy-state schema version in {label}: "
                f"{checkpoint.schema_version}."
            )
        return checkpoint


class ExperimentStore:
    """Persist proposals, results and strategy checkpoints atomically."""

    CONFIG_FILENAME = "config_snapshot.json"
    STATE_FILENAME = "run_state.json"
    RUNS_DIRECTORY = "runs"
    ATTEMPT_HISTORY_DIRECTORY = "attempt_history"
    STRATEGY_DIRECTORY = "optimizer_state"

    def __init__(
        self,
        directory: Path,
        config_snapshot: Mapping[str, Any],
        state: ExperimentState,
    ) -> None:
        self.directory = directory
        self.config_snapshot = MappingProxyType(dict(config_snapshot))
        self.state = state

    @classmethod
    def create(cls, config: OptimizerConfig) -> "ExperimentStore":
        """Create a new experiment without overwriting an existing one."""
        output_directory = config.paths.output_directory
        if output_directory.exists():
            raise ExperimentStoreError(
                "Experiment output directory already exists; refusing to "
                f"overwrite it: {output_directory}"
            )

        output_directory.parent.mkdir(parents=True, exist_ok=True)
        temporary_directory = output_directory.with_name(
            f".{output_directory.name}.{uuid.uuid4().hex}.tmp"
        )
        timestamp = _utc_timestamp()
        snapshot = config.as_dict()
        config_sha256 = _config_sha256(snapshot)
        state = ExperimentState(
            schema_version=EXPERIMENT_STATE_SCHEMA_VERSION,
            experiment_id=uuid.uuid4().hex,
            experiment_name=config.experiment_name,
            config_sha256=config_sha256,
            status="ready",
            total_runs=config.total_runs,
            completed_runs=0,
            consecutive_penalty_runs=0,
            consecutive_ignored_runs=0,
            consecutive_failed_parameter_sets=0,
            failure_observation_mode=None,
            current_run_number=None,
            last_error=None,
            pause_reason=None,
            resume_run_number=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

        try:
            temporary_directory.mkdir()
            for child_name in (
                cls.RUNS_DIRECTORY,
                cls.ATTEMPT_HISTORY_DIRECTORY,
                cls.STRATEGY_DIRECTORY,
                "generated_profiles",
                "gcode",
                "logs",
            ):
                (temporary_directory / child_name).mkdir()
            _atomic_write_json(
                temporary_directory / cls.CONFIG_FILENAME,
                snapshot,
            )
            _atomic_write_json(
                temporary_directory / cls.STATE_FILENAME,
                state.as_dict(),
            )
            temporary_directory.replace(output_directory)
        except Exception:
            if temporary_directory.exists():
                shutil.rmtree(temporary_directory)
            raise

        return cls.open(output_directory, expected_config=config)

    @classmethod
    def open(
        cls,
        directory: str | Path,
        *,
        expected_config: OptimizerConfig | None = None,
    ) -> "ExperimentStore":
        """Open and reconcile an existing experiment directory."""
        resolved_directory = Path(directory).expanduser().resolve()
        if not resolved_directory.is_dir():
            raise ExperimentStoreError(
                f"Experiment directory not found: {resolved_directory}"
            )

        config_path = resolved_directory / cls.CONFIG_FILENAME
        state_path = resolved_directory / cls.STATE_FILENAME
        snapshot = _read_json_object(config_path)
        state = ExperimentState.from_dict(_read_json_object(state_path))
        stored_hash = _config_sha256(snapshot)
        if stored_hash != state.config_sha256:
            raise ExperimentStoreError(
                "The saved configuration snapshot does not match its "
                "recorded SHA-256 hash."
            )
        if expected_config is not None:
            expected_hash = _config_sha256(expected_config.as_dict())
            if expected_hash != stored_hash:
                raise ExperimentStoreError(
                    "The supplied configuration differs from the saved "
                    "experiment configuration. Resume was refused."
                )
        if state.experiment_name != snapshot.get("experiment_name"):
            raise ExperimentStoreError(
                "Experiment name differs between config_snapshot.json and "
                "run_state.json."
            )
        if state.total_runs != snapshot.get("total_runs"):
            raise ExperimentStoreError(
                "total_runs differs between config_snapshot.json and "
                "run_state.json."
            )

        store = cls(resolved_directory, snapshot, state)
        store._ensure_required_directories()
        store._reconcile_state()
        return store

    def propose_run(
        self,
        parameters: Mapping[str, int | float],
        *,
        strategy: str,
        optimizer_iteration: int | None = None,
    ) -> RunRecord:
        """Persist one proposal before any physical action starts."""
        run_number = self.next_run_number()
        if run_number is None:
            raise ExperimentStoreError("The experiment is already complete.")
        existing = self._load_run_if_present(run_number)
        if existing is not None:
            raise ExperimentStoreError(
                f"Run {run_number} already has a saved proposal with status "
                f"{existing.status!r}; load it instead of generating a new "
                "proposal."
            )

        canonical_strategy = self._validate_strategy(strategy)
        if optimizer_iteration is not None:
            _validate_plain_int(
                optimizer_iteration,
                "optimizer_iteration",
                minimum=0,
            )
        normalized_parameters = self._normalize_parameters(parameters)
        timestamp = _utc_timestamp()
        record = RunRecord(
            schema_version=RUN_STATE_SCHEMA_VERSION,
            run_number=run_number,
            attempt_number=1,
            status="proposed",
            strategy=canonical_strategy,
            optimizer_iteration=optimizer_iteration,
            parameters=MappingProxyType(normalized_parameters),
            cycle_id=None,
            objective_value=None,
            ra_um=None,
            rz_um=None,
            is_penalty=False,
            is_ignored=False,
            soft_failure_count=0,
            failed_stage=None,
            error=None,
            proposed_at=timestamp,
            started_at=None,
            finished_at=None,
            updated_at=timestamp,
        )
        self._write_run(record)
        self._reconcile_state()
        return record

    def mark_run_started(self, run_number: int) -> RunRecord:
        """Mark that the saved proposal is now entering the hardware loop."""
        record = self.load_run(run_number)
        if record.status != "proposed":
            raise ExperimentStoreError(
                f"Run {run_number} cannot start from status "
                f"{record.status!r}."
            )
        timestamp = _utc_timestamp()
        updated = replace(
            record,
            status="running",
            started_at=timestamp,
            updated_at=timestamp,
        )
        self._write_run(updated)
        self._reconcile_state()
        return updated

    def mark_run_completed(
        self,
        run_number: int,
        *,
        objective_value: float,
        ra_um: float | None,
        rz_um: float | None,
        cycle_id: str | None = None,
    ) -> RunRecord:
        """Persist a successful physical result before advancing."""
        record = self.load_run(run_number)
        if record.status != "running":
            raise ExperimentStoreError(
                f"Run {run_number} cannot complete from status "
                f"{record.status!r}."
            )
        timestamp = _utc_timestamp()
        updated = replace(
            record,
            status="completed",
            cycle_id=_clean_optional_text(cycle_id, "cycle_id"),
            objective_value=_finite_number(
                objective_value,
                "objective_value",
            ),
            ra_um=_finite_optional_number(ra_um, "ra_um"),
            rz_um=_finite_optional_number(rz_um, "rz_um"),
            is_penalty=False,
            is_ignored=False,
            failed_stage=None,
            error=None,
            finished_at=timestamp,
            updated_at=timestamp,
        )
        self._write_run(updated)
        self._reconcile_state()
        return updated

    def mark_preflight_failed(
        self,
        run_number: int,
        *,
        error: str,
        failed_stage: str | None = None,
    ) -> RunRecord:
        """Persist a preflight failure without consuming an attempt."""
        record = self.load_run(run_number)
        if record.status not in {"proposed", "running"}:
            raise ExperimentStoreError(
                f"Run {run_number} preflight cannot fail from status "
                f"{record.status!r}."
            )
        timestamp = _utc_timestamp()
        updated = replace(
            record,
            status="retryable_failed",
            failed_stage=_clean_optional_text(
                failed_stage,
                "failed_stage",
            ),
            error=_clean_required_text(error, "error"),
            objective_value=None,
            ra_um=None,
            rz_um=None,
            is_penalty=False,
            is_ignored=False,
            started_at=None,
            finished_at=timestamp,
            updated_at=timestamp,
        )
        self._write_run(updated)
        self._reconcile_state()
        return updated

    def mark_attempt_failed(
        self,
        run_number: int,
        *,
        error: str,
        failed_stage: str | None,
        maximum_attempts: int,
        penalty_value: float,
        use_penalty_for_optimizer: bool,
        maximum_consecutive_failed_parameter_sets: int,
        cycle_id: str | None = None,
    ) -> RunRecord:
        """Persist a failure, then either penalize or ignore after the limit."""
        record = self.load_run(run_number)
        if record.status != "running":
            raise ExperimentStoreError(
                f"Run {run_number} cannot record an attempt failure from "
                f"status {record.status!r}."
            )
        limit = _validate_plain_int(
            maximum_attempts,
            "maximum_attempts",
            minimum=1,
        )
        failed_set_streak_limit = _validate_plain_int(
            maximum_consecutive_failed_parameter_sets,
            "maximum_consecutive_failed_parameter_sets",
            minimum=1,
        )
        if not isinstance(use_penalty_for_optimizer, bool):
            raise ExperimentStoreError(
                "use_penalty_for_optimizer must be boolean."
            )
        next_soft_failure_count = record.soft_failure_count + 1
        if next_soft_failure_count > limit:
            raise ExperimentStoreError(
                f"Run {run_number} already reached the configured limit "
                f"of {limit} comparable failures."
            )

        timestamp = _utc_timestamp()
        failed = replace(
            record,
            status="retryable_failed",
            cycle_id=_clean_optional_text(cycle_id, "cycle_id"),
            objective_value=None,
            ra_um=None,
            rz_um=None,
            is_penalty=False,
            is_ignored=False,
            soft_failure_count=next_soft_failure_count,
            failed_stage=_clean_optional_text(
                failed_stage,
                "failed_stage",
            ),
            error=_clean_required_text(error, "error"),
            finished_at=timestamp,
            updated_at=timestamp,
        )

        if next_soft_failure_count < limit:
            self._write_run(failed)
            self._reconcile_state()
            return failed

        penalty = _finite_number(penalty_value, "penalty_value")
        self._archive_attempt(
            failed,
            action=(
                "penalty_after_max_attempts"
                if use_penalty_for_optimizer
                else "ignored_after_max_attempts"
            ),
        )
        completed = replace(
            failed,
            status="completed",
            objective_value=(penalty if use_penalty_for_optimizer else None),
            ra_um=None,
            rz_um=None,
            is_penalty=use_penalty_for_optimizer,
            is_ignored=not use_penalty_for_optimizer,
            updated_at=_utc_timestamp(),
        )
        self._write_run(completed)
        self._reconcile_state()
        if (
            self.state.completed_runs < self.state.total_runs
            and self.state.consecutive_failed_parameter_sets
            >= failed_set_streak_limit
        ):
            self._pause_after_failed_set_streak(
                resume_run_number=completed.run_number + 1,
                threshold=failed_set_streak_limit,
            )
        return completed

    def prepare_retry(
        self,
        run_number: int,
        *,
        maximum_attempts: int,
    ) -> RunRecord:
        """Reuse the saved parameters and count only started attempts."""
        record = self.load_run(run_number)
        legacy_measurement_failure = (
            record.status == "terminal_failed"
            and record.failed_stage == "measurement_penalty"
        )
        if record.status != "retryable_failed" and not legacy_measurement_failure:
            raise ExperimentStoreError(
                f"Run {run_number} is not marked as retryable_failed."
            )
        limit = _validate_plain_int(
            maximum_attempts,
            "maximum_attempts",
            minimum=1,
        )
        hardware_attempt_failed = record.started_at is not None
        soft_failure_count = record.soft_failure_count
        if legacy_measurement_failure and soft_failure_count == 0:
            soft_failure_count = 1
        next_attempt = record.attempt_number
        if hardware_attempt_failed:
            if soft_failure_count >= limit:
                raise ExperimentStoreError(
                    f"Run {run_number} already reached the configured "
                    f"limit of {limit} comparable failures."
                )
            self._archive_attempt(
                record,
                action="retry_same_parameters",
            )
            next_attempt += 1

        timestamp = _utc_timestamp()
        updated = replace(
            record,
            attempt_number=next_attempt,
            status="proposed",
            cycle_id=None,
            objective_value=None,
            ra_um=None,
            rz_um=None,
            is_penalty=False,
            is_ignored=False,
            soft_failure_count=soft_failure_count,
            failed_stage=None,
            error=None,
            proposed_at=timestamp,
            started_at=None,
            finished_at=None,
            updated_at=timestamp,
        )
        self._write_run(updated)
        self._reconcile_state()
        return updated

    def mark_manual_stop(
        self,
        run_number: int,
        *,
        error: str,
        failed_stage: str | None,
        cycle_id: str | None = None,
    ) -> RunRecord:
        """Pause a changed or unsafe hardware state without a penalty."""
        record = self.load_run(run_number)
        if record.status != "running":
            raise ExperimentStoreError(
                f"Run {run_number} cannot require manual intervention from "
                f"status {record.status!r}."
            )
        timestamp = _utc_timestamp()
        stopped = replace(
            record,
            status="terminal_failed",
            cycle_id=_clean_optional_text(cycle_id, "cycle_id"),
            objective_value=None,
            ra_um=None,
            rz_um=None,
            is_penalty=False,
            is_ignored=False,
            failed_stage=_clean_optional_text(
                failed_stage,
                "failed_stage",
            ),
            error=_clean_required_text(error, "error"),
            finished_at=timestamp,
            updated_at=timestamp,
        )
        self._write_run(stopped)
        self._reconcile_state()
        return stopped

    def prepare_manual_resume(self, run_number: int) -> RunRecord:
        """Prepare the same run after an explicit manual plant check."""
        record = self.load_run(run_number)
        if record.status != "terminal_failed":
            raise ExperimentStoreError(
                f"Run {run_number} is not waiting for manual intervention."
            )
        self._archive_attempt(
            record,
            action="resume_after_manual_intervention",
        )
        timestamp = _utc_timestamp()
        resumed = replace(
            record,
            attempt_number=record.attempt_number + 1,
            status="proposed",
            cycle_id=None,
            objective_value=None,
            ra_um=None,
            rz_um=None,
            is_penalty=False,
            is_ignored=False,
            failed_stage=None,
            error=None,
            proposed_at=timestamp,
            started_at=None,
            finished_at=None,
            updated_at=timestamp,
        )
        self._write_run(resumed)
        self._reconcile_state()
        return resumed

    def acknowledge_failed_set_pause(self, from_run: int) -> None:
        """Clear only the persistent failed-parameter-set circuit breaker."""
        if self.state.pause_reason is None:
            raise ExperimentStoreError(
                "The experiment is not paused by the failed-set circuit "
                "breaker."
            )
        if from_run != self.state.resume_run_number:
            raise ExperimentStoreError(
                "The failed-set pause can only resume at run "
                f"{self.state.resume_run_number}."
            )
        timestamp = _utc_timestamp()
        self.state = replace(
            self.state,
            pause_reason=None,
            resume_run_number=None,
            last_error=None,
            updated_at=timestamp,
        )
        _atomic_write_json(
            self.directory / self.STATE_FILENAME,
            self.state.as_dict(),
        )
        self._reconcile_state()

    def configure_failure_observation_mode(self, mode: str) -> str:
        """Persist one immutable penalty/ignore decision per experiment."""
        normalized = _clean_required_text(
            mode,
            "failure_observation_mode",
        ).lower()
        if normalized not in {"penalty", "ignore"}:
            raise ExperimentStoreError(
                "failure_observation_mode must be 'penalty' or 'ignore'."
            )
        configured = self.state.failure_observation_mode
        historical_modes: set[str] = set()
        for run_number in range(1, self.state.completed_runs + 1):
            record = self.load_run(run_number)
            if record.is_penalty:
                historical_modes.add("penalty")
            if record.is_ignored:
                historical_modes.add("ignore")
        if len(historical_modes) > 1:
            raise ExperimentStoreError(
                "Existing completed runs contain mixed penalty and ignore "
                "handling; automatic mode cannot be selected safely."
            )
        if historical_modes and normalized not in historical_modes:
            previous_mode = next(iter(historical_modes))
            raise ExperimentStoreError(
                "Existing completed failures already use "
                f"failure_observation_mode={previous_mode!r}."
            )
        if configured is not None and configured != normalized:
            raise ExperimentStoreError(
                "This experiment already uses failure_observation_mode="
                f"{configured!r}; changing it during the experiment is "
                "refused."
            )
        if configured is None:
            self.state = replace(
                self.state,
                failure_observation_mode=normalized,
                updated_at=_utc_timestamp(),
            )
            _atomic_write_json(
                self.directory / self.STATE_FILENAME,
                self.state.as_dict(),
            )
        return normalized

    def acknowledge_penalty_pause(self, from_run: int) -> None:
        """Backward-compatible alias for old CLI integrations."""
        self.acknowledge_failed_set_pause(from_run)

    def acknowledge_ignored_pause(self, from_run: int) -> None:
        """Backward-compatible alias for the intermediate API name."""
        self.acknowledge_failed_set_pause(from_run)

    def load_run(self, run_number: int) -> RunRecord:
        _validate_plain_int(run_number, "run_number", minimum=1)
        path = self._run_path(run_number)
        if not path.is_file():
            raise ExperimentStoreError(f"Run {run_number} is not saved.")
        record = RunRecord.from_dict(
            _read_json_object(path),
            path.name,
        )
        if record.run_number != run_number:
            raise ExperimentStoreError(
                f"Run number inside {path.name} does not match its filename."
            )
        self._normalize_parameters(record.parameters)
        return record

    def load_resume_run(
        self,
        from_run: int | None = None,
    ) -> RunRecord | None:
        """Return the one existing unfinished run that must be resumed."""
        next_run = self.next_run_number()
        if next_run is None:
            return None
        requested_run = next_run if from_run is None else from_run
        _validate_plain_int(requested_run, "from_run", minimum=1)
        if requested_run != next_run:
            raise ExperimentStoreError(
                f"The safe resume point is run {next_run}; refusing to "
                f"skip to run {requested_run}."
            )
        return self._load_run_if_present(requested_run)

    def next_run_number(self) -> int | None:
        """Return the first missing or unfinished run in sequence."""
        existing_numbers = self._existing_run_numbers()
        for run_number in range(1, self.state.total_runs + 1):
            if run_number not in existing_numbers:
                later = sorted(
                    number
                    for number in existing_numbers
                    if number > run_number
                )
                if later:
                    raise ExperimentStoreError(
                        f"Run history has a gap at run {run_number}; later "
                        f"records already exist: {later}."
                    )
                return run_number
            record = self.load_run(run_number)
            if record.status != "completed":
                return run_number
        return None

    def save_strategy_checkpoint(
        self,
        *,
        strategy: str,
        iteration: int,
        last_completed_run: int,
        state: Mapping[str, object],
    ) -> Path:
        """Save one immutable algorithm checkpoint for an iteration."""
        canonical_strategy = self._validate_strategy(strategy)
        _validate_plain_int(iteration, "iteration", minimum=0)
        _validate_plain_int(
            last_completed_run,
            "last_completed_run",
            minimum=0,
        )
        if last_completed_run > self.state.completed_runs:
            raise ExperimentStoreError(
                "last_completed_run cannot be greater than the number of "
                "persisted completed runs."
            )
        if not isinstance(state, Mapping):
            raise ExperimentStoreError(
                "Strategy checkpoint state must be a mapping."
            )
        state_copy = dict(state)
        try:
            json.dumps(state_copy, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ExperimentStoreError(
                "Strategy checkpoint state must be JSON serializable."
            ) from error

        checkpoint = StrategyCheckpoint(
            schema_version=STRATEGY_STATE_SCHEMA_VERSION,
            strategy=canonical_strategy,
            iteration=iteration,
            last_completed_run=last_completed_run,
            state=MappingProxyType(state_copy),
            saved_at=_utc_timestamp(),
        )
        path = self._strategy_checkpoint_path(
            canonical_strategy,
            iteration,
        )
        if path.exists():
            raise ExperimentStoreError(
                f"Strategy checkpoint already exists: {path.name}"
            )
        _atomic_write_json(path, checkpoint.as_dict())
        return path

    def load_latest_strategy_checkpoint(
        self,
        strategy: str,
    ) -> StrategyCheckpoint | None:
        canonical_strategy = self._validate_strategy(strategy)
        paths = sorted(
            (self.directory / self.STRATEGY_DIRECTORY).glob(
                f"{canonical_strategy}_iteration_*.json"
            )
        )
        if not paths:
            return None
        path = paths[-1]
        checkpoint = StrategyCheckpoint.from_dict(
            _read_json_object(path),
            path.name,
        )
        if checkpoint.strategy != canonical_strategy:
            raise ExperimentStoreError(
                f"Strategy inside {path.name} does not match its filename."
            )
        return checkpoint

    def _normalize_parameters(
        self,
        raw_parameters: Mapping[str, int | float],
    ) -> dict[str, int | float]:
        if not isinstance(raw_parameters, Mapping):
            raise ExperimentStoreError("parameters must be a mapping.")
        variable_bounds = self._configured_variable_bounds()
        fixed_parameters = self._configured_fixed_parameters()
        expected_names = set(variable_bounds) | set(fixed_parameters)
        actual_names = set(raw_parameters)
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            unexpected = sorted(actual_names - expected_names)
            details: list[str] = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if unexpected:
                details.append("unexpected: " + ", ".join(unexpected))
            raise ExperimentStoreError(
                "Proposal parameters do not match the configuration ("
                + "; ".join(details)
                + ")."
            )

        normalized: dict[str, int | float] = {}
        ordered_names = [*variable_bounds, *fixed_parameters]
        for name in ordered_names:
            value = _finite_number(raw_parameters[name], f"parameters.{name}")
            definition = PARAMETER_DEFINITIONS[name]
            quantized = definition.quantize(value)
            if name in variable_bounds:
                lower, upper = variable_bounds[name]
                if not float(lower) <= float(quantized) <= float(upper):
                    raise ExperimentStoreError(
                        f"parameters.{name} must be between {lower} and "
                        f"{upper}, got {value}."
                    )
            else:
                required_value = fixed_parameters[name]
                if quantized != required_value:
                    raise ExperimentStoreError(
                        f"parameters.{name} must equal the configured fixed "
                        f"value {required_value}, got {value}."
                    )
            normalized[name] = quantized
        return normalized

    def _configured_variable_bounds(
        self,
    ) -> dict[str, tuple[int | float, int | float]]:
        raw_parameters = self.config_snapshot.get("parameters")
        if not isinstance(raw_parameters, list):
            raise ExperimentStoreError(
                "config_snapshot.json has invalid parameters."
            )
        bounds: dict[str, tuple[int | float, int | float]] = {}
        for raw_parameter in raw_parameters:
            parameter = _require_mapping(
                raw_parameter,
                "config_snapshot.parameters entry",
            )
            name = _require_text(parameter, "name")
            if name not in PARAMETER_DEFINITIONS:
                raise ExperimentStoreError(
                    f"Unknown parameter {name!r} in config snapshot."
                )
            lower = _json_number(parameter.get("lower"), f"{name}.lower")
            upper = _json_number(parameter.get("upper"), f"{name}.upper")
            bounds[name] = (lower, upper)
        return bounds

    def _configured_fixed_parameters(self) -> dict[str, int | float]:
        raw_fixed = _require_mapping(
            self.config_snapshot.get("fixed_parameters"),
            "config_snapshot.fixed_parameters",
        )
        return {
            name: PARAMETER_DEFINITIONS[name].quantize(
                _json_number(value, f"fixed_parameters.{name}")
            )
            for name, value in raw_fixed.items()
        }

    def _validate_strategy(self, supplied_strategy: str) -> str:
        if not isinstance(supplied_strategy, str):
            raise ExperimentStoreError("strategy must be text.")
        canonical = STRATEGY_ALIASES.get(supplied_strategy.strip().lower())
        if canonical is None:
            raise ExperimentStoreError(
                f"Unknown strategy {supplied_strategy!r}."
            )
        raw_strategy = _require_mapping(
            self.config_snapshot.get("strategy"),
            "config_snapshot.strategy",
        )
        configured = _require_text(raw_strategy, "name")
        if canonical != configured:
            raise ExperimentStoreError(
                f"Strategy {canonical!r} does not match the configured "
                f"strategy {configured!r}."
            )
        return canonical

    def _reconcile_state(self) -> None:
        """Repair a stale summary from the authoritative per-run files."""
        completed_runs = 0
        current_record: RunRecord | None = None
        existing_numbers = self._existing_run_numbers()
        for run_number in range(1, self.state.total_runs + 1):
            if run_number not in existing_numbers:
                break
            record = self.load_run(run_number)
            if record.status == "completed":
                completed_runs += 1
                continue
            current_record = record
            break

        consecutive_penalty_runs = 0
        for run_number in range(completed_runs, 0, -1):
            if not self.load_run(run_number).is_penalty:
                break
            consecutive_penalty_runs += 1

        consecutive_ignored_runs = 0
        for run_number in range(completed_runs, 0, -1):
            if not self.load_run(run_number).is_ignored:
                break
            consecutive_ignored_runs += 1

        consecutive_failed_parameter_sets = 0
        for run_number in range(completed_runs, 0, -1):
            record = self.load_run(run_number)
            if not (record.is_penalty or record.is_ignored):
                break
            consecutive_failed_parameter_sets += 1

        if completed_runs == self.state.total_runs:
            status = "completed"
            current_run_number = None
            last_error = None
            pause_reason = None
            resume_run_number = None
        elif self.state.pause_reason is not None:
            status = "blocked"
            current_run_number = self.state.resume_run_number
            last_error = self.state.pause_reason
            pause_reason = self.state.pause_reason
            resume_run_number = self.state.resume_run_number
        elif current_record is None:
            status = "ready"
            current_run_number = None
            last_error = None
            pause_reason = None
            resume_run_number = None
        elif current_record.status in {
            "retryable_failed",
            "terminal_failed",
        }:
            status = "blocked"
            current_run_number = current_record.run_number
            last_error = current_record.error
            pause_reason = None
            resume_run_number = None
        else:
            status = "running"
            current_run_number = current_record.run_number
            last_error = None
            pause_reason = None
            resume_run_number = None

        reconciled = replace(
            self.state,
            status=status,
            completed_runs=completed_runs,
            consecutive_penalty_runs=consecutive_penalty_runs,
            consecutive_ignored_runs=consecutive_ignored_runs,
            consecutive_failed_parameter_sets=(
                consecutive_failed_parameter_sets
            ),
            current_run_number=current_run_number,
            last_error=last_error,
            pause_reason=pause_reason,
            resume_run_number=resume_run_number,
        )
        if reconciled != self.state:
            reconciled = replace(reconciled, updated_at=_utc_timestamp())
            _atomic_write_json(
                self.directory / self.STATE_FILENAME,
                reconciled.as_dict(),
            )
            self.state = reconciled

    def _pause_after_failed_set_streak(
        self,
        *,
        resume_run_number: int,
        threshold: int,
    ) -> None:
        reason = (
            f"Safety stop after {threshold} consecutive failed parameter "
            "sets. "
            "Inspect the plant before acknowledging the pause."
        )
        self.state = replace(
            self.state,
            status="blocked",
            current_run_number=resume_run_number,
            last_error=reason,
            pause_reason=reason,
            resume_run_number=resume_run_number,
            updated_at=_utc_timestamp(),
        )
        _atomic_write_json(
            self.directory / self.STATE_FILENAME,
            self.state.as_dict(),
        )

    def _ensure_required_directories(self) -> None:
        for child_name in (
            self.RUNS_DIRECTORY,
            self.STRATEGY_DIRECTORY,
            "generated_profiles",
            "gcode",
            "logs",
        ):
            path = self.directory / child_name
            if not path.is_dir():
                raise ExperimentStoreError(
                    f"Required experiment directory is missing: {path}"
                )
        # Existing step-1-to-8 experiments are upgraded without modifying
        # their saved run records.
        (
            self.directory / self.ATTEMPT_HISTORY_DIRECTORY
        ).mkdir(exist_ok=True)

    def _load_run_if_present(self, run_number: int) -> RunRecord | None:
        path = self._run_path(run_number)
        return self.load_run(run_number) if path.is_file() else None

    def _write_run(self, record: RunRecord) -> None:
        _atomic_write_json(
            self._run_path(record.run_number),
            record.as_dict(),
        )

    def _archive_attempt(
        self,
        record: RunRecord,
        *,
        action: str,
    ) -> Path:
        path = (
            self.directory
            / self.ATTEMPT_HISTORY_DIRECTORY
            / (
                f"run_{record.run_number:04d}_"
                f"attempt_{record.attempt_number:02d}.json"
            )
        )
        sequence = 2
        while path.exists():
            path = (
                self.directory
                / self.ATTEMPT_HISTORY_DIRECTORY
                / (
                    f"run_{record.run_number:04d}_"
                    f"attempt_{record.attempt_number:02d}_"
                    f"event_{sequence:02d}.json"
                )
            )
            sequence += 1
        _atomic_write_json(
            path,
            {
                "schema_version": 1,
                "action": _clean_required_text(action, "action"),
                "archived_at": _utc_timestamp(),
                "run": record.as_dict(),
            },
        )
        return path

    def _run_path(self, run_number: int) -> Path:
        return (
            self.directory
            / self.RUNS_DIRECTORY
            / f"run_{run_number:04d}.json"
        )

    def _existing_run_numbers(self) -> set[int]:
        numbers: set[int] = set()
        for path in (self.directory / self.RUNS_DIRECTORY).glob(
            "run_*.json"
        ):
            raw_number = path.stem.removeprefix("run_")
            if not raw_number.isdigit():
                raise ExperimentStoreError(
                    f"Invalid run-state filename: {path.name}"
                )
            number = int(raw_number)
            if number < 1 or number > self.state.total_runs:
                raise ExperimentStoreError(
                    f"Run-state filename is outside total_runs: {path.name}"
                )
            numbers.add(number)
        return numbers

    def _strategy_checkpoint_path(
        self,
        strategy: str,
        iteration: int,
    ) -> Path:
        return (
            self.directory
            / self.STRATEGY_DIRECTORY
            / f"{strategy}_iteration_{iteration:04d}.json"
        )


def _config_sha256(snapshot: Mapping[str, Any]) -> str:
    semantic_snapshot = dict(snapshot)
    semantic_snapshot.pop("source_path", None)
    serialized = json.dumps(
        semantic_snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


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


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError as error:
        raise ExperimentStoreError(
            f"Required state file is missing: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise ExperimentStoreError(
            f"Invalid JSON in {path} at line {error.lineno}, column "
            f"{error.colno}: {error.msg}."
        ) from error
    if not isinstance(value, dict):
        raise ExperimentStoreError(f"{path} must contain a JSON object.")
    return value


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_mapping(raw_value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(raw_value, dict):
        raise ExperimentStoreError(f"{label} must be a JSON object.")
    if any(not isinstance(key, str) for key in raw_value):
        raise ExperimentStoreError(f"{label} contains a non-text key.")
    return raw_value


def _require_text(value: Mapping[str, Any], key: str) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ExperimentStoreError(f"{key} must be non-empty text.")
    return raw_value.strip()


def _optional_text(value: Mapping[str, Any], key: str) -> str | None:
    raw_value = value.get(key)
    if raw_value is None:
        return None
    return _clean_required_text(raw_value, key)


def _clean_required_text(raw_value: object, label: str) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ExperimentStoreError(f"{label} must be non-empty text.")
    return raw_value.strip()


def _clean_optional_text(raw_value: object, label: str) -> str | None:
    if raw_value is None:
        return None
    return _clean_required_text(raw_value, label)


def _require_int(
    value: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
) -> int:
    if key not in value:
        raise ExperimentStoreError(f"{key} is required.")
    return _validate_plain_int(value[key], key, minimum=minimum)


def _optional_int(
    value: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
) -> int | None:
    raw_value = value.get(key)
    if raw_value is None:
        return None
    return _validate_plain_int(raw_value, key, minimum=minimum)


def _optional_int_with_default(
    value: Mapping[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
) -> int:
    if key not in value:
        return default
    return _validate_plain_int(value[key], key, minimum=minimum)


def _optional_bool_with_default(
    value: Mapping[str, Any],
    key: str,
    *,
    default: bool,
) -> bool:
    if key not in value:
        return default
    raw_value = value[key]
    if not isinstance(raw_value, bool):
        raise ExperimentStoreError(f"{key} must be true or false.")
    return raw_value


def _validate_plain_int(raw_value: object, label: str, *, minimum: int) -> int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise ExperimentStoreError(f"{label} must be an integer.")
    if raw_value < minimum:
        raise ExperimentStoreError(f"{label} must be at least {minimum}.")
    return raw_value


def _json_number(raw_value: object, label: str) -> int | float:
    value = _finite_number(raw_value, label)
    if isinstance(raw_value, int) and not isinstance(raw_value, bool):
        return int(raw_value)
    return value


def _finite_number(raw_value: object, label: str) -> float:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise ExperimentStoreError(f"{label} must be numeric.")
    value = float(raw_value)
    if not math.isfinite(value):
        raise ExperimentStoreError(f"{label} must be finite.")
    return value


def _finite_optional_number(
    raw_value: object,
    label: str,
) -> float | None:
    if raw_value is None:
        return None
    return _finite_number(raw_value, label)


def _optional_number(
    value: Mapping[str, Any],
    key: str,
) -> float | None:
    return _finite_optional_number(value.get(key), key)


def _require_timestamp(value: Mapping[str, Any], key: str) -> str:
    timestamp = _require_text(value, key)
    _validate_timestamp(timestamp, key)
    return timestamp


def _optional_timestamp(
    value: Mapping[str, Any],
    key: str,
) -> str | None:
    timestamp = _optional_text(value, key)
    if timestamp is not None:
        _validate_timestamp(timestamp, key)
    return timestamp


def _validate_timestamp(timestamp: str, label: str) -> None:
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as error:
        raise ExperimentStoreError(
            f"{label} must be an ISO-8601 timestamp."
        ) from error
    if parsed.tzinfo is None:
        raise ExperimentStoreError(f"{label} must contain a timezone.")

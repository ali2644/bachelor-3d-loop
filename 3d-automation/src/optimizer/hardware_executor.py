from __future__ import annotations

import math
from pathlib import Path
from typing import Mapping, Protocol

from optimizer.config import OptimizerConfig
from optimizer.experiment_store import RunRecord
from optimizer.framework_runner import ExecutionResult, RunExecutorError
from orchestrator import (
    CycleExecutionError,
    CycleRequest,
    CycleResult,
    CycleStage,
    CycleStatus,
)
from printer.print_parameters import (
    PrintParameters,
    SlicerProfileGenerator,
)


class PrintOrchestratorProtocol(Protocol):
    def run_preflight(
        self,
        request: CycleRequest,
        *,
        include_printer: bool = True,
    ) -> None: ...

    def run_single_print_cycle(
        self,
        request: CycleRequest,
    ) -> CycleResult: ...


class ProfileGeneratorProtocol(Protocol):
    def generate(
        self,
        base_profile_path: str | Path,
        parameters: PrintParameters,
        *,
        output_filename: str | None = None,
    ) -> Path: ...


class OrchestratorRunExecutor:
    """Adapt one persisted framework run to the physical orchestrator."""

    SAFE_REPEAT_STAGES = frozenset(
        {
            CycleStage.PREFLIGHT,
            CycleStage.SLICING,
        }
    )
    COMPARABLE_FAILURE_STAGES = frozenset(
        {
            CycleStage.WAITING_FOR_PRINT,
            CycleStage.MEASURING,
        }
    )

    def __init__(
        self,
        config: OptimizerConfig,
        orchestrator: PrintOrchestratorProtocol,
        *,
        profile_generator: ProfileGeneratorProtocol | None = None,
    ) -> None:
        config.validate_input_files()
        self.config = config
        self.orchestrator = orchestrator
        self.experiment_directory = config.paths.output_directory
        self.profile_generator = (
            profile_generator
            if profile_generator is not None
            else SlicerProfileGenerator(
                self.experiment_directory / "generated_profiles"
            )
        )

    def build_request(self, run: RunRecord) -> CycleRequest:
        """Create profile and paths without contacting any hardware."""
        try:
            parameters = _print_parameters(run.parameters)
            label = (
                f"run_{run.run_number:04d}_"
                f"attempt_{run.attempt_number:02d}"
            )
            profile_path = self.profile_generator.generate(
                self.config.paths.base_profile,
                parameters,
                output_filename=f"{label}_profile.ini",
            ).resolve()
            gcode_path = (
                self.experiment_directory / "gcode" / f"{label}.gcode"
            ).resolve()
            return CycleRequest(
                stl_path=self.config.paths.stl,
                profile_path=profile_path,
                gcode_path=gcode_path,
                print_parameters=parameters.as_record(),
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise RunExecutorError(
                f"Could not prepare run {run.run_number}: {error}",
                retryable=True,
                failed_stage="request_preparation",
                consumes_attempt=False,
            ) from error

    def preflight(self, run: RunRecord) -> CycleRequest:
        """Generate the request and check hardware without starting a print."""
        request = self.build_request(run)
        try:
            self.orchestrator.run_preflight(
                request,
                include_printer=True,
            )
        except CycleExecutionError as error:
            raise self._classified_cycle_error(error) from error
        except Exception as error:
            raise RunExecutorError(
                f"Unexpected preflight failure: {error}",
                retryable=True,
                failed_stage=CycleStage.PREFLIGHT.value,
                consumes_attempt=False,
            ) from error
        return request

    def execute(self, run: RunRecord) -> ExecutionResult:
        request = self.build_request(run)
        try:
            result = self.orchestrator.run_single_print_cycle(request)
        except CycleExecutionError as error:
            raise self._classified_cycle_error(error) from error
        except Exception as error:
            raise RunExecutorError(
                f"Unexpected orchestrator failure: {error}",
                retryable=False,
                failed_stage="unknown_hardware_state",
            ) from error
        return self._execution_result(result)

    def _execution_result(self, result: CycleResult) -> ExecutionResult:
        if result.status != CycleStatus.COMPLETED:
            raise RunExecutorError(
                "Orchestrator returned a non-completed cycle without "
                "raising CycleExecutionError.",
                retryable=False,
                failed_stage=result.stage.value,
            )
        if result.stage != CycleStage.COMPLETED:
            raise RunExecutorError(
                "Completed cycle has an inconsistent final stage.",
                retryable=False,
                failed_stage=result.stage.value,
            )
        if result.error:
            handling_recovery = (
                "Final push was aborted" in result.error
                or "final push failed" in result.error.lower()
            )
            raise RunExecutorError(
                (
                    "Robot handling required recovery and must be checked "
                    "manually: "
                    if handling_recovery
                    else "The physical cycle produced no valid measurement: "
                )
                + result.error,
                retryable=not handling_recovery,
                failed_stage=(
                    CycleStage.ROBOT_HANDLING.value
                    if handling_recovery
                    else "measurement_penalty"
                ),
                cycle_id=result.cycle_id,
            )

        try:
            ra_um = _measurement(result.measurements, "Ra")
            rz_um = _measurement(result.measurements, "Rz")
        except ValueError as error:
            raise RunExecutorError(
                f"Invalid physical measurement: {error}",
                retryable=True,
                failed_stage="result_validation",
                cycle_id=result.cycle_id,
            ) from error
        return ExecutionResult(
            ra_um=ra_um,
            rz_um=rz_um,
            cycle_id=result.cycle_id,
            print_time_seconds=result.print_time_seconds,
        )

    def _classified_cycle_error(
        self,
        error: CycleExecutionError,
    ) -> RunExecutorError:
        before_physical_attempt = error.stage in self.SAFE_REPEAT_STAGES
        comparable_failure = error.stage in self.COMPARABLE_FAILURE_STAGES
        retryable = before_physical_attempt or comparable_failure
        if before_physical_attempt:
            explanation = (
                "The failure occurred before a possible print start and may "
                "be retried explicitly with the saved parameters."
            )
        elif comparable_failure:
            explanation = (
                "This comparable process or measurement failure counts as "
                "one of at most two attempts with identical parameters."
            )
        else:
            explanation = (
                "The physical state may already have changed; automatic "
                "repetition is blocked until the plant is checked."
            )
        return RunExecutorError(
            f"{error} {explanation}",
            retryable=retryable,
            failed_stage=error.stage.value,
            consumes_attempt=not before_physical_attempt,
        )


def _print_parameters(
    raw_parameters: Mapping[str, int | float],
) -> PrintParameters:
    return PrintParameters(
        top_solid_layers=_integer_parameter(
            raw_parameters,
            "top_solid_layers",
        ),
        print_speed=_float_parameter(raw_parameters, "print_speed"),
        extrusion_width=_float_parameter(
            raw_parameters,
            "extrusion_width",
        ),
        extrusion_multiplier=_float_parameter(
            raw_parameters,
            "extrusion_multiplier",
        ),
        temperature=_integer_parameter(raw_parameters, "temperature"),
        fan_speed=_integer_parameter(raw_parameters, "fan_speed"),
    )


def _float_parameter(
    parameters: Mapping[str, int | float],
    name: str,
) -> float:
    value = float(parameters[name])
    if not math.isfinite(value):
        raise ValueError(f"Parameter {name!r} must be finite.")
    return value


def _integer_parameter(
    parameters: Mapping[str, int | float],
    name: str,
) -> int:
    value = _float_parameter(parameters, name)
    if not value.is_integer():
        raise ValueError(f"Parameter {name!r} must be an integer.")
    return int(value)


def _measurement(
    measurements: Mapping[str, float],
    name: str,
) -> float:
    raw_value = measurements.get(name)
    if isinstance(raw_value, bool):
        raise ValueError(f"Measurement {name!r} is missing or not numeric.")
    try:
        value = float(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Measurement {name!r} is missing or not numeric."
        ) from error
    if not math.isfinite(value):
        raise ValueError(f"Measurement {name!r} is not finite.")
    return value

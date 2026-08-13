from __future__ import annotations

import hashlib
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, ContextManager, Mapping, Protocol


LOGGER = logging.getLogger(__name__)


class SlicerServiceProtocol(Protocol):
    def is_available(self) -> bool: ...

    def send_stl_to_slicer(
        self,
        stl_file_path: Path,
        profile: Path,
        gcode_file_path: Path,
    ) -> bool: ...


class PrinterServiceProtocol(Protocol):
    def wait_until_connected(
        self,
        retries: int = 10,
        delay_seconds: float = 3,
    ) -> bool: ...

    def upload_gcode(
        self,
        gcode_file_path: Path,
        *,
        start_after_upload: bool = False,
    ) -> bool: ...

    def start_print_job(self) -> bool: ...

    def get_printer_state(self) -> str | None: ...


class RobotServiceProtocol(Protocol):
    def check_connection(self) -> None: ...

    def initialize(self) -> None: ...

    def prepare_part_for_measurement(self) -> None: ...

    def complete_part_handling_after_measurement(self) -> None: ...


class QualityStationProtocol(Protocol):
    def health(self) -> bool: ...

    def measure(self) -> dict[str, float]: ...

class CameraServiceProtocol(Protocol):
    def health(self) -> bool: ...

    def capture_still(
        self,
        cycle_id: str,
    ) -> str: ...

class CycleRecorderProtocol(Protocol):
    def record(self, result: "CycleResult") -> None: ...


class CycleStage(str, Enum):
    PREFLIGHT = "preflight"
    SLICING = "slicing"
    UPLOADING = "uploading"
    STARTING_PRINT = "starting_print"
    WAITING_FOR_PRINT = "waiting_for_print"
    CAMERA_CAPTURE = "camera_capture"
    COOLING = "cooling"
    ROBOT_HANDLING = "robot_handling"
    MEASURING = "measuring"
    RECORDING = "recording"
    COMPLETED = "completed"


class CycleStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class CycleExecutionError(RuntimeError):
    """Failure of one explicitly identified end-to-end cycle stage."""

    def __init__(self, stage: CycleStage, message: str) -> None:
        self.stage = stage
        super().__init__(f"Cycle failed during {stage.value}: {message}")


@dataclass(frozen=True)
class CycleRequest:
    stl_path: Path
    profile_path: Path
    gcode_path: Path
    print_parameters: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CycleResult:
    cycle_id: str
    mode: str
    status: CycleStatus
    stage: CycleStage
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    stl_path: Path
    profile_path: Path
    gcode_path: Path
    profile_sha256: str
    print_parameters: Mapping[str, str]
    measurements: Mapping[str, float] = field(default_factory=dict)
    printer_states: tuple[str, ...] = ()
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "mode": self.mode,
            "status": self.status.value,
            "stage": self.stage.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": round(self.duration_seconds, 3),
            "stl_path": str(self.stl_path),
            "profile_path": str(self.profile_path),
            "gcode_path": str(self.gcode_path),
            "profile_sha256": self.profile_sha256,
            "print_parameters": dict(self.print_parameters),
            "measurements": dict(self.measurements),
            "printer_states": list(self.printer_states),
            "error": self.error,
        }


RobotServiceFactory = Callable[
    [],
    ContextManager[RobotServiceProtocol],
]


class PrintOrchestrator:
    """
    Execute one bounded print, handling and measurement cycle.

    A failed stage aborts the cycle immediately, except for a failed QS
    measurement, which produces fixed penalty values so that robot handling
    and the experiment can continue. Measurement never starts after a robot
    error and the robot never starts before a newly started print was observed
    as active and subsequently finished.
    """

    ACTIVE_PRINT_STATES = frozenset({"PRINTING", "PAUSED"})
    FAILED_PRINT_STATES = frozenset({"STOPPED", "ERROR", "ATTENTION"})
    READY_PRINT_STATES = frozenset({"IDLE", "FINISHED"})
    REQUIRED_MEASUREMENTS = ("Ra", "Rz")
    MEASUREMENT_PENALTY_VALUE = 100.0

    def __init__(
        self,
        slicer_service: SlicerServiceProtocol,
        printer_service: PrinterServiceProtocol,
        robot_service_factory: RobotServiceFactory,
        quality_station: QualityStationProtocol,
        cycle_recorder: CycleRecorderProtocol,
        camera_service: CameraServiceProtocol | None = None,
        *,
        print_poll_interval_seconds: float = 15.0,
        print_start_timeout_seconds: float = 180.0,
        print_timeout_seconds: float = 8 * 60 * 60,
        max_consecutive_status_errors: int = 5,
        cooling_time_seconds: float = 0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if print_poll_interval_seconds < 0:
            raise ValueError("print_poll_interval_seconds must not be negative")
        if print_start_timeout_seconds <= 0:
            raise ValueError("print_start_timeout_seconds must be positive")
        if print_timeout_seconds <= 0:
            raise ValueError("print_timeout_seconds must be positive")
        if max_consecutive_status_errors <= 0:
            raise ValueError("max_consecutive_status_errors must be positive")
        if cooling_time_seconds < 0:
            raise ValueError("cooling_time_seconds must not be negative")

        self.slicer_service = slicer_service
        self.printer_service = printer_service
        self.robot_service_factory = robot_service_factory
        self.quality_station = quality_station
        self.cycle_recorder = cycle_recorder
        self.camera_service = camera_service

        self.print_poll_interval_seconds = print_poll_interval_seconds
        self.print_start_timeout_seconds = print_start_timeout_seconds
        self.print_timeout_seconds = print_timeout_seconds
        self.max_consecutive_status_errors = max_consecutive_status_errors
        self.cooling_time_seconds = cooling_time_seconds

        self._sleep = sleep
        self._monotonic = monotonic

    def run_preflight(
        self,
        request: CycleRequest,
        *,
        include_printer: bool = True,
    ) -> None:
        """Check files, QS and printer without starting or moving hardware."""
        self._validate_request_paths(request)

        if include_printer and not self.slicer_service.is_available():
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                "PrusaSlicer is missing or not executable.",
            )

        self._wait_for_quality_station_health()

        if (
            include_printer
            and self.camera_service is not None
        ):
            try:
                if not self.camera_service.health():
                    raise CycleExecutionError(
                        CycleStage.PREFLIGHT,
                        "Camera API is not healthy.",
                    )

            except CycleExecutionError:
                raise

            except Exception as error:
                raise CycleExecutionError(
                    CycleStage.PREFLIGHT,
                    (
                        "Camera health check failed: "
                        f"{error}"
                    ),
                ) from error

        try:
            with self.robot_service_factory() as robot_service:
                robot_service.check_connection()
        except Exception as error:
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                f"Robot connection check failed: {error}",
            ) from error

        if not include_printer:
            return

        if not self.printer_service.wait_until_connected():
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                "Printer is not connected.",
            )

        state = self.printer_service.get_printer_state()
        if state is None:
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                "Printer state could not be read.",
            )

        normalized_state = state.upper()
        if normalized_state not in self.READY_PRINT_STATES:
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                "Printer must be IDLE or FINISHED before a cycle, "
                f"but reported {normalized_state}.",
            )

    def run_single_print_cycle(self, request: CycleRequest) -> CycleResult:
        return self._run_cycle(
            request,
            mode="full",
            include_print=True,
        )

    def run_handling_and_measurement_cycle(
        self,
        request: CycleRequest,
    ) -> CycleResult:
        """
        Run only robot handling and QS measurement with an existing part.

        This is the hardware integration step before the first full cycle.
        """
        return self._run_cycle(
            request,
            mode="robot-qs",
            include_print=False,
        )

    def _run_cycle(
        self,
        request: CycleRequest,
        *,
        mode: str,
        include_print: bool,
    ) -> CycleResult:
        cycle_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)
        started_monotonic = self._monotonic()
        stage = CycleStage.PREFLIGHT
        profile_sha256 = ""
        printer_states: tuple[str, ...] = ()
        measurements: dict[str, float] = {}
        measurement_error: str | None = None

        LOGGER.info(
            "Starting %s cycle %s.",
            mode,
            cycle_id,
        )

        try:
            self.run_preflight(
                request,
                include_printer=include_print,
            )
            profile_sha256 = self._sha256_file(request.profile_path)

            if include_print:
                stage = CycleStage.SLICING
                LOGGER.info("Cycle %s: slicing STL.", cycle_id)
                if not self.slicer_service.send_stl_to_slicer(
                    request.stl_path,
                    request.profile_path,
                    request.gcode_path,
                ):
                    raise CycleExecutionError(
                        stage,
                        "PrusaSlicer did not create a valid G-code file.",
                    )

                stage = CycleStage.UPLOADING
                LOGGER.info("Cycle %s: uploading G-code.", cycle_id)
                if not self.printer_service.upload_gcode(
                    request.gcode_path,
                    start_after_upload=True,
                ):
                    raise CycleExecutionError(
                        stage,
                        "G-code upload with automatic print start failed.",
                    )

                stage = CycleStage.STARTING_PRINT
                LOGGER.info(
                    "Cycle %s: print start was requested atomically with "
                    "the upload.",
                    cycle_id,
                )

                stage = CycleStage.WAITING_FOR_PRINT
                printer_states = self.wait_until_print_finished()

                if self.camera_service is not None:
                    stage = CycleStage.CAMERA_CAPTURE

                    LOGGER.info(
                        "Cycle %s: capturing camera image "
                        "before handling.",
                        cycle_id,
                    )

                    filename = (
                        self.camera_service.capture_still(
                            cycle_id
                        )
                    )

                    LOGGER.info(
                        "Cycle %s: camera image saved as %s.",
                        cycle_id,
                        filename,
                    )

                stage = CycleStage.COOLING
                if self.cooling_time_seconds > 0:
                    LOGGER.info(
                        "Cycle %s: waiting %.1f seconds before handling.",
                        cycle_id,
                        self.cooling_time_seconds,
                    )
                    self._sleep(self.cooling_time_seconds)

            stage = CycleStage.ROBOT_HANDLING
            LOGGER.info("Cycle %s: starting robot handling.", cycle_id)
            with self.robot_service_factory() as robot_service:
                robot_service.initialize()
                robot_service.prepare_part_for_measurement()

                stage = CycleStage.MEASURING
                LOGGER.info(
                    "Cycle %s: part is under the probe; starting QS "
                    "measurement.",
                    cycle_id,
                )

                try:
                    measurements = self._validate_measurements(
                        self.quality_station.measure()
                    )

                except Exception as error:
                    measurement_error = (
                        "QS measurement failed; penalty values were used: "
                        f"{type(error).__name__}: {error}"
                    )

                    measurements = {
                        parameter: self.MEASUREMENT_PENALTY_VALUE
                        for parameter in self.REQUIRED_MEASUREMENTS
                    }

                    LOGGER.warning(
                        "Cycle %s: QS measurement failed. Saving "
                        "Ra=%.1f um and Rz=%.1f um as penalty values.",
                        cycle_id,
                        measurements["Ra"],
                        measurements["Rz"],
                        exc_info=True,
                    )

                    error_message = str(error)

                    reset_required = (
                        "HTTP 409" in error_message
                        and "CTSTA was accepted" in error_message
                        and "no measurement movement was detected"
                        in error_message
                    )

                    if reset_required:
                        LOGGER.warning(
                            "Cycle %s: starting one additional QS "
                            "measurement attempt to reset the SJ-220 "
                            "error state. The result will be ignored.",
                            cycle_id,
                        )

                        try:
                            self.quality_station.measure()

                        except Exception as reset_error:
                            LOGGER.info(
                                "Cycle %s: additional QS reset attempt "
                                "ended with %s: %s. The result is "
                                "intentionally ignored.",
                                cycle_id,
                                type(reset_error).__name__,
                                reset_error,
                            )

                        else:
                            LOGGER.info(
                                "Cycle %s: additional QS reset attempt "
                                "completed successfully. Its result is "
                                "intentionally ignored.",
                                cycle_id,
                            )

                    else:
                        LOGGER.info(
                            "Cycle %s: no automatic SJ-220 reset attempt "
                            "is required for this measurement error.",
                            cycle_id,
                        )

                else:
                    LOGGER.info(
                        "Cycle %s: QS measurement completed; Ra=%s um, "
                        "Rz=%s um.",
                        cycle_id,
                        measurements["Ra"],
                        measurements["Rz"],
                    )

                stage = CycleStage.ROBOT_HANDLING
                robot_service.complete_part_handling_after_measurement()

            finished_at = datetime.now(timezone.utc)
            result = CycleResult(
                cycle_id=cycle_id,
                mode=mode,
                status=CycleStatus.COMPLETED,
                stage=CycleStage.COMPLETED,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=self._monotonic() - started_monotonic,
                stl_path=request.stl_path,
                profile_path=request.profile_path,
                gcode_path=request.gcode_path,
                profile_sha256=profile_sha256,
                print_parameters=dict(request.print_parameters),
                measurements=measurements,
                printer_states=printer_states,
                error=measurement_error,
            )

            stage = CycleStage.RECORDING
            self.cycle_recorder.record(result)

            if measurement_error is None:
                LOGGER.info(
                    "Cycle %s completed: Ra=%s um, Rz=%s um.",
                    cycle_id,
                    measurements["Ra"],
                    measurements["Rz"],
                )
            else:
                LOGGER.warning(
                    "Cycle %s completed with measurement penalty: "
                    "Ra=%s um, Rz=%s um.",
                    cycle_id,
                    measurements["Ra"],
                    measurements["Rz"],
                )
            return result

        except Exception as error:
            failure = (
                error
                if isinstance(error, CycleExecutionError)
                else CycleExecutionError(stage, str(error))
            )
            finished_at = datetime.now(timezone.utc)
            failed_result = CycleResult(
                cycle_id=cycle_id,
                mode=mode,
                status=CycleStatus.FAILED,
                stage=failure.stage,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=self._monotonic() - started_monotonic,
                stl_path=request.stl_path,
                profile_path=request.profile_path,
                gcode_path=request.gcode_path,
                profile_sha256=profile_sha256,
                print_parameters=dict(request.print_parameters),
                measurements=measurements,
                printer_states=printer_states,
                error=str(failure),
            )

            try:
                self.cycle_recorder.record(failed_result)
            except Exception:
                LOGGER.exception(
                    "Could not record failed cycle %s.",
                    cycle_id,
                )

            LOGGER.exception("Cycle %s aborted.", cycle_id)

            if failure is error:
                raise
            raise failure from error

    def wait_until_print_finished(self) -> tuple[str, ...]:
        """
        Wait for the newly started print to become active and then finish.

        Requiring an observed active state prevents a stale FINISHED state
        from the previous print from starting the robot prematurely.
        """
        wait_started = self._monotonic()
        start_deadline = wait_started + self.print_start_timeout_seconds
        finish_deadline = wait_started + self.print_timeout_seconds

        active_print_observed = False
        consecutive_status_errors = 0
        observed_states: list[str] = []

        while self._monotonic() <= finish_deadline:
            state = self.printer_service.get_printer_state()

            if state is None:
                consecutive_status_errors += 1
                LOGGER.warning(
                    "Printer state unavailable (%s/%s).",
                    consecutive_status_errors,
                    self.max_consecutive_status_errors,
                )

                if (
                    consecutive_status_errors
                    >= self.max_consecutive_status_errors
                ):
                    raise CycleExecutionError(
                        CycleStage.WAITING_FOR_PRINT,
                        "Printer status was unavailable too many times.",
                    )
            else:
                consecutive_status_errors = 0
                normalized_state = state.upper()

                if (
                    not observed_states
                    or observed_states[-1] != normalized_state
                ):
                    observed_states.append(normalized_state)
                    LOGGER.info(
                        "Printer state changed to %s.",
                        normalized_state,
                    )

                if normalized_state in self.ACTIVE_PRINT_STATES:
                    active_print_observed = True

                if normalized_state == "FINISHED":
                    if active_print_observed:
                        return tuple(observed_states)

                    LOGGER.info(
                        "Ignoring FINISHED until the new print is active."
                    )

                if normalized_state in self.FAILED_PRINT_STATES:
                    raise CycleExecutionError(
                        CycleStage.WAITING_FOR_PRINT,
                        f"Printer reported {normalized_state}.",
                    )

            if (
                not active_print_observed
                and self._monotonic() > start_deadline
            ):
                raise CycleExecutionError(
                    CycleStage.WAITING_FOR_PRINT,
                    "The printer never entered PRINTING or PAUSED after "
                    "the start command.",
                )

            self._sleep(self.print_poll_interval_seconds)

        raise CycleExecutionError(
            CycleStage.WAITING_FOR_PRINT,
            "Maximum print duration exceeded.",
        )

    @staticmethod
    def _validate_request_paths(request: CycleRequest) -> None:
        if not request.stl_path.is_file():
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                f"STL file not found: {request.stl_path}",
            )

        if not request.profile_path.is_file():
            raise CycleExecutionError(
                CycleStage.PREFLIGHT,
                f"Slicer profile not found: {request.profile_path}",
            )

        request.gcode_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    @classmethod
    def _validate_measurements(
        cls,
        measurements: Mapping[str, object],
    ) -> dict[str, float]:
        validated: dict[str, float] = {}

        for parameter in cls.REQUIRED_MEASUREMENTS:
            raw_value = measurements.get(parameter)
            if isinstance(raw_value, bool):
                raw_value = None

            try:
                value = float(raw_value)  # type: ignore[arg-type]
            except (TypeError, ValueError) as error:
                raise CycleExecutionError(
                    CycleStage.MEASURING,
                    f"QS result {parameter!r} is missing or not numeric.",
                ) from error

            if not math.isfinite(value):
                raise CycleExecutionError(
                    CycleStage.MEASURING,
                    f"QS result {parameter!r} is not finite.",
                )

            validated[parameter] = value

        return validated

    def _wait_for_quality_station_health(
    self,
    *,
    timeout_seconds: float = 300.0,
    retry_interval_seconds: float = 10.0,
    ) -> None:
        """Wait for the quality-station API to become healthy."""
        deadline = time.monotonic() + timeout_seconds
        attempts = 0
        last_failure = "Quality-station API reported an unhealthy state."
        last_exception: Exception | None = None

        while True:
            attempts += 1

            try:
                if self.quality_station.health():
                    return

                last_failure = (
                    "Quality-station API reported an unhealthy state."
                )
                last_exception = None

            except Exception as error:
                last_exception = error
                last_failure = f"{type(error).__name__}: {error}"

            remaining_seconds = deadline - time.monotonic()

            if remaining_seconds <= 0:
                break

            time.sleep(
                min(retry_interval_seconds, remaining_seconds)
            )

        cycle_error = CycleExecutionError(
            CycleStage.PREFLIGHT,
            "Quality-station did not become healthy within "
            f"{timeout_seconds:.0f} seconds after {attempts} attempts. "
            f"Last failure: {last_failure}",
        )

        if last_exception is not None:
            raise cycle_error from last_exception

        raise cycle_error

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
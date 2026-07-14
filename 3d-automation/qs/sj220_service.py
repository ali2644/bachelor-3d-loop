from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Iterable

import serial

from qs.sj220_exceptions import (
    SJ220ConnectionError,
    SJ220DeviceError,
    SJ220ProtocolError,
    SJ220ResultError,
    SJ220StateError,
    SJ220TimeoutError,
)
from qs.sj220_models import (
    MeasurementReport,
    MeasurementResult,
    SJ220Status,
)


LOGGER = logging.getLogger(__name__)

ERROR_RESPONSE_PATTERN = re.compile(
    r"NG(?P<code>\d{3})(?:,(?P<position>\d{2}))?"
)


class SJ220Service:
    """Controls a Mitutoyo SJ-220 via its RS-232C protocol."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 38400,
        read_timeout_seconds: float = 3.0,
        write_timeout_seconds: float = 3.0,
        measurement_timeout_seconds: float = 60.0,
        measurement_start_timeout_seconds: float = 30.0,
        poll_interval_seconds: float = 0.25,
        transient_retry_count: int = 5,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._read_timeout_seconds = read_timeout_seconds
        self._write_timeout_seconds = write_timeout_seconds
        self._measurement_timeout_seconds = measurement_timeout_seconds
        self._measurement_start_timeout_seconds = (
            measurement_start_timeout_seconds
        )
        self._poll_interval_seconds = poll_interval_seconds
        self._transient_retry_count = transient_retry_count

        self._serial: serial.Serial | None = None
        self._io_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return (
            self._serial is not None
            and self._serial.is_open
        )

    def connect(self) -> None:
        """Open the serial connection."""

        if self.is_connected:
            return

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._read_timeout_seconds,
                write_timeout=self._write_timeout_seconds,
                rtscts=True,
                dsrdtr=False,
                xonxoff=False,
            )

            # Clear old bytes only once when opening the connection.
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()

        except (serial.SerialException, OSError) as error:
            self._serial = None

            raise SJ220ConnectionError(
                f"Could not open SJ-220 serial port "
                f"{self._port!r}: {error}"
            ) from error

        LOGGER.info(
            "Connected to SJ-220 on %s with %s baud, 8N1.",
            self._port,
            self._baudrate,
        )

    def close(self) -> None:
        """Close the serial connection."""

        if self._serial is None:
            return

        try:
            if self._serial.is_open:
                self._serial.close()
        except serial.SerialException as error:
            raise SJ220ConnectionError(
                f"Could not close SJ-220 connection: {error}"
            ) from error
        finally:
            self._serial = None

        LOGGER.info("SJ-220 connection closed.")

    def __enter__(self) -> SJ220Service:
        self.connect()
        return self

    def __exit__(
        self,
        exception_type: object,
        exception_value: object,
        traceback: object,
    ) -> None:
        self.close()

    def _get_serial(self) -> serial.Serial:
        if self._serial is None or not self._serial.is_open:
            raise SJ220ConnectionError(
                "SJ-220 is not connected. Call connect() first."
            )

        return self._serial

    def _send_command(self, command: str) -> str:
        """
        Send one command and return the payload after the OK header.

        Examples:
            OK000 -> "000"
            OK02  -> "02"
            OK    -> ""
            NG007 -> raises SJ220DeviceError
        """

        if not command:
            raise ValueError("Command must not be empty.")

        if "\r" in command or "\n" in command:
            raise ValueError(
                "Command must not contain CR or LF characters."
            )

        try:
            encoded_command = f"{command}\r".encode("ascii")
        except UnicodeEncodeError as error:
            raise SJ220ProtocolError(
                f"Command contains non-ASCII characters: {command!r}"
            ) from error

        ser = self._get_serial()

        with self._io_lock:
            try:
                written_bytes = ser.write(encoded_command)

                if written_bytes != len(encoded_command):
                    raise SJ220ConnectionError(
                        f"Only {written_bytes} of "
                        f"{len(encoded_command)} bytes were written."
                    )

                ser.flush()
                raw_response = ser.read_until(b"\r")

            except serial.SerialTimeoutException as error:
                raise SJ220TimeoutError(
                    f"Write timeout for command {command!r}."
                ) from error

            except serial.SerialException as error:
                raise SJ220ConnectionError(
                    f"Serial communication failed for "
                    f"command {command!r}: {error}"
                ) from error

        LOGGER.debug(
            "TX ASCII=%r HEX=%s",
            encoded_command,
            encoded_command.hex(" ").upper(),
        )
        LOGGER.debug(
            "RX ASCII=%r HEX=%s",
            raw_response,
            raw_response.hex(" ").upper(),
        )

        if not raw_response:
            raise SJ220TimeoutError(
                f"No response from SJ-220 for command {command!r}."
            )

        if not raw_response.endswith(b"\r"):
            raise SJ220TimeoutError(
                f"Incomplete response for command {command!r}: "
                f"{raw_response!r}"
            )

        try:
            response = raw_response[:-1].decode("ascii")
        except UnicodeDecodeError as error:
            raise SJ220ProtocolError(
                f"Response contains invalid non-ASCII bytes: "
                f"{raw_response!r}"
            ) from error

        if response.startswith("OK"):
            return response[2:]

        error_match = ERROR_RESPONSE_PATTERN.fullmatch(response)

        if error_match is not None:
            raise SJ220DeviceError(
                code=error_match.group("code"),
                command=command,
                response=response,
                error_position=error_match.group("position"),
            )

        raise SJ220ProtocolError(
            f"Unexpected SJ-220 response for command "
            f"{command!r}: {response!r}"
        )

    def _send_read_command(self, command: str) -> str:
        """
        Send an idempotent read command.

        NG011 and NG033 are temporary states and may safely be retried.
        """

        for attempt in range(1, self._transient_retry_count + 1):
            try:
                return self._send_command(command)

            except SJ220DeviceError as error:
                if error.code not in {"011", "033"}:
                    raise

                if attempt == self._transient_retry_count:
                    raise

                LOGGER.warning(
                    "SJ-220 is busy for command %s "
                    "(error %s, attempt %s/%s).",
                    command,
                    error.code,
                    attempt,
                    self._transient_retry_count,
                )

                time.sleep(self._poll_interval_seconds)

        raise AssertionError("Unreachable retry state.")

    def get_status(self) -> SJ220Status:
        """Read the current detector/measurement status."""

        payload = self._send_read_command("RDSTU00")

        try:
            return SJ220Status(payload)
        except ValueError as error:
            raise SJ220ProtocolError(
                f"Unknown status returned by SJ-220: {payload!r}"
            ) from error

    def get_detector_position(self) -> float:
        """Read the current detector position using RDPSA."""

        payload = self._send_read_command("RDPSA")

        try:
            return float(payload)
        except ValueError as error:
            raise SJ220ProtocolError(
                f"Invalid detector position: {payload!r}"
            ) from error

    def start_measurement(self) -> None:
        """Start one measurement."""

        status = self.get_status()

        if status is not SJ220Status.IDLE:
            raise SJ220StateError(
                "Measurement cannot be started because the SJ-220 "
                f"is not idle. Current status: "
                f"{status.value} – {status.description}."
            )

        # CTSTA triggers a physical movement.
        # It must not automatically be sent multiple times.
        response_payload = self._send_command("CTSTA")

        if response_payload:
            raise SJ220ProtocolError(
                f"Unexpected CTSTA response payload: "
                f"{response_payload!r}"
            )

        LOGGER.info("SJ-220 measurement started.")

    def wait_until_measurement_finished(self) -> None:
        """
        Wait until the measurement movement has completed.

        RDSTU00 status 005 is a valid transitional status. It is not
        treated as an error because the detector may briefly be located
        between its defined end positions after a measurement.
        """

        started_at = time.monotonic()

        overall_deadline = (
            started_at + self._measurement_timeout_seconds
        )

        start_deadline = (
            started_at + self._measurement_start_timeout_seconds
        )

        measurement_became_active = False
        previous_status: SJ220Status | None = None

        while time.monotonic() < overall_deadline:
            status = self.get_status()

            if status != previous_status:
                LOGGER.info(
                    "SJ-220 status: %s – %s",
                    status.value,
                    status.description,
                )
                previous_status = status

            if status == SJ220Status.MEASURING:
                measurement_became_active = True

            elif status in {
                SJ220Status.RETURNING,
                SJ220Status.RETRACTING,
                SJ220Status.INTERMEDIATE_POSITION,
            }:
                # These are valid states during or after detector movement.
                if measurement_became_active:
                    LOGGER.debug(
                        "Waiting for detector to reach its final position."
                    )

            elif status == SJ220Status.IDLE:
                if measurement_became_active:
                    LOGGER.info(
                        "SJ-220 measurement movement completed."
                    )
                    return

                if time.monotonic() >= start_deadline:
                    raise SJ220StateError(
                        "CTSTA was accepted, but no measurement movement "
                        f"was detected within "
                        f"{self._measurement_start_timeout_seconds} seconds."
                    )

            elif status == SJ220Status.RETRACTED:
                if measurement_became_active:
                    LOGGER.info(
                        "SJ-220 measurement completed with "
                        "the detector retracted."
                    )
                    return

                raise SJ220StateError(
                    "Detector was already retracted before "
                    "the measurement became active."
                )

            time.sleep(self._poll_interval_seconds)

        last_status_text = (
            f"{previous_status.value} – {previous_status.description}"
            if previous_status is not None
            else "unknown"
        )

        raise SJ220TimeoutError(
            "Measurement did not reach a completed state within "
            f"{self._measurement_timeout_seconds} seconds. "
            f"Last status: {last_status_text}."
        )

    def get_parameter_count(self) -> int:
        """Read the number of configured result parameters."""

        payload = self._send_read_command("RDPAR")

        if not re.fullmatch(r"\d{2}", payload):
            raise SJ220ProtocolError(
                f"Invalid RDPAR response: {payload!r}"
            )

        parameter_count = int(payload)

        if parameter_count <= 0:
            raise SJ220ResultError(
                "No result parameters are configured on the SJ-220."
            )

        return parameter_count

    def read_result(
        self,
        parameter_number: int,
        sampling_length_number: int = 0,
    ) -> MeasurementResult:
        """Read one configured calculation result."""

        if not 1 <= parameter_number <= 99:
            raise ValueError(
                "parameter_number must be between 1 and 99."
            )

        if not 0 <= sampling_length_number <= 99:
            raise ValueError(
                "sampling_length_number must be between 0 and 99."
            )

        command = (
            f"RDRES02,"
            f"{parameter_number:02d},"
            f"{sampling_length_number:02d}"
        )

        payload = self._send_read_command(command)

        # RDRES02 payload:
        # 6 characters parameter name
        # 7 characters value
        # 3 characters unit
        if len(payload) != 16:
            raise SJ220ProtocolError(
                f"RDRES02 returned {len(payload)} characters instead "
                f"of 16: {payload!r}"
            )

        parameter = payload[0:6].strip()
        raw_value = payload[6:13].strip()
        unit = payload[13:16].strip()

        if not parameter:
            raise SJ220ProtocolError(
                f"Missing parameter name in payload: {payload!r}"
            )

        if not raw_value:
            raise SJ220ResultError(
                f"Missing value for parameter {parameter!r}."
            )

        try:
            value = float(raw_value.replace(",", "."))
        except ValueError as error:
            raise SJ220ProtocolError(
                f"Invalid numeric result {raw_value!r} "
                f"for parameter {parameter!r}."
            ) from error

        return MeasurementResult(
            parameter=parameter,
            value=value,
            unit=unit,
            raw_value=raw_value,
            parameter_number=parameter_number,
        )

    def read_all_results(self) -> tuple[MeasurementResult, ...]:
        """Read every configured result parameter."""

        parameter_count = self.get_parameter_count()
        results: list[MeasurementResult] = []

        # SJ-220 customized parameters start at 01, not 00.
        for parameter_number in range(1, parameter_count + 1):
            result = self.read_result(parameter_number)
            results.append(result)

        return tuple(results)

    def measure(
        self,
        required_parameters: Iterable[str] = ("Ra", "Rz"),
    ) -> MeasurementReport:
        """
        Run a complete measurement cycle.

        1. Check status
        2. Start measurement
        3. Wait for completion
        4. Read every configured result
        5. Verify required parameters
        """

        started_at = time.monotonic()

        self.start_measurement()
        self.wait_until_measurement_finished()

        results = self.read_all_results()

        available_parameters = {
            result.parameter
            for result in results
        }

        missing_parameters = (
            set(required_parameters) - available_parameters
        )

        if missing_parameters:
            raise SJ220ResultError(
                "Measurement completed, but required parameters "
                f"are missing: {sorted(missing_parameters)}. "
                f"Available parameters: "
                f"{sorted(available_parameters)}."
            )

        duration_seconds = time.monotonic() - started_at

        return MeasurementReport(
            results=results,
            duration_seconds=duration_seconds,
        )
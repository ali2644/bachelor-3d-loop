from dataclasses import dataclass
import re
import time

import serial


SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE = 38400
MEASUREMENT_TIMEOUT_SECONDS = 60


ERROR_MESSAGES = {
    "003": "Origin position was not reached in time.",
    "004": "Retraction position was not reached in time.",
    "005": "Origin limit remains active.",
    "006": "Retraction limit remains active.",
    "007": "Detector over-range.",
    "011": "Command sent while the device is busy.",
    "012": "Control timeout.",
    "013": "Communication buffer overflow.",
    "014": "Flash memory erase error.",
    "015": "Flash memory write error.",
    "016": "Program error.",
    "017": "System error.",
    "018": "Invalid measurement start position.",
    "019": "Invalid setting value.",
    "022": "Detector disconnected.",
    "030": "Illegal command.",
    "031": "Invalid command format.",
    "032": "Invalid command value.",
    "033": "Command is still being processed.",
    "071": "SPC communication error.",
    "101": "No calculation results available.",
    "102": "Calculated result is out of range.",
    "103": "Measurement interrupted because of result over-range.",
    "110": "Insufficient number of peaks and valleys.",
    "111": "Rz cannot be calculated: insufficient peaks and valleys.",
    "112": "Insufficient data points.",
    "113": "Invalid calculation region.",
    "114": "No profile element.",
    "115": "BAC/ADC calculation failed due to insufficient peaks and valleys.",
    "116": "Rk calculation failed.",
    "117": "R-Motif calculation failed: fewer than two valid local peaks.",
    "118": "R-Motif exceeds upper limit length A.",
    "121": "W-Motif calculation failed: fewer than three motifs.",
    "130": "Other calculation error.",
}


class SJ220Error(RuntimeError):
    """Base exception for errors related to the SJ-220."""


class SJ220DeviceError(SJ220Error):
    """Error reported directly by the SJ-220."""

    def __init__(
        self,
        code: str,
        command: str,
        error_byte: str | None = None,
    ):
        self.code = code
        self.command = command
        self.error_byte = error_byte

        description = ERROR_MESSAGES.get(
            code,
            "Unknown SJ-220 error.",
        )

        details = f"SJ-220 error {code}: {description}"

        if error_byte is not None:
            details += f" Error position/byte: {error_byte}."

        details += f" Command: {command}"

        super().__init__(details)


class SJ220ProtocolError(SJ220Error):
    """Unexpected or malformed response from the SJ-220."""


@dataclass(frozen=True)
class MeasurementResult:
    parameter: str
    value: float
    unit: str
    raw_value: str


def send_command(
    ser: serial.Serial,
    command: str,
) -> str:
    payload = f"{command}\r".encode("ascii")

    # Nicht vor jedem Befehl resetten.
    ser.write(payload)
    ser.flush()

    raw_response = ser.read_until(b"\r")

    print(f"TX: {payload!r}")
    print(f"RX: {raw_response!r}")
    print(f"RX HEX: {raw_response.hex(' ').upper()}")

    if not raw_response:
        raise TimeoutError(
            f"No response from SJ-220 for command: {command}"
        )

    response = raw_response.decode(
        "latin-1",
        errors="replace",
    ).rstrip("\r")

    if response.startswith("OK"):
        return response[2:]

    error_match = re.fullmatch(
        r"NG(\d{3})(?:,(\d{2}))?",
        response,
    )

    if error_match:
        raise SJ220DeviceError(
            code=error_match.group(1),
            command=command,
            error_byte=error_match.group(2),
        )

    raise SJ220ProtocolError(
        f"Unexpected response for {command}: {response!r}"
    )

def read_status(ser: serial.Serial) -> str:
    status = send_command(ser, "RDSTU00")

    status_messages = {
        "000": "Idle / ready",
        "001": "Measurement in progress",
        "002": "Detector returning",
        "003": "Detector retracting",
        "004": "Detector retracted",
        "005": "Detector outside the normal origin state",
    }

    description = status_messages.get(
        status,
        "Unknown status",
    )

    print(f"Status: {status} – {description}")
    print("-" * 50)

    return status


def wait_for_measurement_completion(
    ser: serial.Serial,
) -> None:
    initial_status = read_status(ser)

    if initial_status != "000":
        raise SJ220Error(
            f"SJ-220 is not ready before measurement. "
            f"Current status: {initial_status}"
        )

    print("Starting measurement...")
    send_command(ser, "CTSTA")

    deadline = time.monotonic() + MEASUREMENT_TIMEOUT_SECONDS
    measurement_was_active = False

    while time.monotonic() < deadline:
        time.sleep(0.5)

        status = read_status(ser)

        if status in {"001", "002"}:
            measurement_was_active = True
            continue

        if status == "000":
            if measurement_was_active:
                print("Movement completed.")
                return

            # Avoid treating an immediate idle response as a completed
            # measurement before the device has actually started.
            continue

        if status in {"003", "004", "005"}:
            raise SJ220Error(
                f"Unexpected detector status during measurement: {status}"
            )

    raise TimeoutError(
        f"Measurement did not finish within "
        f"{MEASUREMENT_TIMEOUT_SECONDS} seconds."
    )


def read_parameter_count(
    ser: serial.Serial,
) -> int:
    payload = send_command(ser, "RDPAR")

    if not re.fullmatch(r"\d{2}", payload):
        raise SJ220ProtocolError(
            f"Invalid RDPAR response payload: {payload!r}"
        )

    parameter_count = int(payload)

    if parameter_count <= 0:
        raise SJ220Error(
            "The SJ-220 reports that no parameters are configured."
        )

    print(f"Configured parameters: {parameter_count}")
    print("-" * 50)

    return parameter_count


def parse_result_payload(
    payload: str,
) -> MeasurementResult:
    """
    RDRES02 returns fixed-width fields:

    - parameter name: 6 characters
    - result:         7 characters
    - unit:           3 characters
    """
    expected_length = 16

    if len(payload) < expected_length:
        raise SJ220ProtocolError(
            "Measurement response is too short. "
            f"Expected at least {expected_length} characters, "
            f"received {len(payload)}: {payload!r}"
        )

    parameter = payload[0:6].strip()
    raw_value = payload[6:13].strip()
    unit = payload[13:16].strip()

    if not parameter:
        raise SJ220ProtocolError(
            f"Parameter name is missing: {payload!r}"
        )

    try:
        value = float(raw_value.replace(",", "."))
    except ValueError as error:
        raise SJ220ProtocolError(
            f"Measurement value is not numeric: "
            f"{raw_value!r}, full payload: {payload!r}"
        ) from error

    return MeasurementResult(
        parameter=parameter,
        value=value,
        unit=unit,
        raw_value=raw_value,
    )
RESULT_TIMEOUT_SECONDS = 10
RESULT_RETRY_INTERVAL_SECONDS = 0.25


def read_result_with_retry(
    ser: serial.Serial,
    parameter_index: int,
) -> MeasurementResult:
    command = f"RDRES02,{parameter_index:02d},00"
    deadline = time.monotonic() + RESULT_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            payload = send_command(ser, command)
            return parse_result_payload(payload)

        except SJ220DeviceError as error:
            # 101: Noch keine Berechnungsergebnisse vorhanden.
            # 033: Befehl wird noch verarbeitet.
            if error.code in {"101", "033"}:
                print(
                    f"Result not ready yet "
                    f"(SJ-220 error {error.code}). Retrying..."
                )
                time.sleep(RESULT_RETRY_INTERVAL_SECONDS)
                continue

            # Overrange und andere echte Messfehler sofort melden.
            raise

    raise TimeoutError(
        f"No calculation result became available within "
        f"{RESULT_TIMEOUT_SECONDS} seconds for parameter "
        f"{parameter_index}."
    )

def read_all_results(
    ser: serial.Serial,
) -> list[MeasurementResult]:
    parameter_count = read_parameter_count(ser)
    results: list[MeasurementResult] = []

    print("Reading calculation results...")

    # SJ-220 parameter numbering starts at 01, not 00.
    for parameter_number in range(1, parameter_count + 1):
        result = read_result_with_retry(
            ser,
            parameter_number,
        )

        results.append(result)

        print(
            f"Parameter {parameter_number:02d}: "
            f"{result.parameter} = "
            f"{result.value} {result.unit}"
        )
        print("-" * 50)

    return results


def print_required_results(
    results: list[MeasurementResult],
) -> None:
    results_by_name = {
        result.parameter.strip(): result
        for result in results
    }

    print("\nMeasurement results")
    print("=" * 50)

    for result in results:
        print(
            f"{result.parameter}: "
            f"{result.value} {result.unit}"
        )

    print("=" * 50)

    ra = results_by_name.get("Ra")
    rz = results_by_name.get("Rz")

    if ra is None:
        print("Warning: Ra is not configured on the SJ-220.")
    else:
        print(f"Ra = {ra.value} {ra.unit}")

    if rz is None:
        print("Warning: Rz is not configured on the SJ-220.")
    else:
        print(f"Rz = {rz.value} {rz.unit}")


def main() -> None:
    try:
        with serial.Serial(
        port=SERIAL_PORT,
        baudrate=38400,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=3,
        write_timeout=3,
        rtscts=True,
        dsrdtr=False,
        xonxoff=False,
        ) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            wait_for_measurement_completion(ser)

            print("\nReading measurement results...")
            results = read_all_results(ser)

            print_required_results(results)

    except SJ220DeviceError as error:
        print("\nMEASUREMENT FAILED")
        print("=" * 50)
        print(error)

        if error.code in {"007", "102", "103"}:
            print(
                "Check the detector position, the workpiece alignment "
                "and the configured measurement range."
            )

    except SJ220ProtocolError as error:
        print("\nPROTOCOL ERROR")
        print(error)

    except TimeoutError as error:
        print("\nTIMEOUT")
        print(error)

    except serial.SerialException as error:
        print("\nSERIAL CONNECTION ERROR")
        print(error)

    except KeyboardInterrupt:
        print("\nProgram stopped by user.")


if __name__ == "__main__":
    main()
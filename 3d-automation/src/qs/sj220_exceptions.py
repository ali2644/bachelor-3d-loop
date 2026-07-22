from __future__ import annotations


ERROR_MESSAGES: dict[str, str] = {
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
    "111": "Rz cannot be calculated because there are too few peaks and valleys.",
    "112": "Insufficient data points.",
    "113": "Invalid calculation region.",
    "114": "No profile element available.",
    "115": "BAC/ADC calculation failed.",
    "116": "Rk calculation failed.",
    "117": "R-Motif calculation failed.",
    "118": "R-Motif exceeds upper limit length A.",
    "121": "W-Motif calculation failed.",
    "130": "Other calculation error.",
    "184": "Printer access timeout.",
}


class SJ220Error(RuntimeError):
    """Base class for all SJ-220 errors."""


class SJ220ConnectionError(SJ220Error):
    """The serial connection could not be opened or was interrupted."""


class SJ220TimeoutError(SJ220Error):
    """The SJ-220 did not answer within the configured timeout."""


class SJ220ProtocolError(SJ220Error):
    """The SJ-220 returned a malformed or unexpected response."""


class SJ220StateError(SJ220Error):
    """The SJ-220 is in a state in which the operation cannot be performed."""


class SJ220ResultError(SJ220Error):
    """Measurement results are missing or inconsistent."""

class SJ220PortInUseError(SJ220ConnectionError):
    """The SJ-220 serial port is already used by another process."""

class SJ220DeviceError(SJ220Error):
    """An NG error returned directly by the SJ-220."""

    def __init__(
        self,
        code: str,
        command: str,
        response: str,
        error_position: str | None = None,
    ) -> None:
        self.code = code
        self.command = command
        self.response = response
        self.error_position = error_position

        description = ERROR_MESSAGES.get(
            code,
            "Unknown error reported by the SJ-220.",
        )

        message = (
            f"SJ-220 error {code}: {description} "
            f"Command: {command!r}. Response: {response!r}."
        )

        if error_position is not None:
            message += f" Error position: {error_position}."

        super().__init__(message)
from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import quote

import requests


LOGGER = logging.getLogger(__name__)


class PrusaLinkService:
    """Small timeout-bounded client for the PrusaLink endpoints in use."""

    def __init__(
        self,
        printer_ip: str,
        api_key: str,
        *,
        remote_gcode_path: str = "FOLDER/new_model_2707.gcode",
        request_timeout_seconds: float = 10.0,
        upload_timeout_seconds: float = 5 * 60,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = f"http://{printer_ip}".rstrip("/")
        self.remote_gcode_path = remote_gcode_path.lstrip("/")
        self.request_timeout_seconds = request_timeout_seconds
        self.upload_timeout_seconds = upload_timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})
        self._last_remote_gcode_path: str | None = None

    @property
    def _remote_file_url(self) -> str:
        remote_path = (
            self._last_remote_gcode_path
            or self.remote_gcode_path
        )
        return self._remote_file_url_for(remote_path)

    def _remote_file_url_for(self, remote_path: str) -> str:
        remote_path = quote(
            remote_path,
            safe="/",
        )
        return f"{self.base_url}/api/v1/files/usb/{remote_path}"

    def _remote_path_for(self, gcode_path: Path) -> str:
        if self.remote_gcode_path.endswith("/"):
            return f"{self.remote_gcode_path}{gcode_path.name}"
        return self.remote_gcode_path

    def is_connected(self) -> bool:
        try:
            response = self.session.get(
                f"{self.base_url}/api/printer",
                timeout=self.request_timeout_seconds,
            )
            return response.status_code == 200
        except requests.RequestException as error:
            LOGGER.warning("Printer connection check failed: %s", error)
            return False

    def upload_gcode(
        self,
        gcode_file_path: str | Path,
        *,
        start_after_upload: bool = False,
    ) -> bool:
        gcode_path = Path(gcode_file_path)
        if not gcode_path.is_file() or gcode_path.stat().st_size == 0:
            LOGGER.error(
                "G-code file is missing or empty: %s",
                gcode_path,
            )
            return False

        remote_path = self._remote_path_for(gcode_path)
        remote_file_url = self._remote_file_url_for(remote_path)

        try:
            with gcode_path.open("rb") as stream:
                response = self.session.put(
                    remote_file_url,
                    data=stream,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Overwrite": "?1",
                        "Print-After-Upload": (
                            "?1" if start_after_upload else "?0"
                        ),
                    },
                    timeout=(
                        self.request_timeout_seconds,
                        self.upload_timeout_seconds,
                    ),
                )
        except (OSError, requests.RequestException) as error:
            LOGGER.error("G-code upload failed: %s", error)
            return False

        if response.status_code not in {200, 201, 204}:
            LOGGER.error(
                "G-code upload returned HTTP %s: %s",
                response.status_code,
                response.text,
            )
            return False

        self._last_remote_gcode_path = remote_path
        LOGGER.info(
            "G-code uploaded to %s%s.",
            remote_path,
            " with automatic print start" if start_after_upload else "",
        )

        if start_after_upload:
            # The following printer-state polling verifies that the print
            # really starts. Avoid a separate POST here: on the MINI the
            # upload can open the LCD preview before that second request,
            # leaving the printer waiting for manual confirmation.
            return True

        return self._wait_until_remote_file_available()

    def start_print_job(self) -> bool:
        try:
            response = self.session.post(
                self._remote_file_url,
                timeout=self.request_timeout_seconds,
            )
        except requests.RequestException as error:
            LOGGER.error(
                "Print start request failed. Its final state is unknown: %s",
                error,
            )
            return False

        if response.status_code not in {200, 201, 204}:
            LOGGER.error(
                "Print start returned HTTP %s: %s",
                response.status_code,
                response.text,
            )
            return False

        return True

    def get_status(self) -> dict[str, object] | None:
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/status",
                timeout=self.request_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            LOGGER.warning("Could not read printer status: %s", error)
            return None

        if not isinstance(data, dict):
            LOGGER.warning("Printer returned a non-object status payload.")
            return None

        return data

    def get_printer_state(self) -> str | None:
        status = self.get_status()
        if status is None:
            return None

        printer = status.get("printer")
        if not isinstance(printer, dict):
            return None

        state = printer.get("state")
        if not isinstance(state, str):
            return None

        return state.upper()

    def wait_until_connected(
        self,
        retries: int = 10,
        delay_seconds: float = 3,
    ) -> bool:
        for attempt in range(1, retries + 1):
            if self.is_connected():
                LOGGER.info("Connected to the printer.")
                return True

            LOGGER.warning(
                "Printer connection attempt %s/%s failed.",
                attempt,
                retries,
            )
            if attempt < retries:
                time.sleep(delay_seconds)

        return False

    def _wait_until_remote_file_available(
        self,
        *,
        retries: int = 10,
        delay_seconds: float = 1.0,
    ) -> bool:
        for attempt in range(1, retries + 1):
            try:
                response = self.session.head(
                    self._remote_file_url,
                    timeout=self.request_timeout_seconds,
                )
                if response.status_code == 200:
                    return True
            except requests.RequestException as error:
                LOGGER.warning(
                    "Remote-file check %s/%s failed: %s",
                    attempt,
                    retries,
                    error,
                )

            if attempt < retries:
                time.sleep(delay_seconds)

        LOGGER.error(
            "Uploaded file did not become available at %s.",
            self._last_remote_gcode_path or self.remote_gcode_path,
        )
        return False
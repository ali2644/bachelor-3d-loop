from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import requests


class CameraClientError(RuntimeError):
    """The Raspberry Pi camera API was unavailable or returned invalid data."""


class CameraClient:
    def __init__(
        self,
        base_url: str,
        *,
        download_directory: str | Path,
        health_timeout_seconds: float = 5.0,
        capture_timeout_seconds: float = 30.0,
        download_timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.download_directory = Path(
            download_directory
        ).expanduser()
        self.health_timeout_seconds = health_timeout_seconds
        self.capture_timeout_seconds = capture_timeout_seconds
        self.download_timeout_seconds = download_timeout_seconds
        self.session = session or requests.Session()

    def health(self) -> bool:
        try:
            response = self.session.get(
                f"{self.base_url}/camera/health",
                timeout=self.health_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()

        except (requests.RequestException, ValueError) as error:
            raise CameraClientError(
                f"Camera health check failed: {error}"
            ) from error

        if (
            not isinstance(data, Mapping)
            or data.get("status") != "ok"
        ):
            raise CameraClientError(
                f"Unexpected camera health response: {data!r}"
            )

        return True

    def capture_still(self, cycle_id: str) -> str:
        """Capture exactly one image for a cycle and return its filename."""

        try:
            response = self.session.post(
                f"{self.base_url}/camera/captures/{cycle_id}",
                timeout=self.capture_timeout_seconds,
            )

        except requests.RequestException as error:
            raise CameraClientError(
                f"Camera capture request failed: {error}"
            ) from error

        if not response.ok:
            detail = self._extract_error_detail(response)

            raise CameraClientError(
                "Camera capture failed with HTTP "
                f"{response.status_code}: {detail}"
            )

        try:
            data = response.json()

        except ValueError as error:
            raise CameraClientError(
                "Camera API returned invalid JSON."
            ) from error

        if (
            not isinstance(data, Mapping)
            or data.get("status") != "completed"
            or data.get("cycle_id") != cycle_id
        ):
            raise CameraClientError(
                f"Unexpected camera capture response: {data!r}"
            )

        filename = data.get("filename")

        if not isinstance(filename, str) or not filename:
            raise CameraClientError(
                "Camera capture response does not contain a filename."
            )

        self._download_capture(
            cycle_id,
            filename,
        )

        return filename

    def _download_capture(
        self,
        cycle_id: str,
        filename: str,
    ) -> Path:
        expected_filename = f"{cycle_id}.jpg"

        if filename != expected_filename:
            raise CameraClientError(
                "Camera API returned an unexpected "
                f"filename: {filename!r}."
            )

        try:
            response = self.session.get(
                f"{self.base_url}/camera/captures/{cycle_id}",
                timeout=self.download_timeout_seconds,
            )

        except requests.RequestException as error:
            raise CameraClientError(
                f"Camera image download failed: {error}"
            ) from error

        if not response.ok:
            detail = self._extract_error_detail(response)

            raise CameraClientError(
                "Camera image download failed with HTTP "
                f"{response.status_code}: {detail}"
            )

        image_data = response.content

        if not image_data:
            raise CameraClientError(
                "Camera API returned an empty image."
            )

        output_path = (
            self.download_directory
            / filename
        )
        temporary_path = output_path.with_name(
            f"{output_path.name}.part"
        )

        try:
            self.download_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
            temporary_path.write_bytes(image_data)
            temporary_path.replace(output_path)

        except OSError as error:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise CameraClientError(
                "Could not save camera image locally: "
                f"{error}"
            ) from error

        return output_path

    @staticmethod
    def _extract_error_detail(
        response: requests.Response,
    ) -> object:
        try:
            data = response.json()

        except ValueError:
            return response.text

        if isinstance(data, Mapping):
            return data.get("detail", data)

        return data
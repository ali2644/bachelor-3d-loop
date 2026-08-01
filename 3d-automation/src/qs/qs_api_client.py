from __future__ import annotations

import math
from collections.abc import Mapping

import requests


class QualityStationClientError(RuntimeError):
    """The QS HTTP service was unavailable or returned invalid data."""


class QualityStationClient:
    def __init__(
        self,
        base_url: str,
        *,
        health_timeout_seconds: float = 5.0,
        measurement_timeout_seconds: float = 90.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.health_timeout_seconds = health_timeout_seconds
        self.measurement_timeout_seconds = measurement_timeout_seconds
        self.session = session or requests.Session()

    def health(self) -> bool:
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=self.health_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            raise QualityStationClientError(
                f"QS health check failed: {error}"
            ) from error

        if (
            not isinstance(data, Mapping)
            or data.get("status") != "ok"
        ):
            raise QualityStationClientError(
                f"Unexpected QS health response: {data!r}"
            )

        return True

    def measure(self) -> dict[str, float]:
        """
        Start exactly one measurement.

        This POST is deliberately not retried. After a network timeout it is
        unknown whether the SJ-220 already started moving.
        """
        try:
            response = self.session.post(
                f"{self.base_url}/measurements",
                timeout=self.measurement_timeout_seconds,
            )
        except requests.RequestException as error:
            raise QualityStationClientError(
                "QS measurement request failed. Do not retry automatically; "
                f"check the SJ-220 state first. Details: {error}"
            ) from error

        if not response.ok:
            detail = self._extract_error_detail(response)
            raise QualityStationClientError(
                f"QS measurement failed with HTTP "
                f"{response.status_code}: {detail}"
            )

        try:
            data = response.json()
        except ValueError as error:
            raise QualityStationClientError(
                "QS returned invalid JSON."
            ) from error

        if not isinstance(data, Mapping) or data.get("status") != "completed":
            raise QualityStationClientError(
                f"Unexpected QS measurement response: {data!r}"
            )

        results = data.get("results")
        if not isinstance(results, Mapping):
            raise QualityStationClientError(
                "QS response does not contain a results object."
            )

        validated: dict[str, float] = {}
        for parameter in ("Ra", "Rz"):
            raw_value = results.get(parameter)
            if isinstance(raw_value, bool):
                raw_value = None

            try:
                value = float(raw_value)
            except (TypeError, ValueError) as error:
                raise QualityStationClientError(
                    f"QS result {parameter!r} is missing or invalid."
                ) from error

            if not math.isfinite(value):
                raise QualityStationClientError(
                    f"QS result {parameter!r} is not finite."
                )

            validated[parameter] = value

        return validated

    @staticmethod
    def _extract_error_detail(response: requests.Response) -> object:
        try:
            data = response.json()
        except ValueError:
            return response.text

        if isinstance(data, Mapping):
            return data.get("detail", data)

        return data

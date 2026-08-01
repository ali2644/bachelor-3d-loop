from __future__ import annotations

import sys
import types
import unittest

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Session:
        pass

    requests_stub.RequestException = RequestException
    requests_stub.Session = Session
    sys.modules["requests"] = requests_stub

from qs.qs_api_client import (
    QualityStationClient,
    QualityStationClientError,
)


class FakeResponse:
    def __init__(
        self,
        data,
        *,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        self.data = data
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 400

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.data


class FakeSession:
    def __init__(
        self,
        *,
        health_response: FakeResponse,
        measurement_response: FakeResponse,
    ) -> None:
        self.health_response = health_response
        self.measurement_response = measurement_response
        self.post_calls = 0

    def get(self, url: str, timeout: float) -> FakeResponse:
        return self.health_response

    def post(self, url: str, timeout: float) -> FakeResponse:
        self.post_calls += 1
        return self.measurement_response


class QualityStationClientTest(unittest.TestCase):
    def test_validates_health_and_measurement_response(self) -> None:
        session = FakeSession(
            health_response=FakeResponse(
                {"status": "ok", "service": "qs-station"}
            ),
            measurement_response=FakeResponse(
                {
                    "status": "completed",
                    "results": {"Ra": 4.152, "Rz": 22.5},
                    "unit": "um",
                }
            ),
        )
        client = QualityStationClient(
            "http://raspberrypi:8000",
            session=session,
        )

        self.assertTrue(client.health())
        self.assertEqual(
            client.measure(),
            {"Ra": 4.152, "Rz": 22.5},
        )
        self.assertEqual(session.post_calls, 1)

    def test_rejects_missing_required_measurement(self) -> None:
        session = FakeSession(
            health_response=FakeResponse({"status": "ok"}),
            measurement_response=FakeResponse(
                {
                    "status": "completed",
                    "results": {"Ra": 4.152},
                }
            ),
        )
        client = QualityStationClient(
            "http://raspberrypi:8000",
            session=session,
        )

        with self.assertRaises(QualityStationClientError):
            client.measure()

        self.assertEqual(session.post_calls, 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

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

from printer.prusalink_service import PrusaLinkService


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        data=None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.data = data
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.data


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.put_calls = 0
        self.head_calls = 0
        self.post_calls = 0

    def get(self, url: str, timeout):
        if url.endswith("/api/printer"):
            return FakeResponse(status_code=200)
        return FakeResponse(
            data={"printer": {"state": "printing"}}
        )

    def put(self, url: str, *, data, headers, timeout):
        self.put_calls += 1
        self.put_url = url
        self.uploaded_data = data.read()
        self.upload_headers = headers
        return FakeResponse(status_code=201)

    def head(self, url: str, timeout):
        self.head_calls += 1
        return FakeResponse(status_code=200)

    def post(self, url: str, timeout):
        self.post_calls += 1
        return FakeResponse(status_code=204)


class PrusaLinkServiceTest(unittest.TestCase):
    def test_upload_verifies_remote_file_and_reads_state(self) -> None:
        session = FakeSession()
        service = PrusaLinkService(
            "10.8.170.57",
            "secret",
            session=session,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            gcode_path = Path(temporary_directory) / "output.gcode"
            gcode_path.write_text("G28\n", encoding="utf-8")

            self.assertTrue(service.upload_gcode(gcode_path))

        self.assertEqual(session.headers["X-Api-Key"], "secret")
        self.assertEqual(session.put_calls, 1)
        self.assertEqual(session.head_calls, 1)
        self.assertEqual(session.uploaded_data, b"G28\n")
        self.assertEqual(
            session.upload_headers,
            {
                "Content-Type": "application/octet-stream",
                "Overwrite": "?1",
                "Print-After-Upload": "?0",
            },
        )
        self.assertEqual(service.get_printer_state(), "PRINTING")

    def test_upload_can_request_an_atomic_print_start(self) -> None:
        session = FakeSession()
        service = PrusaLinkService(
            "10.8.170.57",
            "secret",
            remote_gcode_path="FOLDER/",
            session=session,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            gcode_path = Path(temporary_directory) / "output.gcode"
            gcode_path.write_text("G28\n", encoding="utf-8")

            self.assertTrue(
                service.upload_gcode(
                    gcode_path,
                    start_after_upload=True,
                )
            )

        self.assertEqual(session.put_calls, 1)
        self.assertTrue(
            session.put_url.endswith("/usb/FOLDER/output.gcode")
        )
        self.assertEqual(session.head_calls, 0)
        self.assertEqual(session.post_calls, 0)
        self.assertEqual(
            session.upload_headers["Print-After-Upload"],
            "?1",
        )

    def test_start_uses_the_same_verified_remote_path(self) -> None:
        session = FakeSession()
        service = PrusaLinkService(
            "10.8.170.57",
            "secret",
            remote_gcode_path="FOLDER/test.gcode",
            session=session,
        )

        self.assertTrue(service.start_print_job())
        self.assertEqual(session.post_calls, 1)


if __name__ == "__main__":
    unittest.main()
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import requests

from camera.camera_client import CameraClient, CameraClientError




class FakeResponse:
    def __init__(
        self,
        data,
        *,
        status_code: int = 200,
        text: str = "",
        content: bytes = b"",
    ) -> None:
        self._data = data
        self.status_code = status_code
        self.text = text
        self.content = content

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(
                f"HTTP {self.status_code}"
            )

    def json(self):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeSession:
    def __init__(
        self,
        *,
        get_response: FakeResponse | None = None,
        post_response: FakeResponse | None = None,
    ) -> None:
        self.get_response = get_response
        self.post_response = post_response
        self.get_calls = []
        self.post_calls = []

    def get(self, url: str, *, timeout: float):
        self.get_calls.append((url, timeout))
        if self.get_response is None:
            raise AssertionError("Unexpected GET")
        return self.get_response

    def post(self, url: str, *, timeout: float):
        self.post_calls.append((url, timeout))
        if self.post_response is None:
            raise AssertionError("Unexpected POST")
        return self.post_response


class CameraClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )
        self.addCleanup(
            self.temporary_directory.cleanup
        )
        self.download_directory = Path(
            self.temporary_directory.name
        )
    def test_health_uses_camera_health_endpoint(self) -> None:
        session = FakeSession(
            get_response=FakeResponse(
                {
                    "status": "ok",
                    "service": "camera",
                    "device_path": "/dev/video0",
                }
            )
        )
        client = CameraClient(
            "http://raspberry:8000/",
            download_directory=self.download_directory,
            session=session,
        )

        self.assertTrue(client.health())
        self.assertEqual(
            session.get_calls,
            [
                (
                    "http://raspberry:8000/camera/health",
                    5.0,
                )
            ],
        )

    def test_capture_http_error_is_wrapped(self) -> None:
        cycle_id = "b" * 32
        session = FakeSession(
            post_response=FakeResponse(
                {
                    "detail": {
                        "type": "camera_capture_error",
                        "message": "ffmpeg failed",
                    }
                },
                status_code=502,
            )
        )
        client = CameraClient(
            "http://raspberry:8000",
            download_directory=self.download_directory,
            session=session,
        )

        with self.assertRaises(CameraClientError):
            client.capture_still(cycle_id)

    def test_invalid_capture_response_is_rejected(self) -> None:
        cycle_id = "c" * 32
        session = FakeSession(
            post_response=FakeResponse(
                {
                    "status": "completed",
                    "cycle_id": "wrong-cycle",
                    "filename": "image.jpg",
                }
            )
        )
        client = CameraClient(
            "http://raspberry:8000",
            download_directory=self.download_directory,
            session=session,
        )

        with self.assertRaises(CameraClientError):
            client.capture_still(cycle_id)
    def test_capture_still_downloads_image(
        self,
    ) -> None:
        cycle_id = "a" * 32
        image_data = b"fake-jpeg-data"

        session = FakeSession(
            post_response=FakeResponse(
                {
                    "status": "completed",
                    "cycle_id": cycle_id,
                    "filename": f"{cycle_id}.jpg",
                }
            ),
            get_response=FakeResponse(
                None,
                content=image_data,
            ),
        )
        client = CameraClient(
            "http://raspberry:8000",
            download_directory=self.download_directory,
            session=session,
        )

        filename = client.capture_still(cycle_id)

        self.assertEqual(
            filename,
            f"{cycle_id}.jpg",
        )
        self.assertEqual(
            (
                self.download_directory
                / filename
            ).read_bytes(),
            image_data,
        )
        self.assertEqual(
            session.get_calls,
            [
                (
                    (
                        "http://raspberry:8000/"
                        f"camera/captures/{cycle_id}"
                    ),
                    30.0,
                )
            ],
        )

    def test_download_http_error_is_wrapped(
        self,
    ) -> None:
        cycle_id = "d" * 32
        session = FakeSession(
            post_response=FakeResponse(
                {
                    "status": "completed",
                    "cycle_id": cycle_id,
                    "filename": f"{cycle_id}.jpg",
                }
            ),
            get_response=FakeResponse(
                {
                    "detail": {
                        "type": "camera_capture_not_found",
                    }
                },
                status_code=404,
            ),
        )
        client = CameraClient(
            "http://raspberry:8000",
            download_directory=self.download_directory,
            session=session,
        )

        with self.assertRaisesRegex(
            CameraClientError,
            "download failed with HTTP 404",
        ):
            client.capture_still(cycle_id)

    def test_empty_download_is_rejected(self) -> None:
        cycle_id = "e" * 32
        session = FakeSession(
            post_response=FakeResponse(
                {
                    "status": "completed",
                    "cycle_id": cycle_id,
                    "filename": f"{cycle_id}.jpg",
                }
            ),
            get_response=FakeResponse(
                None,
                content=b"",
            ),
        )
        client = CameraClient(
            "http://raspberry:8000",
            download_directory=self.download_directory,
            session=session,
        )

        with self.assertRaisesRegex(
            CameraClientError,
            "empty image",
        ):
            client.capture_still(cycle_id)

    def test_unexpected_filename_is_rejected(
        self,
    ) -> None:
        cycle_id = "f" * 32
        session = FakeSession(
            post_response=FakeResponse(
                {
                    "status": "completed",
                    "cycle_id": cycle_id,
                    "filename": "wrong-image.jpg",
                }
            ),
        )
        client = CameraClient(
            "http://raspberry:8000",
            download_directory=self.download_directory,
            session=session,
        )

        with self.assertRaisesRegex(
            CameraClientError,
            "unexpected filename",
        ):
            client.capture_still(cycle_id)
if __name__ == "__main__":
    unittest.main()

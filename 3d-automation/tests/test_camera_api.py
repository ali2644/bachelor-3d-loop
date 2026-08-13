from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from qs import api


class CameraApiTest(unittest.TestCase):
    def test_camera_health_reports_configured_device(self) -> None:
        with (
            patch(
                "qs.api._camera_device_path",
                return_value="/dev/video7",
            ),
            patch(
                "qs.api.shutil.which",
                return_value="/usr/bin/tool",
            ),
            patch(
                "qs.api.Path.exists",
                return_value=True,
            ),
        ):
            result = api.camera_health()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["service"], "camera")
        self.assertEqual(
            result["device_path"],
            "/dev/video7",
        )

    def test_camera_capture_uses_cycle_id_as_filename(
        self,
    ) -> None:
        cycle_id = "a" * 32

        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)

            def fake_capture(
                device_path: str,
                output_path: str,
                *,
                width: int,
                height: int,
                pixel_format: str,
            ) -> None:
                self.assertEqual(
                    device_path,
                    "/dev/video0",
                )
                self.assertEqual(width, 1920)
                self.assertEqual(height, 1080)
                self.assertEqual(
                    pixel_format,
                    "mjpeg",
                )
                Path(output_path).write_bytes(
                    b"fake-jpeg-data"
                )

            with (
                patch(
                    "qs.api._camera_output_directory",
                    return_value=output_directory,
                ),
                patch(
                    "qs.api._camera_device_path",
                    return_value="/dev/video0",
                ),
                patch(
                    "qs.api._camera_width",
                    return_value=1920,
                ),
                patch(
                    "qs.api._camera_height",
                    return_value=1080,
                ),
                patch(
                    "qs.api._camera_pixel_format",
                    return_value="mjpeg",
                ),
                patch(
                    "qs.api.capture_still",
                    side_effect=fake_capture,
                ),
            ):
                result = api.create_camera_capture(
                    cycle_id
                )

        self.assertEqual(
            result,
            {
                "status": "completed",
                "cycle_id": cycle_id,
                "filename": f"{cycle_id}.jpg",
            },
        )

    def test_invalid_cycle_id_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            api.create_camera_capture(
                "../invalid"
            )

        self.assertEqual(
            context.exception.status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from printer.slicer_service import SlicerService


class SlicerServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.slicer_path = self.root / "PrusaSlicer.AppImage"
        self.stl_path = self.root / "part.stl"
        self.profile_path = self.root / "profile.ini"
        self.gcode_path = self.root / "output.gcode"

        self.slicer_path.write_text("executable", encoding="utf-8")
        self.slicer_path.chmod(
            self.slicer_path.stat().st_mode | stat.S_IXUSR
        )
        self.stl_path.write_text("solid part\nendsolid\n", encoding="utf-8")
        self.profile_path.write_text(
            "layer_height = 0.2\n",
            encoding="utf-8",
        )

    @patch("printer.slicer_service.subprocess.run")
    def test_nonzero_return_code_is_failure(self, run_mock) -> None:
        run_mock.return_value = CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr="invalid profile",
        )
        service = SlicerService(self.slicer_path)

        success = service.send_stl_to_slicer(
            self.stl_path,
            self.profile_path,
            self.gcode_path,
        )

        self.assertFalse(success)

    @patch("printer.slicer_service.subprocess.run")
    def test_success_requires_nonempty_gcode_file(self, run_mock) -> None:
        run_mock.return_value = CompletedProcess(
            args=[],
            returncode=0,
            stdout="done",
            stderr="",
        )
        service = SlicerService(self.slicer_path)

        success = service.send_stl_to_slicer(
            self.stl_path,
            self.profile_path,
            self.gcode_path,
        )

        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main()

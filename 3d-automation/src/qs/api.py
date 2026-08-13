from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from camera.camera_ctrl import capture_still

from fastapi import FastAPI, HTTPException

from qs.sj220_exceptions import (
    SJ220ConnectionError,
    SJ220DeviceError,
    SJ220Error,
    SJ220PortInUseError,
    SJ220ProtocolError,
    SJ220ResultError,
    SJ220StateError,
    SJ220TimeoutError,
)
from qs.sj220_service import SJ220Service


LOGGER = logging.getLogger(__name__)

CAMERA_CYCLE_ID_PATTERN = re.compile(
    r"^[0-9a-f]{32}$"
)


def _camera_device_path() -> str:
    return os.getenv(
        "CAMERA_DEVICE_PATH",
        "/dev/video0",
    )


def _camera_output_directory() -> Path:
    return Path(
        os.getenv(
            "CAMERA_OUTPUT_DIR",
            "data/camera_images",
        )
    ).expanduser()


def _camera_width() -> int:
    return int(
        os.getenv("CAMERA_WIDTH", "1920")
    )


def _camera_height() -> int:
    return int(
        os.getenv("CAMERA_HEIGHT", "1080")
    )


def _camera_pixel_format() -> str:
    return os.getenv(
        "CAMERA_PIXEL_FORMAT",
        "mjpeg",
    )

app = FastAPI(
    title="QS Station API",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "qs-station",
    }

@app.get("/camera/health")
def camera_health() -> dict[str, str]:
    device_path = _camera_device_path()

    missing_commands = [
        command
        for command in ("ffmpeg", "v4l2-ctl")
        if shutil.which(command) is None
    ]

    if missing_commands:
        raise HTTPException(
            status_code=503,
            detail={
                "type": "missing_dependency",
                "message": (
                    "Missing camera command(s): "
                    + ", ".join(missing_commands)
                ),
            },
        )

    if not Path(device_path).exists():
        raise HTTPException(
            status_code=503,
            detail={
                "type": "camera_unavailable",
                "message": (
                    f"Camera device not found: "
                    f"{device_path}"
                ),
            },
        )

    return {
        "status": "ok",
        "service": "camera",
        "device_path": device_path,
    }

@app.post("/camera/captures/{cycle_id}")
def create_camera_capture(
    cycle_id: str,
) -> dict[str, str]:

    if CAMERA_CYCLE_ID_PATTERN.fullmatch(
        cycle_id
    ) is None:
        raise HTTPException(
            status_code=422,
            detail={
                "type": "invalid_cycle_id",
                "message": (
                    "cycle_id must be a "
                    "32-character lowercase UUID "
                    "hex value."
                ),
            },
        )

    output_directory = (
        _camera_output_directory()
    )
    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        output_directory
        / f"{cycle_id}.jpg"
    )

    try:
        capture_still(
            _camera_device_path(),
            str(output_path),
            width=_camera_width(),
            height=_camera_height(),
            pixel_format=_camera_pixel_format(),
        )

    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        LOGGER.exception(
            "Camera capture failed for cycle %s.",
            cycle_id,
        )

        raise HTTPException(
            status_code=502,
            detail={
                "type": "camera_capture_error",
                "message": str(error),
            },
        ) from error

    if (
        not output_path.is_file()
        or output_path.stat().st_size == 0
    ):
        raise HTTPException(
            status_code=502,
            detail={
                "type": "camera_capture_error",
                "message": (
                    "Camera did not create a "
                    f"valid image: {output_path}"
                ),
            },
        )

    return {
        "status": "completed",
        "cycle_id": cycle_id,
        "filename": output_path.name,
    }


@app.post("/measurements")
def create_measurement() -> dict[str, object]:
    try:
        with SJ220Service(
            port="/dev/ttyUSB0",
            baudrate=38400,
        ) as quality_station:
            report = quality_station.measure(
                required_parameters=("Ra", "Rz"),
            )

        results = report.as_dict()
        units = {
            result.unit
            for result in report.results
        }

        return {
            "status": "completed",
            "results": results,
            "unit": units.pop() if len(units) == 1 else None,
            "duration_seconds": round(
                report.duration_seconds,
                2,
            ),
        }

    except SJ220PortInUseError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "port_in_use",
                "message": str(error),
            },
        ) from error

    except SJ220ConnectionError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "type": "connection_error",
                "message": str(error),
            },
        ) from error

    except SJ220TimeoutError as error:
        raise HTTPException(
            status_code=504,
            detail={
                "type": "timeout",
                "message": str(error),
            },
        ) from error

    except SJ220StateError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "invalid_state",
                "message": str(error),
            },
        ) from error

    except SJ220DeviceError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "type": "device_error",
                "code": error.code,
                "message": str(error),
            },
        ) from error

    except SJ220ResultError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "type": "result_error",
                "message": str(error),
            },
        ) from error

    except SJ220ProtocolError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "type": "protocol_error",
                "message": str(error),
            },
        ) from error

    except SJ220Error as error:
        LOGGER.exception("Unhandled SJ-220 error.")

        raise HTTPException(
            status_code=500,
            detail={
                "type": "sj220_error",
                "message": str(error),
            },
        ) from error
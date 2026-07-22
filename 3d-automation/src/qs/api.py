from __future__ import annotations

import logging

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
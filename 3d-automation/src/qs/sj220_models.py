from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SJ220Status(str, Enum):
    IDLE = "000"
    MEASURING = "001"
    RETURNING = "002"
    RETRACTING = "003"
    RETRACTED = "004"
    INTERMEDIATE_POSITION = "005"

    @property
    def description(self) -> str:
        descriptions = {
            SJ220Status.IDLE: "Idle / ready",
            SJ220Status.MEASURING: "Measurement in progress",
            SJ220Status.RETURNING: "Detector returning",
            SJ220Status.RETRACTING: "Detector retracting",
            SJ220Status.RETRACTED: "Detector retracted",
            SJ220Status.INTERMEDIATE_POSITION: (
                "Detector between defined end positions"
            ),
        }
        return descriptions[self]


@dataclass(frozen=True)
class MeasurementResult:
    parameter: str
    value: float
    unit: str
    raw_value: str
    parameter_number: int


@dataclass(frozen=True)
class MeasurementReport:
    results: tuple[MeasurementResult, ...]
    duration_seconds: float

    def as_dict(self) -> dict[str, float]:
        return {
            result.parameter: result.value
            for result in self.results
        }

    def get_result(self, parameter: str) -> MeasurementResult | None:
        for result in self.results:
            if result.parameter == parameter:
                return result

        return None
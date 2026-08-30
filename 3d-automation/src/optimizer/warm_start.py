from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.stats import qmc

from optimizer.config import OptimizerConfig, load_optimizer_config
from optimizer.experiment_store import ExperimentStore, RunRecord
from printer.print_parameters import PrintParameters


WARM_START_PLAN_SCHEMA_VERSION = 1
MAX_GENERATION_BATCHES = 100


class WarmStartError(RuntimeError):
    """Raised when a valid and unique warm-start plan cannot be built."""


@dataclass(frozen=True)
class WarmStartPoint:
    index: int
    parameters: PrintParameters

    def numeric_parameters(self) -> dict[str, int | float]:
        return {
            "top_solid_layers": self.parameters.top_solid_layers,
            "print_speed": float(self.parameters.print_speed),
            "extrusion_width": float(self.parameters.extrusion_width),
            "extrusion_multiplier": float(
                self.parameters.extrusion_multiplier
            ),
            "temperature": self.parameters.temperature,
            "fan_speed": self.parameters.fan_speed,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "warm_start_index": self.index,
            "parameters": self.numeric_parameters(),
        }


@dataclass(frozen=True)
class WarmStartPlan:
    schema_version: int
    method: str
    seed: int
    variable_names: tuple[str, ...]
    points: tuple[WarmStartPoint, ...]

    @property
    def sample_count(self) -> int:
        return len(self.points)

    def point_for_run(self, run_number: int) -> WarmStartPoint:
        if isinstance(run_number, bool) or not isinstance(run_number, int):
            raise WarmStartError("run_number must be an integer.")
        if not 1 <= run_number <= self.sample_count:
            raise WarmStartError(
                f"Run {run_number} is outside the warm-start phase "
                f"1-{self.sample_count}."
            )
        return self.points[run_number - 1]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "method": self.method,
            "seed": self.seed,
            "sample_count": self.sample_count,
            "variable_names": list(self.variable_names),
            "points": [point.as_dict() for point in self.points],
        }


class WarmStartGenerator:
    """Generate deterministic, quantized and unique physical start points."""

    def __init__(self, config: OptimizerConfig) -> None:
        self.config = config

    def generate(self) -> WarmStartPlan:
        sample_count = self.config.warm_start.sample_count
        capacity = self._quantized_space_capacity()
        if sample_count > capacity:
            raise WarmStartError(
                f"The configured parameter space contains at most {capacity} "
                f"different quantized parameter sets, but {sample_count} "
                "warm-start samples were requested."
            )

        unique_points: list[PrintParameters] = []
        seen: set[tuple[object, ...]] = set()
        for batch_index in range(MAX_GENERATION_BATCHES):
            remaining = sample_count - len(unique_points)
            if remaining == 0:
                break
            batch_size = sample_count if batch_index == 0 else max(
                sample_count,
                remaining * 4,
            )
            unit_samples = self._sample_unit_batch(
                batch_size,
                batch_index,
            )
            for unit_sample in unit_samples:
                parameters = self._to_print_parameters(unit_sample)
                key = self._parameter_key(parameters)
                if key in seen:
                    continue
                seen.add(key)
                unique_points.append(parameters)
                if len(unique_points) == sample_count:
                    break

        if len(unique_points) != sample_count:
            raise WarmStartError(
                "Could not generate the requested number of unique "
                "warm-start points after quantization. Widen the parameter "
                "bounds or reduce warm_start.sample_count."
            )

        return WarmStartPlan(
            schema_version=WARM_START_PLAN_SCHEMA_VERSION,
            method=self.config.warm_start.method,
            seed=self.config.seed,
            variable_names=self.config.variable_names,
            points=tuple(
                WarmStartPoint(index=index, parameters=parameters)
                for index, parameters in enumerate(unique_points, start=1)
            ),
        )

    def propose_next(self, store: ExperimentStore) -> RunRecord:
        """Save the next warm-start point or return its existing record."""
        plan = self.generate()
        next_run_number = store.next_run_number()
        if next_run_number is None:
            raise WarmStartError("The experiment is already complete.")
        if next_run_number > plan.sample_count:
            raise WarmStartError(
                "The warm-start phase is already complete; the selected "
                "main strategy must provide the next proposal."
            )

        existing_record = store.load_resume_run(next_run_number)
        if existing_record is not None:
            return existing_record

        point = plan.point_for_run(next_run_number)
        return store.propose_run(
            point.numeric_parameters(),
            strategy=self.config.strategy.name,
            optimizer_iteration=None,
        )

    def _sample_unit_batch(
        self,
        sample_count: int,
        batch_index: int,
    ) -> np.ndarray:
        dimensions = len(self.config.parameters)
        seed = self.config.seed + batch_index
        method = self.config.warm_start.method

        if method == "lhs":
            return qmc.LatinHypercube(
                d=dimensions,
                seed=seed,
            ).random(n=sample_count)
        if method == "random":
            return np.random.default_rng(seed).random(
                size=(sample_count, dimensions)
            )
        if method == "sobol":
            exponent = math.ceil(math.log2(sample_count))
            samples = qmc.Sobol(
                d=dimensions,
                scramble=True,
                seed=seed,
            ).random_base2(m=exponent)
            return samples[:sample_count]
        raise WarmStartError(f"Unknown warm-start method {method!r}.")

    def _to_print_parameters(
        self,
        unit_sample: np.ndarray,
    ) -> PrintParameters:
        if len(unit_sample) != len(self.config.parameters):
            raise WarmStartError(
                "Unit sample dimension does not match configured variables."
            )

        values: dict[str, int | float] = dict(
            self.config.fixed_parameters
        )
        for variable, unit_value in zip(
            self.config.parameters,
            unit_sample,
            strict=True,
        ):
            scaled_value = float(variable.lower) + float(unit_value) * (
                float(variable.upper) - float(variable.lower)
            )
            values[variable.name] = variable.quantize(scaled_value)

        try:
            return PrintParameters(
                top_solid_layers=int(values["top_solid_layers"]),
                print_speed=float(values["print_speed"]),
                extrusion_width=float(values["extrusion_width"]),
                extrusion_multiplier=float(values["extrusion_multiplier"]),
                temperature=int(values["temperature"]),
                fan_speed=int(values["fan_speed"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise WarmStartError(
                f"Generated warm-start parameters are invalid: {error}"
            ) from error

    def _quantized_space_capacity(self) -> int:
        capacity = 1
        for variable in self.config.parameters:
            definition = variable.definition
            scale = 10**definition.decimals
            lower_step = math.ceil(float(variable.lower) * scale - 1e-9)
            upper_step = math.floor(float(variable.upper) * scale + 1e-9)
            step_count = max(0, upper_step - lower_step + 1)
            capacity *= step_count
        return capacity

    @staticmethod
    def _parameter_key(parameters: PrintParameters) -> tuple[object, ...]:
        return (
            parameters.top_solid_layers,
            float(parameters.print_speed),
            float(parameters.extrusion_width),
            float(parameters.extrusion_multiplier),
            parameters.temperature,
            parameters.fan_speed,
        )


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Preview the deterministic warm-start plan without touching "
            "hardware or experiment state."
        )
    )
    parser.add_argument("config", type=Path)
    parsed = parser.parse_args(arguments)

    config = load_optimizer_config(parsed.config)
    plan = WarmStartGenerator(config).generate()
    print(json.dumps(plan.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

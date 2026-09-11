from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from optimizer.objective import (
    ObjectiveExpressionError,
    validate_objective_expression,
)


CONFIG_SCHEMA_VERSION = 1
SUPPORTED_WARM_START_METHODS = frozenset({"lhs", "random", "sobol"})

STRATEGY_ALIASES = {
    "bo": "bayesian",
    "bayesian": "bayesian",
    "bayesian_optimization": "bayesian",
    "pso": "pso",
    "de": "differential_evolution",
    "differential_evolution": "differential_evolution",
    "random": "random",
    "sobol": "sobol",
}
SUPPORTED_STRATEGIES = frozenset(STRATEGY_ALIASES.values())


class OptimizerConfigError(ValueError):
    """Raised when an optimizer JSON configuration is invalid."""


@dataclass(frozen=True)
class ParameterDefinition:
    """Number format and intrinsic domain of one supported parameter."""

    decimals: int
    integer: bool = False
    minimum: float | None = None
    maximum: float | None = None
    exclusive_minimum: bool = False

    def quantize(self, value: float) -> int | float:
        if self.integer:
            return int(round(float(value)))
        return round(float(value), self.decimals)


# Experiment bounds are selected entirely in the JSON configuration. These
# definitions only preserve types, rounding and unavoidable mathematical
# domains. In particular, top_solid_layers may be fixed or optimized.
PARAMETER_DEFINITIONS: Mapping[str, ParameterDefinition] = MappingProxyType(
    {
        "top_solid_layers": ParameterDefinition(
            decimals=0,
            integer=True,
            minimum=0,
        ),
        "print_speed": ParameterDefinition(
            decimals=1,
            minimum=0,
            exclusive_minimum=True,
        ),
        "extrusion_width": ParameterDefinition(
            decimals=3,
            minimum=0,
            exclusive_minimum=True,
        ),
        "extrusion_multiplier": ParameterDefinition(
            decimals=3,
            minimum=0,
            exclusive_minimum=True,
        ),
        "temperature": ParameterDefinition(
            decimals=0,
            integer=True,
            minimum=0,
        ),
        "fan_speed": ParameterDefinition(
            decimals=0,
            integer=True,
            minimum=0,
            maximum=100,
        ),
    }
)


@dataclass(frozen=True)
class ParameterBounds:
    """Lower and upper bound selected for one optimization variable."""

    name: str
    lower: int | float
    upper: int | float

    @property
    def definition(self) -> ParameterDefinition:
        return PARAMETER_DEFINITIONS[self.name]

    def quantize(self, value: float) -> int | float:
        """Round a proposed value according to this parameter's type."""
        bounded = min(max(float(value), float(self.lower)), float(self.upper))
        return self.definition.quantize(bounded)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "lower": self.lower,
            "upper": self.upper,
        }


@dataclass(frozen=True)
class WarmStartConfig:
    method: str
    sample_count: int


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    options: Mapping[str, object]


@dataclass(frozen=True)
class OptimizerPaths:
    stl: Path
    base_profile: Path
    output_directory: Path
    history_csvs: tuple[Path, ...]


@dataclass(frozen=True)
class OptimizerConfig:
    """Validated, strategy-independent configuration of one experiment."""

    schema_version: int
    experiment_name: str
    total_runs: int
    seed: int
    objective: str
    warm_start: WarmStartConfig
    strategy: StrategyConfig
    parameters: tuple[ParameterBounds, ...]
    fixed_parameters: Mapping[str, int | float]
    paths: OptimizerPaths
    source_path: Path

    @property
    def variable_names(self) -> tuple[str, ...]:
        return tuple(parameter.name for parameter in self.parameters)

    @property
    def main_batch_size(self) -> int:
        """Number of physical runs needed for one strategy update."""
        if self.strategy.name == "bayesian":
            return 1
        return self.warm_start.sample_count

    def validate_input_files(self) -> None:
        """Fail before hardware moves when required local inputs are absent."""
        missing: list[Path] = []
        for path in (self.paths.stl, self.paths.base_profile):
            if not path.is_file():
                missing.append(path)
        for path in self.paths.history_csvs:
            if not path.is_file():
                missing.append(path)
        if missing:
            formatted = "\n".join(f"- {path}" for path in missing)
            raise OptimizerConfigError(
                "Configured input files do not exist:\n" + formatted
            )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-compatible snapshot with resolved absolute paths."""
        return {
            "schema_version": self.schema_version,
            "experiment_name": self.experiment_name,
            "total_runs": self.total_runs,
            "seed": self.seed,
            "objective": self.objective,
            "warm_start": {
                "method": self.warm_start.method,
                "sample_count": self.warm_start.sample_count,
            },
            "strategy": {
                "name": self.strategy.name,
                "options": dict(self.strategy.options),
            },
            "parameters": [
                parameter.as_dict() for parameter in self.parameters
            ],
            "fixed_parameters": dict(self.fixed_parameters),
            "paths": {
                "stl": str(self.paths.stl),
                "base_profile": str(self.paths.base_profile),
                "output_directory": str(self.paths.output_directory),
                "history_csvs": [
                    str(path) for path in self.paths.history_csvs
                ],
            },
            "source_path": str(self.source_path),
        }


def load_optimizer_config(path: str | Path) -> OptimizerConfig:
    """Load and fully validate one optimizer JSON configuration file."""
    source_path = Path(path).expanduser().resolve()
    try:
        with source_path.open("r", encoding="utf-8") as stream:
            raw_config = json.load(stream)
    except FileNotFoundError as error:
        raise OptimizerConfigError(
            f"Optimizer configuration not found: {source_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise OptimizerConfigError(
            f"Invalid JSON in {source_path} at line {error.lineno}, "
            f"column {error.colno}: {error.msg}."
        ) from error

    root = _require_mapping(raw_config, "configuration")
    _reject_unknown_keys(
        root,
        {
            "schema_version",
            "experiment_name",
            "total_runs",
            "seed",
            "objective",
            "warm_start",
            "strategy",
            "parameters",
            "fixed_parameters",
            "paths",
        },
        "configuration",
    )

    schema_version = _require_int(root, "schema_version", minimum=1)
    if schema_version != CONFIG_SCHEMA_VERSION:
        raise OptimizerConfigError(
            f"schema_version must be {CONFIG_SCHEMA_VERSION}, got "
            f"{schema_version}."
        )

    experiment_name = _require_text(root, "experiment_name")
    total_runs = _require_int(root, "total_runs", minimum=1)
    seed = _require_int(root, "seed", minimum=0)
    objective = _require_text(root, "objective")
    try:
        validate_objective_expression(objective)
    except ObjectiveExpressionError as error:
        raise OptimizerConfigError(
            f"Invalid objective: {error}"
        ) from error

    warm_start = _parse_warm_start(root.get("warm_start"))
    strategy = _parse_strategy(root.get("strategy"))
    parameters = _parse_parameters(root.get("parameters"))
    fixed_parameters = _parse_fixed_parameters(
        root.get("fixed_parameters")
    )
    _validate_complete_parameter_partition(parameters, fixed_parameters)
    paths = _parse_paths(root.get("paths"), source_path.parent)

    if total_runs < warm_start.sample_count:
        raise OptimizerConfigError(
            "total_runs must be at least warm_start.sample_count."
        )
    if strategy.name == "bayesian" and warm_start.sample_count < 2:
        raise OptimizerConfigError(
            "Bayesian optimization requires at least 2 warm-start samples."
        )
    if strategy.name == "pso" and warm_start.sample_count < 2:
        raise OptimizerConfigError(
            "PSO requires at least 2 warm-start samples/particles."
        )
    if (
        strategy.name == "differential_evolution"
        and warm_start.sample_count < 4
    ):
        raise OptimizerConfigError(
            "Differential Evolution requires at least 4 warm-start "
            "samples/individuals."
        )
    if strategy.name != "bayesian":
        additional_runs = total_runs - warm_start.sample_count
        if additional_runs % warm_start.sample_count != 0:
            raise OptimizerConfigError(
                "For batch-based strategies, total_runs minus "
                "warm_start.sample_count must be a complete strategy "
                "batch."
            )

    return OptimizerConfig(
        schema_version=schema_version,
        experiment_name=experiment_name,
        total_runs=total_runs,
        seed=seed,
        objective=objective,
        warm_start=warm_start,
        strategy=strategy,
        parameters=parameters,
        fixed_parameters=MappingProxyType(dict(fixed_parameters)),
        paths=paths,
        source_path=source_path,
    )


def _parse_warm_start(raw_value: object) -> WarmStartConfig:
    value = _require_mapping(raw_value, "warm_start")
    _reject_unknown_keys(value, {"method", "sample_count"}, "warm_start")
    method = _require_text(value, "method").lower()
    if method not in SUPPORTED_WARM_START_METHODS:
        supported = ", ".join(sorted(SUPPORTED_WARM_START_METHODS))
        raise OptimizerConfigError(
            f"warm_start.method must be one of: {supported}."
        )
    return WarmStartConfig(
        method=method,
        sample_count=_require_int(value, "sample_count", minimum=1),
    )


def _parse_strategy(raw_value: object) -> StrategyConfig:
    value = _require_mapping(raw_value, "strategy")
    _reject_unknown_keys(value, {"name", "options"}, "strategy")
    supplied_name = _require_text(value, "name").lower()
    try:
        name = STRATEGY_ALIASES[supplied_name]
    except KeyError as error:
        supported = ", ".join(sorted(SUPPORTED_STRATEGIES))
        raise OptimizerConfigError(
            f"strategy.name {supplied_name!r} is not supported. Use one "
            f"of: {supported}. QBC is intentionally excluded for now."
        ) from error

    raw_options = value.get("options", {})
    options = _require_mapping(raw_options, "strategy.options")
    validated_options = _validate_strategy_options(name, options)
    return StrategyConfig(
        name=name,
        options=MappingProxyType(validated_options),
    )


def _validate_strategy_options(
    strategy_name: str,
    raw_options: Mapping[str, Any],
) -> dict[str, object]:
    allowed_keys = {
        "bayesian": {
            "acquisition",
            "candidate_count",
            "n_restarts_optimizer",
        },
        "pso": {
            "inertia",
            "cognitive_weight",
            "social_weight",
            "max_velocity",
        },
        "differential_evolution": {
            "differential_weight",
            "crossover_probability",
        },
        "random": set(),
        "sobol": set(),
    }[strategy_name]
    _reject_unknown_keys(raw_options, allowed_keys, "strategy.options")

    if strategy_name == "bayesian":
        acquisition = _optional_text(
            raw_options,
            "acquisition",
            default="ei",
        ).lower()
        if acquisition not in {"ei", "thompson"}:
            raise OptimizerConfigError(
                "strategy.options.acquisition must be 'ei' or 'thompson'."
            )
        return {
            "acquisition": acquisition,
            "candidate_count": _optional_int(
                raw_options,
                "candidate_count",
                default=4096,
                minimum=64,
            ),
            "n_restarts_optimizer": _optional_int(
                raw_options,
                "n_restarts_optimizer",
                default=5,
                minimum=0,
            ),
        }

    if strategy_name == "pso":
        return {
            "inertia": _optional_number(
                raw_options,
                "inertia",
                default=0.7,
                minimum=0.0,
                maximum=1.0,
            ),
            "cognitive_weight": _optional_number(
                raw_options,
                "cognitive_weight",
                default=1.5,
                minimum=0.0,
            ),
            "social_weight": _optional_number(
                raw_options,
                "social_weight",
                default=1.5,
                minimum=0.0,
            ),
            "max_velocity": _optional_number(
                raw_options,
                "max_velocity",
                default=0.2,
                minimum=0.0,
                maximum=1.0,
                exclusive_minimum=True,
            ),
        }

    if strategy_name == "differential_evolution":
        return {
            "differential_weight": _optional_number(
                raw_options,
                "differential_weight",
                default=0.8,
                minimum=0.0,
                maximum=2.0,
                exclusive_minimum=True,
            ),
            "crossover_probability": _optional_number(
                raw_options,
                "crossover_probability",
                default=0.9,
                minimum=0.0,
                maximum=1.0,
            ),
        }

    return {}


def _parse_parameters(raw_value: object) -> tuple[ParameterBounds, ...]:
    if not isinstance(raw_value, list) or not raw_value:
        raise OptimizerConfigError(
            "parameters must be a non-empty JSON array."
        )

    parsed: list[ParameterBounds] = []
    seen_names: set[str] = set()
    for index, raw_parameter in enumerate(raw_value):
        label = f"parameters[{index}]"
        parameter = _require_mapping(raw_parameter, label)
        _reject_unknown_keys(
            parameter,
            {"name", "lower", "upper"},
            label,
        )
        name = _require_text(parameter, "name", prefix=label)
        if name not in PARAMETER_DEFINITIONS:
            supported = ", ".join(PARAMETER_DEFINITIONS)
            raise OptimizerConfigError(
                f"{label}.name {name!r} is unknown. Use one of: "
                f"{supported}."
            )
        if name in seen_names:
            raise OptimizerConfigError(
                f"Parameter {name!r} is configured more than once."
            )
        seen_names.add(name)

        definition = PARAMETER_DEFINITIONS[name]
        lower = _require_number(parameter, "lower", prefix=label)
        upper = _require_number(parameter, "upper", prefix=label)
        _validate_parameter_value(name, lower, definition, f"{label}.lower")
        _validate_parameter_value(name, upper, definition, f"{label}.upper")
        if lower >= upper:
            raise OptimizerConfigError(
                f"{label}.lower must be smaller than {label}.upper."
            )
        parsed.append(
            ParameterBounds(
                name=name,
                lower=int(lower) if definition.integer else float(lower),
                upper=int(upper) if definition.integer else float(upper),
            )
        )

    return tuple(parsed)


def _parse_fixed_parameters(
    raw_value: object,
) -> dict[str, int | float]:
    value = _require_mapping(raw_value, "fixed_parameters")
    fixed: dict[str, int | float] = {}
    for name, raw_parameter_value in value.items():
        if name not in PARAMETER_DEFINITIONS:
            supported = ", ".join(PARAMETER_DEFINITIONS)
            raise OptimizerConfigError(
                f"fixed_parameters contains unknown parameter {name!r}. "
                f"Use one of: {supported}."
            )
        parameter_value = _number(
            raw_parameter_value,
            f"fixed_parameters.{name}",
        )
        definition = PARAMETER_DEFINITIONS[name]
        _validate_parameter_value(
            name,
            parameter_value,
            definition,
            f"fixed_parameters.{name}",
        )
        fixed[name] = (
            int(parameter_value)
            if definition.integer
            else float(parameter_value)
        )
    return fixed


def _validate_complete_parameter_partition(
    parameters: tuple[ParameterBounds, ...],
    fixed_parameters: Mapping[str, int | float],
) -> None:
    variable_names = {parameter.name for parameter in parameters}
    fixed_names = set(fixed_parameters)

    overlap = sorted(variable_names & fixed_names)
    if overlap:
        raise OptimizerConfigError(
            "Parameters cannot be variable and fixed at the same time: "
            + ", ".join(overlap)
            + "."
        )

    missing = sorted(set(PARAMETER_DEFINITIONS) - variable_names - fixed_names)
    if missing:
        raise OptimizerConfigError(
            "Every supported process parameter must either appear in "
            "parameters or fixed_parameters. Missing: "
            + ", ".join(missing)
            + "."
        )


def _parse_paths(raw_value: object, base_directory: Path) -> OptimizerPaths:
    value = _require_mapping(raw_value, "paths")
    _reject_unknown_keys(
        value,
        {"stl", "base_profile", "output_directory", "history_csvs"},
        "paths",
    )
    history_value = value.get("history_csvs", [])
    if not isinstance(history_value, list) or any(
        not isinstance(item, str) or not item.strip()
        for item in history_value
    ):
        raise OptimizerConfigError(
            "paths.history_csvs must be an array of non-empty paths."
        )

    history_paths = tuple(
        _resolve_path(item, base_directory) for item in history_value
    )
    if len(set(history_paths)) != len(history_paths):
        raise OptimizerConfigError(
            "paths.history_csvs contains the same resolved path more "
            "than once."
        )

    return OptimizerPaths(
        stl=_resolve_path(
            _require_text(value, "stl", prefix="paths"),
            base_directory,
        ),
        base_profile=_resolve_path(
            _require_text(value, "base_profile", prefix="paths"),
            base_directory,
        ),
        output_directory=_resolve_path(
            _require_text(value, "output_directory", prefix="paths"),
            base_directory,
        ),
        history_csvs=history_paths,
    )


def _resolve_path(raw_path: str, base_directory: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base_directory / path
    return path.resolve()


def _validate_parameter_value(
    name: str,
    value: float,
    definition: ParameterDefinition,
    label: str,
) -> None:
    if definition.integer and not value.is_integer():
        raise OptimizerConfigError(f"{label} must be an integer.")
    if definition.minimum is not None:
        invalid_minimum = (
            value <= definition.minimum
            if definition.exclusive_minimum
            else value < definition.minimum
        )
        if invalid_minimum:
            comparison = (
                "greater than"
                if definition.exclusive_minimum
                else "at least"
            )
            raise OptimizerConfigError(
                f"{label} must be {comparison} {definition.minimum:g}."
            )
    if definition.maximum is not None and value > definition.maximum:
        raise OptimizerConfigError(
            f"{label} must be at most {definition.maximum:g}."
        )


def _require_mapping(raw_value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(raw_value, dict):
        raise OptimizerConfigError(f"{label} must be a JSON object.")
    if any(not isinstance(key, str) for key in raw_value):
        raise OptimizerConfigError(f"{label} contains a non-text key.")
    return raw_value


def _reject_unknown_keys(
    value: Mapping[str, Any],
    allowed_keys: set[str],
    label: str,
) -> None:
    unknown = sorted(set(value) - allowed_keys)
    if unknown:
        raise OptimizerConfigError(
            f"{label} contains unknown fields: {', '.join(unknown)}."
        )


def _require_text(
    value: Mapping[str, Any],
    key: str,
    *,
    prefix: str | None = None,
) -> str:
    label = f"{prefix}.{key}" if prefix else key
    raw_value = value.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise OptimizerConfigError(f"{label} must be non-empty text.")
    return raw_value.strip()


def _optional_text(
    value: Mapping[str, Any],
    key: str,
    *,
    default: str,
) -> str:
    if key not in value:
        return default
    return _require_text(value, key, prefix="strategy.options")


def _number(raw_value: object, label: str) -> float:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise OptimizerConfigError(f"{label} must be numeric.")
    result = float(raw_value)
    if not math.isfinite(result):
        raise OptimizerConfigError(f"{label} must be finite.")
    return result


def _require_number(
    value: Mapping[str, Any],
    key: str,
    *,
    prefix: str | None = None,
) -> float:
    label = f"{prefix}.{key}" if prefix else key
    if key not in value:
        raise OptimizerConfigError(f"{label} is required.")
    return _number(value[key], label)


def _optional_number(
    value: Mapping[str, Any],
    key: str,
    *,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_minimum: bool = False,
) -> float:
    result = (
        default
        if key not in value
        else _number(value[key], f"strategy.options.{key}")
    )
    if minimum is not None:
        invalid_minimum = (
            result <= minimum if exclusive_minimum else result < minimum
        )
        if invalid_minimum:
            comparison = "greater than" if exclusive_minimum else "at least"
            raise OptimizerConfigError(
                f"strategy.options.{key} must be {comparison} {minimum}."
            )
    if maximum is not None and result > maximum:
        raise OptimizerConfigError(
            f"strategy.options.{key} must be at most {maximum}."
        )
    return result


def _require_int(
    value: Mapping[str, Any],
    key: str,
    *,
    minimum: int,
) -> int:
    if key not in value:
        raise OptimizerConfigError(f"{key} is required.")
    raw_value = value[key]
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise OptimizerConfigError(f"{key} must be an integer.")
    if raw_value < minimum:
        raise OptimizerConfigError(f"{key} must be at least {minimum}.")
    return raw_value


def _optional_int(
    value: Mapping[str, Any],
    key: str,
    *,
    default: int,
    minimum: int,
) -> int:
    if key not in value:
        return default
    raw_value = value[key]
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise OptimizerConfigError(
            f"strategy.options.{key} must be an integer."
        )
    if raw_value < minimum:
        raise OptimizerConfigError(
            f"strategy.options.{key} must be at least {minimum}."
        )
    return raw_value


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and display an optimizer configuration."
    )
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "--check-input-files",
        action="store_true",
        help="Also verify the STL, base profile and history CSV files.",
    )
    parsed = parser.parse_args(arguments)

    try:
        config = load_optimizer_config(parsed.config)
        if parsed.check_input_files:
            config.validate_input_files()
    except OptimizerConfigError as error:
        parser.error(str(error))

    print(json.dumps(config.as_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

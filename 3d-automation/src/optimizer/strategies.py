from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

import numpy as np
from scipy.optimize import differential_evolution
from scipy.stats import norm, qmc
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel

from optimizer.config import OptimizerConfig
from optimizer.experiment_store import ExperimentStore, StrategyCheckpoint
from printer.print_parameters import PrintParameters


class StrategyError(RuntimeError):
    """Raised when an optimization strategy cannot safely propose points."""


@dataclass(frozen=True)
class Observation:
    run_number: int
    parameters: Mapping[str, int | float]
    objective_value: float
    strategy: str
    optimizer_iteration: int | None


@dataclass(frozen=True)
class StrategyProposal:
    candidate_index: int
    parameters: Mapping[str, int | float]

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate_index": self.candidate_index,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class ProposalBatch:
    strategy: str
    iteration: int
    proposals: tuple[StrategyProposal, ...]
    checkpoint_state: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "iteration": self.iteration,
            "proposal_count": len(self.proposals),
            "proposals": [proposal.as_dict() for proposal in self.proposals],
            "checkpoint_state": dict(self.checkpoint_state),
        }


class StrategyAdapter(Protocol):
    name: str

    def propose(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None = None,
    ) -> ProposalBatch: ...


class ParameterSpace:
    """Scale and quantize strategy vectors using the shared configuration."""

    def __init__(self, config: OptimizerConfig) -> None:
        self.config = config
        self.variable_names = config.variable_names
        self.lower_bounds = np.asarray(
            [float(variable.lower) for variable in config.parameters],
            dtype=float,
        )
        self.upper_bounds = np.asarray(
            [float(variable.upper) for variable in config.parameters],
            dtype=float,
        )

    @property
    def dimension(self) -> int:
        return len(self.variable_names)

    def unit_from_parameters(
        self,
        parameters: Mapping[str, int | float],
    ) -> np.ndarray:
        try:
            real = np.asarray(
                [float(parameters[name]) for name in self.variable_names],
                dtype=float,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StrategyError(
                f"Observation has invalid optimizer parameters: {error}"
            ) from error
        scaled = (real - self.lower_bounds) / (
            self.upper_bounds - self.lower_bounds
        )
        if not np.all(np.isfinite(scaled)):
            raise StrategyError("Observation parameters must be finite.")
        if np.any(scaled < -1e-9) or np.any(scaled > 1.0 + 1e-9):
            raise StrategyError(
                "Observation parameters are outside configured bounds."
            )
        return np.clip(scaled, 0.0, 1.0)

    def parameters_from_unit(
        self,
        unit_point: Sequence[float],
    ) -> dict[str, int | float]:
        point = np.asarray(unit_point, dtype=float)
        if point.shape != (self.dimension,):
            raise StrategyError(
                "Strategy point dimension does not match the configuration."
            )
        if not np.all(np.isfinite(point)):
            raise StrategyError("Strategy points must be finite.")
        point = np.clip(point, 0.0, 1.0)
        real = self.lower_bounds + point * (
            self.upper_bounds - self.lower_bounds
        )
        values: dict[str, int | float] = dict(
            self.config.fixed_parameters
        )
        for variable, raw_value in zip(
            self.config.parameters,
            real,
            strict=True,
        ):
            values[variable.name] = variable.quantize(float(raw_value))

        try:
            validated = PrintParameters(
                top_solid_layers=int(values["top_solid_layers"]),
                print_speed=float(values["print_speed"]),
                extrusion_width=float(values["extrusion_width"]),
                extrusion_multiplier=float(values["extrusion_multiplier"]),
                temperature=int(values["temperature"]),
                fan_speed=int(values["fan_speed"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StrategyError(
                f"Strategy generated invalid print parameters: {error}"
            ) from error
        return _numeric_parameters(validated)

    def unique_parameters(
        self,
        unit_candidates: np.ndarray,
        *,
        observations: Sequence[Observation],
        required_count: int,
        seed: int,
    ) -> tuple[tuple[dict[str, int | float], ...], np.ndarray]:
        candidates = np.asarray(unit_candidates, dtype=float)
        if candidates.ndim != 2 or candidates.shape[1] != self.dimension:
            raise StrategyError("Candidate matrix has an invalid shape.")
        if required_count < 1:
            raise StrategyError("required_count must be at least 1.")

        seen = {
            _parameter_key(observation.parameters)
            for observation in observations
        }
        selected_parameters: list[dict[str, int | float]] = []
        selected_units: list[np.ndarray] = []

        fallback = qmc.LatinHypercube(
            d=self.dimension,
            seed=seed,
        ).random(n=max(4096, required_count * 128))
        all_candidates = np.vstack([candidates, fallback])
        for candidate in all_candidates:
            parameters = self.parameters_from_unit(candidate)
            key = _parameter_key(parameters)
            if key in seen:
                continue
            seen.add(key)
            selected_parameters.append(parameters)
            selected_units.append(self.unit_from_parameters(parameters))
            if len(selected_parameters) == required_count:
                break

        if len(selected_parameters) != required_count:
            raise StrategyError(
                "Could not create enough unique parameter proposals after "
                "quantization."
            )
        return tuple(selected_parameters), np.asarray(selected_units)


class BaseStrategy:
    name = ""

    def __init__(self, config: OptimizerConfig) -> None:
        self.config = config
        self.space = ParameterSpace(config)
        if config.strategy.name != self.name:
            raise StrategyError(
                f"Cannot build {self.name!r} from configuration for "
                f"{config.strategy.name!r}."
            )

    def _next_iteration(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None,
        *,
        expected_previous_results: int,
    ) -> tuple[int, tuple[Observation, ...]]:
        main_observations = tuple(
            observation
            for observation in observations
            if observation.optimizer_iteration is not None
        )
        if previous_checkpoint is None:
            if main_observations:
                raise StrategyError(
                    "Main-strategy observations exist, but the previous "
                    "strategy checkpoint is missing."
                )
            return 0, ()

        if previous_checkpoint.strategy != self.name:
            raise StrategyError(
                "Previous checkpoint belongs to a different strategy."
            )
        previous_results = tuple(
            sorted(
                (
                    observation
                    for observation in observations
                    if observation.strategy == self.name
                    and observation.optimizer_iteration
                    == previous_checkpoint.iteration
                ),
                key=lambda observation: observation.run_number,
            )
        )
        if len(previous_results) != expected_previous_results:
            raise StrategyError(
                f"Strategy iteration {previous_checkpoint.iteration} "
                f"requires {expected_previous_results} completed results, "
                f"but {len(previous_results)} are available."
            )
        return previous_checkpoint.iteration + 1, previous_results

    def _next_independent_iteration(
        self,
        previous_checkpoint: StrategyCheckpoint | None,
    ) -> int:
        """Advance strategies that do not need every prior fitness value."""
        if previous_checkpoint is None:
            return 0
        if previous_checkpoint.strategy != self.name:
            raise StrategyError(
                "Previous checkpoint belongs to a different strategy."
            )
        return previous_checkpoint.iteration + 1

    def _batch(
        self,
        *,
        iteration: int,
        parameters: Sequence[Mapping[str, int | float]],
        checkpoint_state: Mapping[str, object],
    ) -> ProposalBatch:
        proposals = tuple(
            StrategyProposal(
                candidate_index=index,
                parameters=dict(parameter_values),
            )
            for index, parameter_values in enumerate(parameters)
        )
        state = {
            **dict(checkpoint_state),
            "proposal_count": len(proposals),
        }
        _validate_json_state(state)
        return ProposalBatch(
            strategy=self.name,
            iteration=iteration,
            proposals=proposals,
            checkpoint_state=state,
        )


class BayesianStrategy(BaseStrategy):
    name = "bayesian"

    def propose(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None = None,
    ) -> ProposalBatch:
        if len(observations) < 2:
            raise StrategyError(
                "Bayesian optimization requires at least 2 observations."
            )
        iteration = self._next_independent_iteration(previous_checkpoint)
        x_scaled = np.asarray(
            [
                self.space.unit_from_parameters(observation.parameters)
                for observation in observations
            ]
        )
        y = _objective_array(observations)
        dimension = self.space.dimension
        options = self.config.strategy.options

        kernel = (
            ConstantKernel(1.0, (1e-3, 1e3))
            * RBF(
                length_scale=np.ones(dimension),
                length_scale_bounds=(1e-2, 10),
            )
            + WhiteKernel(
                noise_level=1e-6,
                noise_level_bounds=(1e-12, 1e1),
            )
        )
        gp = GaussianProcessRegressor(
            kernel=kernel,
            normalize_y=True,
            n_restarts_optimizer=int(options["n_restarts_optimizer"]),
            random_state=self.config.seed,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            gp.fit(x_scaled, y)

        best_y = float(np.min(y))
        exploration_offset = max(float(np.std(y)) * 0.01, 1e-9)

        def expected_improvement(points: np.ndarray) -> np.ndarray:
            matrix = np.asarray(points, dtype=float)
            if matrix.ndim == 1:
                matrix = matrix.reshape(1, -1)
            mean, standard_deviation = gp.predict(matrix, return_std=True)
            improvement = best_y - mean - exploration_offset
            safe_deviation = np.maximum(standard_deviation, 1e-12)
            z = improvement / safe_deviation
            values = (
                improvement * norm.cdf(z)
                + safe_deviation * norm.pdf(z)
            )
            return np.where(standard_deviation > 1e-12, values, 0.0)

        proposal_seed = self.config.seed + iteration + len(observations)
        optimized = differential_evolution(
            lambda point: -float(expected_improvement(point)[0]),
            bounds=[(0.0, 1.0)] * dimension,
            seed=proposal_seed,
            polish=True,
            maxiter=100,
            popsize=8,
        ).x
        candidate_count = int(options["candidate_count"])
        candidates = qmc.LatinHypercube(
            d=dimension,
            seed=proposal_seed,
        ).random(n=candidate_count)
        candidates = np.vstack([optimized, candidates])

        if options["acquisition"] == "ei":
            ranking = np.argsort(expected_improvement(candidates))[::-1]
        else:
            mean, standard_deviation = gp.predict(
                candidates,
                return_std=True,
            )
            random_generator = np.random.default_rng(proposal_seed)
            sampled = mean + standard_deviation * random_generator.normal(
                size=len(candidates)
            )
            ranking = np.argsort(sampled)

        parameters, _ = self.space.unique_parameters(
            candidates[ranking],
            observations=observations,
            required_count=1,
            seed=proposal_seed + 10_000,
        )
        return self._batch(
            iteration=iteration,
            parameters=parameters,
            checkpoint_state={
                "history_size": len(observations),
                "best_objective_value": best_y,
                "acquisition": options["acquisition"],
            },
        )


class RandomStrategy(BaseStrategy):
    name = "random"

    def propose(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None = None,
    ) -> ProposalBatch:
        iteration = self._next_independent_iteration(previous_checkpoint)
        batch_size = self.config.warm_start.sample_count
        seed = self.config.seed + iteration + 1
        candidates = np.random.default_rng(seed).random(
            size=(batch_size, self.space.dimension)
        )
        parameters, _ = self.space.unique_parameters(
            candidates,
            observations=observations,
            required_count=batch_size,
            seed=seed + 10_000,
        )
        return self._batch(
            iteration=iteration,
            parameters=parameters,
            checkpoint_state={"seed": seed},
        )


class SobolStrategy(BaseStrategy):
    name = "sobol"

    def propose(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None = None,
    ) -> ProposalBatch:
        iteration = self._next_independent_iteration(previous_checkpoint)
        batch_size = self.config.warm_start.sample_count
        skip_count = batch_size + iteration * batch_size
        sampler = qmc.Sobol(
            d=self.space.dimension,
            scramble=True,
            seed=self.config.seed,
        )
        sampler.fast_forward(skip_count)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            candidates = sampler.random(n=batch_size)
        parameters, _ = self.space.unique_parameters(
            candidates,
            observations=observations,
            required_count=batch_size,
            seed=self.config.seed + iteration + 10_000,
        )
        return self._batch(
            iteration=iteration,
            parameters=parameters,
            checkpoint_state={
                "sequence_start_index": skip_count,
                "seed": self.config.seed,
            },
        )


class PsoStrategy(BaseStrategy):
    name = "pso"

    def propose(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None = None,
    ) -> ProposalBatch:
        particle_count = self.config.warm_start.sample_count
        options = self.config.strategy.options
        if previous_checkpoint is None:
            warm_start = _warm_start_observations(
                observations,
                particle_count,
            )
            positions = np.asarray(
                [
                    self.space.unit_from_parameters(observation.parameters)
                    for observation in warm_start
                ]
            )
            fitness = _objective_array(warm_start)
            random_generator = np.random.default_rng(self.config.seed)
            velocities = random_generator.uniform(
                low=-0.05,
                high=0.05,
                size=positions.shape,
            )
            pbest_positions = positions.copy()
            pbest_values = fitness.copy()
            best_index = int(np.argmin(pbest_values))
            gbest_position = pbest_positions[best_index].copy()
            gbest_value = float(pbest_values[best_index])
            iteration = 0
        else:
            iteration, previous_results = self._next_iteration(
                observations,
                previous_checkpoint,
                expected_previous_results=particle_count,
            )
            state = previous_checkpoint.state
            positions = _state_array(
                state,
                "particle_positions",
                shape=(particle_count, self.space.dimension),
            )
            velocities = _state_array(
                state,
                "particle_velocities",
                shape=positions.shape,
            )
            pbest_positions = _state_array(
                state,
                "pbest_positions",
                shape=positions.shape,
            )
            pbest_values = _state_array(
                state,
                "pbest_values",
                shape=(particle_count,),
            )
            gbest_position = _state_array(
                state,
                "gbest_position",
                shape=(self.space.dimension,),
            )
            gbest_value = _state_float(state, "gbest_value")
            latest_values = _objective_array(previous_results)
            improved = latest_values < pbest_values
            pbest_values[improved] = latest_values[improved]
            pbest_positions[improved] = positions[improved]
            best_index = int(np.argmin(pbest_values))
            if pbest_values[best_index] < gbest_value:
                gbest_value = float(pbest_values[best_index])
                gbest_position = pbest_positions[best_index].copy()
            random_generator = _restore_rng(state)

        r1 = random_generator.random(positions.shape)
        r2 = random_generator.random(positions.shape)
        velocities = (
            float(options["inertia"]) * velocities
            + float(options["cognitive_weight"])
            * r1
            * (pbest_positions - positions)
            + float(options["social_weight"])
            * r2
            * (gbest_position - positions)
        )
        max_velocity = float(options["max_velocity"])
        velocities = np.clip(velocities, -max_velocity, max_velocity)
        moved_positions = positions + velocities
        boundary_hit = (moved_positions < 0.0) | (moved_positions > 1.0)
        moved_positions = np.clip(moved_positions, 0.0, 1.0)
        velocities[boundary_hit] = 0.0

        parameters, actual_positions = self.space.unique_parameters(
            moved_positions,
            observations=observations,
            required_count=particle_count,
            seed=self.config.seed + iteration + 20_000,
        )
        return self._batch(
            iteration=iteration,
            parameters=parameters,
            checkpoint_state={
                "particle_ids": list(range(particle_count)),
                "particle_positions": actual_positions.tolist(),
                "particle_velocities": velocities.tolist(),
                "pbest_positions": pbest_positions.tolist(),
                "pbest_values": pbest_values.tolist(),
                "gbest_position": gbest_position.tolist(),
                "gbest_value": gbest_value,
                "rng_state": random_generator.bit_generator.state,
            },
        )


class DifferentialEvolutionStrategy(BaseStrategy):
    name = "differential_evolution"

    def propose(
        self,
        observations: Sequence[Observation],
        previous_checkpoint: StrategyCheckpoint | None = None,
    ) -> ProposalBatch:
        population_size = self.config.warm_start.sample_count
        if population_size < 4:
            raise StrategyError(
                "Differential Evolution requires at least 4 individuals."
            )
        options = self.config.strategy.options
        if previous_checkpoint is None:
            warm_start = _warm_start_observations(
                observations,
                population_size,
            )
            population = np.asarray(
                [
                    self.space.unit_from_parameters(observation.parameters)
                    for observation in warm_start
                ]
            )
            fitness = _objective_array(warm_start)
            random_generator = np.random.default_rng(self.config.seed)
            iteration = 0
        else:
            iteration, previous_results = self._next_iteration(
                observations,
                previous_checkpoint,
                expected_previous_results=population_size,
            )
            state = previous_checkpoint.state
            population = _state_array(
                state,
                "population",
                shape=(population_size, self.space.dimension),
            )
            fitness = _state_array(
                state,
                "fitness",
                shape=(population_size,),
            )
            trial_population = _state_array(
                state,
                "trial_population",
                shape=population.shape,
            )
            trial_fitness = _objective_array(previous_results)
            improved = trial_fitness < fitness
            fitness[improved] = trial_fitness[improved]
            population[improved] = trial_population[improved]
            random_generator = _restore_rng(state)

        trial_population = np.zeros_like(population)
        differential_weight = float(options["differential_weight"])
        crossover_probability = float(options["crossover_probability"])
        for individual_index in range(population_size):
            candidates = [
                index
                for index in range(population_size)
                if index != individual_index
            ]
            r1, r2, r3 = random_generator.choice(
                candidates,
                size=3,
                replace=False,
            )
            mutant = population[r1] + differential_weight * (
                population[r2] - population[r3]
            )
            mutant = np.clip(mutant, 0.0, 1.0)
            trial = population[individual_index].copy()
            forced_dimension = int(
                random_generator.integers(self.space.dimension)
            )
            for dimension_index in range(self.space.dimension):
                if (
                    random_generator.random() < crossover_probability
                    or dimension_index == forced_dimension
                ):
                    trial[dimension_index] = mutant[dimension_index]
            trial_population[individual_index] = trial

        parameters, actual_trials = self.space.unique_parameters(
            trial_population,
            observations=observations,
            required_count=population_size,
            seed=self.config.seed + iteration + 30_000,
        )
        return self._batch(
            iteration=iteration,
            parameters=parameters,
            checkpoint_state={
                "individual_ids": list(range(population_size)),
                "population": population.tolist(),
                "fitness": fitness.tolist(),
                "trial_population": actual_trials.tolist(),
                "rng_state": random_generator.bit_generator.state,
            },
        )


def build_strategy(config: OptimizerConfig) -> StrategyAdapter:
    factories = {
        "bayesian": BayesianStrategy,
        "pso": PsoStrategy,
        "differential_evolution": DifferentialEvolutionStrategy,
        "random": RandomStrategy,
        "sobol": SobolStrategy,
    }
    try:
        strategy_class = factories[config.strategy.name]
    except KeyError as error:
        raise StrategyError(
            f"No adapter exists for strategy {config.strategy.name!r}."
        ) from error
    return strategy_class(config)


def observations_from_store(
    store: ExperimentStore,
) -> tuple[Observation, ...]:
    observations: list[Observation] = []
    for run_number in range(1, store.state.completed_runs + 1):
        record = store.load_run(run_number)
        if record.status != "completed":
            raise StrategyError(
                f"Experiment state marks run {run_number} as completed, "
                f"but its stored status is {record.status!r}."
            )
        if record.is_ignored:
            continue
        if record.objective_value is None:
            raise StrategyError(
                f"Completed run {run_number} has no objective value."
            )
        observations.append(
            Observation(
                run_number=run_number,
                parameters=dict(record.parameters),
                objective_value=float(record.objective_value),
                strategy=record.strategy,
                optimizer_iteration=record.optimizer_iteration,
            )
        )
    return tuple(observations)


def _warm_start_observations(
    observations: Sequence[Observation],
    required_count: int,
) -> tuple[Observation, ...]:
    warm_start = tuple(
        sorted(
            (
                observation
                for observation in observations
                if observation.optimizer_iteration is None
            ),
            key=lambda observation: observation.run_number,
        )
    )
    if len(warm_start) < required_count:
        raise StrategyError(
            f"Strategy requires {required_count} completed warm-start "
            f"observations, but {len(warm_start)} are available."
        )
    return warm_start[:required_count]


def _objective_array(
    observations: Sequence[Observation],
) -> np.ndarray:
    values = np.asarray(
        [float(observation.objective_value) for observation in observations],
        dtype=float,
    )
    if not np.all(np.isfinite(values)):
        raise StrategyError("Objective values must be finite.")
    return values


def _numeric_parameters(
    parameters: PrintParameters,
) -> dict[str, int | float]:
    return {
        "top_solid_layers": parameters.top_solid_layers,
        "print_speed": float(parameters.print_speed),
        "extrusion_width": float(parameters.extrusion_width),
        "extrusion_multiplier": float(parameters.extrusion_multiplier),
        "temperature": parameters.temperature,
        "fan_speed": parameters.fan_speed,
    }


def _parameter_key(
    parameters: Mapping[str, int | float],
) -> tuple[object, ...]:
    names = (
        "top_solid_layers",
        "print_speed",
        "extrusion_width",
        "extrusion_multiplier",
        "temperature",
        "fan_speed",
    )
    try:
        return tuple(parameters[name] for name in names)
    except KeyError as error:
        raise StrategyError(
            f"Parameters are missing required value {error.args[0]!r}."
        ) from error


def _checkpoint_proposal_count(checkpoint: StrategyCheckpoint) -> int:
    raw_value = checkpoint.state.get("proposal_count")
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise StrategyError(
            "Previous checkpoint has no valid proposal_count."
        )
    if raw_value < 1:
        raise StrategyError("Checkpoint proposal_count must be at least 1.")
    return raw_value


def _state_array(
    state: Mapping[str, object],
    key: str,
    *,
    shape: tuple[int, ...],
) -> np.ndarray:
    try:
        value = np.asarray(state[key], dtype=float)
    except (KeyError, TypeError, ValueError) as error:
        raise StrategyError(
            f"Checkpoint field {key!r} is missing or invalid."
        ) from error
    if value.shape != shape or not np.all(np.isfinite(value)):
        raise StrategyError(
            f"Checkpoint field {key!r} must have shape {shape}."
        )
    return value.copy()


def _state_float(state: Mapping[str, object], key: str) -> float:
    try:
        value = float(state[key])
    except (KeyError, TypeError, ValueError) as error:
        raise StrategyError(
            f"Checkpoint field {key!r} is missing or invalid."
        ) from error
    if not math.isfinite(value):
        raise StrategyError(f"Checkpoint field {key!r} must be finite.")
    return value


def _restore_rng(
    state: Mapping[str, object],
) -> np.random.Generator:
    raw_state = state.get("rng_state")
    if not isinstance(raw_state, Mapping):
        raise StrategyError("Checkpoint rng_state is missing or invalid.")
    random_generator = np.random.default_rng()
    try:
        random_generator.bit_generator.state = dict(raw_state)
    except (TypeError, ValueError) as error:
        raise StrategyError("Checkpoint rng_state cannot be restored.") from error
    return random_generator


def _validate_json_state(state: Mapping[str, object]) -> None:
    try:
        json.dumps(state, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise StrategyError(
            "Strategy checkpoint state must be JSON serializable."
        ) from error

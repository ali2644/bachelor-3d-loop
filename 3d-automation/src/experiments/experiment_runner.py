from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Protocol

from experiments.experiment_plan import ExperimentPlanEntry
from orchestrator import CycleRequest, CycleResult
from printer.print_parameters import PrintParameters


LOGGER = logging.getLogger(__name__)


class ProfileGeneratorProtocol(Protocol):
    def generate(
        self,
        base_profile_path: str | Path,
        parameters: PrintParameters,
        *,
        output_filename: str | None = None,
    ) -> Path: ...


class PrintOrchestratorProtocol(Protocol):
    def run_single_print_cycle(
        self,
        request: CycleRequest,
    ) -> CycleResult: ...


class ExperimentRunner:
    """Run validated experiment-plan entries as consecutive full cycles."""

    def __init__(
        self,
        orchestrator: PrintOrchestratorProtocol,
        profile_generator: ProfileGeneratorProtocol,
        gcode_directory: str | Path,
    ) -> None:
        self.orchestrator = orchestrator
        self.profile_generator = profile_generator
        self.gcode_directory = Path(gcode_directory)

    def run(
        self,
        experiment_plan: Iterable[ExperimentPlanEntry],
        *,
        stl_path: str | Path,
        base_profile_path: str | Path,
    ) -> tuple[CycleResult, ...]:
        """
        Execute every plan entry in cycle-number order.

        The existing orchestrator remains responsible for one full cycle and
        for recording its result. If a cycle raises an exception, it is kept
        unchanged and the experiment stops before the next entry.
        """
        entries = tuple(
            sorted(
                experiment_plan,
                key=lambda entry: entry.cycle_number,
            )
        )
        if not entries:
            raise ValueError("Experiment plan must not be empty.")

        cycle_numbers = [entry.cycle_number for entry in entries]
        if len(cycle_numbers) != len(set(cycle_numbers)):
            raise ValueError(
                "Experiment plan contains duplicate cycle numbers."
            )

        resolved_stl_path = self._require_file(stl_path, "STL file")
        resolved_base_profile_path = self._require_file(
            base_profile_path,
            "Slicer base profile",
        )
        resolved_gcode_directory = self.gcode_directory.resolve()
        resolved_gcode_directory.mkdir(parents=True, exist_ok=True)

        results: list[CycleResult] = []
        total_cycles = len(entries)

        for position, entry in enumerate(entries, start=1):
            cycle_label = f"cycle_{entry.cycle_number:03d}"
            LOGGER.info(
                "Experiment cycle %s/%s: preparing plan entry %03d.",
                position,
                total_cycles,
                entry.cycle_number,
            )

            generated_profile_path = self.profile_generator.generate(
                resolved_base_profile_path,
                entry.parameters,
                output_filename=f"{cycle_label}_profile.ini",
            ).resolve()
            gcode_path = resolved_gcode_directory / f"{cycle_label}.gcode"

            request = CycleRequest(
                stl_path=resolved_stl_path,
                profile_path=generated_profile_path,
                gcode_path=gcode_path,
                print_parameters=entry.parameters.as_record(),
            )

            try:
                result = self.orchestrator.run_single_print_cycle(request)
            except Exception:
                LOGGER.exception(
                    "Experiment stopped after failed plan entry %03d.",
                    entry.cycle_number,
                )
                raise

            results.append(result)

        return tuple(results)

    @staticmethod
    def _require_file(path: str | Path, description: str) -> Path:
        resolved_path = Path(path).resolve()
        if not resolved_path.is_file():
            raise ValueError(f"{description} not found: {resolved_path}")
        return resolved_path
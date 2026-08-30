# Optimizer framework – step 6: physical orchestrator adapter

`src/optimizer/hardware_executor.py` is the boundary between the generic,
resumable framework and the existing `PrintOrchestrator`. It contains no
device construction and no command-line hardware start. The adapter is tested
with fake orchestrators only in this step.

## Mapping of one saved run

For every persisted `RunRecord`, `OrchestratorRunExecutor`:

1. reconstructs validated `PrintParameters`;
2. creates `run_XXXX_attempt_YY_profile.ini` inside the experiment folder;
3. reserves `run_XXXX_attempt_YY.gcode` inside the experiment folder;
4. constructs a normal `CycleRequest` using the configured STL;
5. calls the existing `run_single_print_cycle(...)` method;
6. accepts finite `Ra` and `Rz` from a completed `CycleResult`;
7. returns them to `FrameworkRunner` as the physical objective result.

The profile generator continues to map the logical optimizer parameters to
the correct PrusaSlicer settings:

| Optimizer value | Slicer setting |
| --- | --- |
| `print_speed` | `top_solid_infill_speed` |
| `extrusion_width` | `top_infill_extrusion_width` |
| `extrusion_multiplier` | `extrusion_multiplier` |
| `temperature` | `temperature` |
| `fan_speed` | minimum, maximum and bridge fan speed |
| `top_solid_layers` | fixed at 5 |

## Conservative failure classification

Only failures known to occur before a possible physical print start may be
repeated with the same saved parameters:

| Stage | Persisted status | Reason |
| --- | --- | --- |
| `preflight` | `retryable_failed` | No print or robot movement started. |
| `slicing` | `retryable_failed` | G-code preparation is still offline. |
| `uploading` or later | `terminal_failed` | Printer or plant state may already have changed. |
| unexpected exception | `terminal_failed` | Physical state is unknown. |

`terminal_failed` means automatic repetition is blocked. It does not mean the
experiment data must be deleted. The plant state and recovery point must first
be checked explicitly.

## Penalty measurements

The current orchestrator can complete a cycle with `Ra=100` and `Rz=100` when
robot handling or QS measurement fails. That behavior remains useful for the
old fixed experiment series, but these values must not teach the optimizer
that the selected process parameters caused poor surface quality.

The adapter therefore rejects any completed `CycleResult` carrying a penalty
error. The framework stores the run as failed with no objective, Ra or Rz.

## Preflight method

`OrchestratorRunExecutor.preflight(run)` generates the run-specific profile
and calls the existing orchestrator preflight. It does not start a print or
move the robot. The later hardware CLI will use this before asking for explicit
confirmation of a new physical optimization experiment.

## Test

```bash
PYTHONPATH=src python tests/test_hardware_executor.py
```

The six tests use temporary files and fake orchestrators. They cover parameter
and path mapping, preflight-only behavior, retry classification, blocking after
a possible print start, rejection of penalty measurements and rejection of
invalid physical measurements.

## Next step

The next component will add an explicit hardware command to `main.py`. It will
construct the real orchestrator with result, image, profile and G-code paths
inside the selected experiment directory. A separate confirmation flag will
be required so that no existing simulation or normal experiment command can
start optimization hardware accidentally.

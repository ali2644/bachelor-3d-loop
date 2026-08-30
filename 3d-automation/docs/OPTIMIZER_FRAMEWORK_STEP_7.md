# Optimizer framework – step 7: guarded hardware CLI

`src/optimizer/hardware_cli.py` is the explicit terminal entry point for the
physical optimization framework. It imports and uses the existing
`main.build_orchestrator` but does not replace or modify `main.py`. This avoids
overwriting the current experiment, camera and resume work in that file.

## Safety gates

A new physical experiment cannot start immediately. The required sequence is:

1. create the experiment with `--new --preflight-only`;
2. persist the first parameter proposal;
3. generate its exact slicer profile and paths;
4. run the existing orchestrator preflight without printing or robot movement;
5. save a preflight receipt tied to experiment ID, run, attempt and parameters;
6. start later with `--resume --confirm-hardware`.

The physical command defaults to one run. More than one physical cycle must be
requested explicitly with `--max-runs`.

## Test only

```bash
PYTHONPATH=src python tests/test_hardware_cli.py
```

The tests inject fake orchestrators. They never import the real device builder,
read credentials, connect to hardware or move the robot.

## Check the command surface

```bash
PYTHONPATH=src python -m optimizer.hardware_cli --help
```

This is also hardware-free.

## Initial hardware preflight

Do not run this until the hardware configuration filename, parameter bounds,
output directory and current plant state have been reviewed.

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --new \
  --preflight-only
```

The command contacts the configured services and checks the robot connection,
but the existing orchestrator preflight does not initialize or move the robot
and does not slice, upload or start a print. A successful result has
`hardware_started: false` and creates the initial preflight receipt.

## First physical run

Only after the preflight result and proposed parameters have been reviewed:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run 1 \
  --max-runs 1 \
  --confirm-hardware
```

The config snapshot must match, run 1 must still be the safe resume point and
the preflight receipt must belong to the same experiment, attempt and
parameters.

## Later resume

After completed runs, the exact safe next run can be supplied:

```bash
PYTHONPATH=src python -m optimizer.hardware_cli \
  config/optimizer_config.hardware.json \
  --resume \
  --from-run 2 \
  --max-runs 1 \
  --confirm-hardware
```

The framework refuses to skip an earlier unfinished run. A retryable failure
also requires `--retry-failed`; terminal failures require plant inspection and
are not bypassed by this CLI.

## Experiment-local storage

The selected `paths.output_directory` contains:

- `results.csv`: accepted optimizer observations;
- `hardware_cycles.csv`: detailed existing-orchestrator records;
- `runs/`: exact run proposal, attempt and state;
- `optimizer_state/`: batch and algorithm checkpoints;
- `generated_profiles/`: run-/attempt-specific slicer profiles;
- `gcode/`: run-/attempt-specific G-code paths;
- `images/`: camera downloads for this experiment;
- `logs/optimizer_hardware.log`: hardware CLI and orchestrator log;
- `logs/initial_hardware_preflight.json`: first-run safety receipt.

## Environment

The existing `main.build_orchestrator` still reads the normal environment
variables, including `PRUSALINK_API_KEY` and `QS_BASE_URL`. The CLI temporarily
sets only the camera download directory to the experiment-local `images/`
folder and restores the previous environment value immediately afterwards.

## Current limit

`history_csvs` remains blocked until a schema-aware import can distinguish
valid measurements, parameter-induced failed prints and infrastructure errors.
It is never silently ignored.

The next step is not a physical run. First create and review a dedicated
`optimizer_config.hardware.json` so the simulation output directory cannot be
reused and the first four or ten warm-start parameters can be inspected before
the initial preflight.

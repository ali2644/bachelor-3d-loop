# Optimizer framework – step 2: persistent experiment state

`src/optimizer/experiment_store.py` persists everything required to determine
the safe resume point after a process crash or computer restart. It performs no
printer, robot or measurement operation.

## Experiment directory

Creating an `ExperimentStore` produces this structure under the configured
`paths.output_directory`:

```text
config_snapshot.json
run_state.json
runs/
optimizer_state/
generated_profiles/
gcode/
logs/
```

- `config_snapshot.json` is the immutable configuration used to create the
  experiment.
- `run_state.json` is a small summary containing experiment ID, status,
  completed-run count and current run.
- `runs/run_XXXX.json` stores the exact quantized proposal and the status of
  one physical run.
- `optimizer_state/*_iteration_XXXX.json` stores one immutable internal
  algorithm checkpoint per iteration.

All JSON replacements use a temporary file followed by `os.replace(...)`.
This prevents a normal interruption during writing from leaving half a JSON
document behind.

## Run lifecycle

```text
proposed -> running -> completed
                   -> retryable_failed -> proposed (same parameters)
                   -> terminal_failed
```

The proposal is written before the hardware loop starts. If run 49 fails, its
parameters remain in `runs/run_0049.json`. A retry increments `attempt_number`
but does not allow the optimizer to generate different parameters for run 49.

A persisted `running` state is deliberately not changed automatically after a
restart. The future CLI must first check the real printer and robot state and
then classify the interruption.

## Resume protection

- Completed runs are never selected again automatically.
- A later run cannot be selected while an earlier run is unfinished.
- An existing proposal cannot be overwritten by a new optimizer proposal.
- Changed configuration is rejected by comparing its SHA-256 fingerprint with
  the saved snapshot.
- Existing output directories are never overwritten.
- The summary state is reconstructed from authoritative per-run files when it
  became stale during an interruption.

## Test

From the `3d-automation` directory:

```bash
PYTHONPATH=src python -m unittest tests/test_experiment_store.py
```

The tests use temporary directories only and do not touch hardware or the real
experiment results.

## Next step

The next component will generate the configured LHS, Random or Sobol warm-start
points and convert every point into validated `PrintParameters`. Each point
will then be handed to `ExperimentStore.propose_run(...)` before any hardware
action is allowed.

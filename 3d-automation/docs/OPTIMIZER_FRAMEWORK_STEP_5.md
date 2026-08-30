# Optimizer framework – step 5: resumable simulation runner

`src/optimizer/framework_runner.py` joins configuration, experiment storage,
warm-start generation and all five strategy adapters. In this step it uses a
deterministic synthetic surface instead of the physical print-measure cycle.
It never imports or contacts printer, robot, camera or quality-station code.

## Safe order for one run

1. Determine the one safe next run number.
2. Persist the warm-start point or complete strategy batch.
3. Persist the individual run proposal.
4. Mark the run as running.
5. Ask the selected executor for a measurement.
6. Persist Ra, Rz and the objective value.
7. Atomically rebuild `results.csv` from the authoritative run JSON files.

The framework batch is saved inside the immutable strategy checkpoint before
its first run starts. A restart in the middle of PSO, Differential Evolution,
Random or Sobol therefore continues with the exact remaining parameter sets.

## First simulation segment

Run from the `3d-automation` directory:

```bash
PYTHONPATH=src python -m optimizer.framework_runner \
  config/optimizer_config.simulation.json \
  --simulate \
  --new \
  --max-runs 6
```

This creates a separate simulation directory and completes runs 1 through 6.
The first four runs are LHS warm-start points; runs 5 and 6 are Bayesian
proposals.

## Resume the same experiment

```bash
PYTHONPATH=src python -m optimizer.framework_runner \
  config/optimizer_config.simulation.json \
  --simulate \
  --resume \
  --from-run 7
```

The configuration snapshot must still match and run 7 must be the first safe
unfinished run. The command refuses an attempt to skip an earlier run.

## Persisted output

The configured output directory contains:

- `config_snapshot.json`: immutable normalized configuration;
- `run_state.json`: short current status summary;
- `runs/run_XXXX.json`: exact proposal, attempt and result for every run;
- `optimizer_state/*_iteration_XXXX.json`: complete batch and algorithm state;
- `results.csv`: readable table rebuilt after every successful run.

## Interrupted and failed runs

- A `proposed` run is safely executed on resume.
- A `retryable_failed` run is repeated only with the explicit
  `--retry-failed` option and keeps exactly the same parameters.
- A persisted `running` run is not repeated automatically. Real printer and
  robot state must first be checked and classified.
- A terminal failure blocks automatic continuation.

## Test

```bash
PYTHONPATH=src python tests/test_framework_runner.py
```

The test runs all five strategies only against temporary synthetic
experiments. It also covers checkpoint-before-execution, PSO resume in the
middle of a batch, explicit retry and refusal to skip or repeat unsafe runs.

## Deliberate limits of step 5

- `history_csvs` import is rejected instead of being silently ignored.
- No physical executor is connected yet.
- A run found in state `running` requires an explicit recovery decision.

The next step will map the existing `PrintOrchestrator` result and classified
`CycleExecutionError` into this tested runner interface.

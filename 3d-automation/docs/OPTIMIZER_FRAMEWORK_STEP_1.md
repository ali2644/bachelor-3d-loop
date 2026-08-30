# Optimizer framework – step 1: configuration

The optimizer framework is configured by one JSON file. This separates user
choices from Python source code and gives every resumed experiment a complete,
reproducible description.

## Files

- `src/optimizer/config.py` loads and validates the JSON file.
- `config/optimizer_config.example.json` is a runnable example configuration.
- `tests/test_optimizer_config.py` checks accepted and rejected settings.

## Configuration flow

1. `load_optimizer_config(...)` reads the JSON file.
2. Unknown or missing fields are rejected instead of being ignored.
3. Strategy aliases such as `BO` and `de` are converted to canonical names.
4. Parameter bounds are checked against the currently supported process
   limits.
5. Relative paths are resolved relative to the JSON file's directory.
6. A frozen `OptimizerConfig` object is returned to the later runner.

No printer, robot or measurement is started in this step.

## Important fields

- `total_runs`: complete number of physical print-measure runs, including the
  warm start.
- `warm_start.method`: `lhs`, `random` or `sobol`.
- `warm_start.sample_count`: number of initial physical runs.
- `strategy.name`: `bayesian`, `pso`, `differential_evolution`, `random` or
  `sobol`. `BO` and `de` are accepted aliases.
- `parameters`: variables that the selected strategy may change.
- `fixed_parameters`: values that remain constant in every run.
- `paths.output_directory`: root directory for results and state files that
  the experiment-store step will create later.
- `paths.history_csvs`: optional earlier result files used as real history.

The loader currently requires `top_solid_layers` to remain fixed at `5`,
matching the current hardware experiment and the current print pipeline. We
will remove that guard only if this parameter is deliberately enabled again in
`PrintParameters` and the slicer-profile generator.

## Validate the example

From the `3d-automation` directory:

```bash
PYTHONPATH=src python -m optimizer.config \
  config/optimizer_config.example.json
```

This prints the normalized configuration and does not touch hardware. Add
`--check-input-files` only when the configured STL, slicer profile and history
CSV files are present on the target computer.

## Next step

The next component will create the experiment directory and persist the
configuration, proposed run and run status atomically. This state layer is
required before any of the five strategies may control real hardware.

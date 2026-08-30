# Optimizer framework – step 3: warm-start generation

`src/optimizer/warm_start.py` converts the selected JSON configuration into a
deterministic sequence of physical start experiments. It supports Latin
Hypercube Sampling (`lhs`), uniform random sampling (`random`) and scrambled
Sobol sampling (`sobol`).

## Data flow

1. Read variable names, bounds, fixed values, method, sample count and seed
   from `OptimizerConfig`.
2. Generate points in a normalized unit cube.
3. Scale each dimension to its configured lower and upper bound.
4. Quantize values using the project's parameter rules.
5. Construct `PrintParameters`, which performs the final process validation.
6. Remove duplicates created by quantization and generate replacements.
7. Before hardware starts, persist the current point with
   `ExperimentStore.propose_run(...)`.

## Reproducibility

The same method, seed, bounds and fixed values produce the same ordered plan.
The full experiment configuration is immutable after the `ExperimentStore` is
created. An already persisted run proposal always takes priority over a newly
regenerated plan.

## Preview without hardware

From the `3d-automation` directory:

```bash
PYTHONPATH=src python -m optimizer.warm_start \
  config/optimizer_config.example.json
```

The command only prints the plan as JSON. It does not create an experiment
directory and does not contact printer, robot, camera or quality station.

## Test

```bash
PYTHONPATH=src python tests/test_warm_start.py
```

The tests cover all three methods, deterministic seeds, bounds, integer
rounding, fixed parameters, uniqueness, insufficient discrete parameter-space
capacity and persistence of the next point before hardware execution.

## Next step

The next component will define one common strategy interface and adapters for
Bayesian Optimization, PSO, Differential Evolution, Random and Sobol. The
runner can then switch strategies using only `strategy.name` in the JSON file.

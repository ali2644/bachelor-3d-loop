# Optimizer framework – step 8: hardware configuration draft

`config/optimizer_config.hardware.draft.json` is a separate commissioning
configuration for the first offline review and later hardware preflight. It
does not reuse the completed simulation directory and does not import the
existing 100-cycle experiment.

This file is deliberately named `draft`: its parameter bounds and experiment
size still require scientific approval before a physical optimization series.

## What this draft describes

The draft contains 12 runs:

- runs 1–10: deterministic LHS warm start;
- runs 11–12: Bayesian Optimization using the measured `Ra_um` values;
- objective: minimize `Ra_um`;
- fixed value: `top_solid_layers = 5`;
- random seed: 42, so the offline warm-start plan is reproducible.

`total_runs: 12` is only a small commissioning experiment. It verifies the
transition from warm start to Bayesian Optimization without declaring that the
scientific 100-run design has been decided. The hardware CLI still defaults to
one physical cycle per invocation.

## Parameter space to review

| Parameter | Lower bound | Upper bound |
|---|---:|---:|
| `print_speed` | 50 | 90 |
| `extrusion_width` | 0.38 | 0.50 |
| `extrusion_multiplier` | 1.05 | 1.20 |
| `temperature` | 215 | 235 |
| `fan_speed` | 30 | 80 |

The framework quantizes `temperature` and `fan_speed` to integers. The other
variables keep their supported decimal precision before they become
`PrintParameters`.

## Why existing history is empty

```json
"history_csvs": []
```

The existing 100-cycle CSV is not silently imported. Its schema, validity
flags, failure meaning and parameter ranges must first be mapped explicitly.
Infrastructure failures must never become bad `Ra` training observations.

## Offline checks only

The following commands neither connect to the printer nor move the robot.

First validate and resolve the paths:

```bash
PYTHONPATH=src python -m optimizer.config \
  config/optimizer_config.hardware.draft.json \
  --check-input-files
```

Then display the exact ten LHS points:

```bash
PYTHONPATH=src python -m optimizer.warm_start \
  config/optimizer_config.hardware.draft.json
```

Review every point before a hardware preflight. Do not run
`optimizer.hardware_cli` during this step.

## How the file will later be used

The configuration loader validates the schema, bounds and strategy options.
The warm-start generator creates the first ten physical parameter proposals.
The experiment store copies the configuration into the new experiment
directory and persists each proposal before hardware starts. After ten valid
`Ra_um` observations, the Bayesian strategy fits its Gaussian-process model
and proposes runs 11 and 12.

Changing the config after creating the experiment changes its hash. Resume is
then rejected intentionally so an experiment cannot continue with unnoticed
different bounds or settings.

## Before the first hardware preflight

Confirm these points:

1. The five lower and upper bounds are approved for the real process.
2. The STL and base profile are the intended production inputs.
3. The output directory is new and correctly named.
4. The first ten generated parameter sets are physically acceptable.
5. It is clear whether the final scientific experiment contains 100 total
   runs or starts only after a separate 100-run dataset.

Only after those checks should the draft be renamed to
`optimizer_config.hardware.json` and used for the guarded preflight from step
7.

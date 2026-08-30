# Optimizer framework – step 4: common strategy adapters

`src/optimizer/strategies.py` gives all configured main strategies the same
interface. It performs calculations only and never contacts hardware or writes
experiment files.

## Common input and output

Every adapter receives:

- completed `Observation` values containing parameters and objective values;
- the previous immutable `StrategyCheckpoint`, when one exists.

Every adapter returns one `ProposalBatch` containing:

- canonical strategy name;
- optimizer iteration number;
- one or more quantized, validated parameter proposals;
- JSON-serializable state for the next checkpoint.

## Strategy behavior

- Bayesian Optimization returns one proposal. The Gaussian process is rebuilt
  from all valid observations and therefore does not serialize the sklearn
  model object.
- Random and Sobol return one batch with the configured warm-start sample
  count, matching the supervisor prototype.
- PSO stores particle positions, velocities, personal/global best values and
  the NumPy random-generator state.
- Differential Evolution stores population, fitness, trial population and
  random-generator state.

PSO and Differential Evolution refuse to create the next batch until every
result of the previous batch is complete.

## Parameter safety

All adapters work internally in the normalized range 0 to 1. Before a proposal
is returned, it is:

1. transformed to the configured physical bounds;
2. quantized using the shared parameter definition;
3. validated through `PrintParameters`;
4. checked against all previously evaluated parameter sets and the other
   proposals in the same batch.

## Test

```bash
PYTHONPATH=src python tests/test_strategies.py
```

The test uses synthetic objective values. It does not create a real experiment
directory and does not contact hardware.

## Next step

The next component will persist a returned checkpoint and batch, execute one
proposal at a time through the existing orchestrator, and feed only valid
physical results back as observations. This is the new framework runner.

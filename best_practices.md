# Best Practices for Agents Working on This Repo

This project is a CPU-heavy Python data pipeline over large UN Comtrade bulk
files. Most runtime comes from reading many compressed CSV files, filtering
HS6 records, grouping large tables, and running simulation benchmarks. The
fastest path is usually better data layout and execution strategy, not a full
rewrite in another language.

## First Principles

- Read the existing pipeline before changing it. The main logic lives in
  `scripts/trade_concentration_pipeline.py`, with specialized runners such as
  `scripts/run_exercises_02_12.py`, `scripts/run_exercise_12_checkpointed.py`,
  and `scripts/exercise10_hs2_benchmark.py`.
- Preserve the research contract. Do not replace real HS6 reporter-product-
  partner trade values with inferred, sampled, or non-equivalent data unless a
  script is explicitly in debug mode.
- Prefer small, resumable improvements over large rewrites. This repo already
  has checkpointing patterns; extend them before introducing new architecture.
- Optimize after measuring. Guessing at bottlenecks often leads to complicated
  code that does not make the slow part faster.
- Keep outputs reproducible. Fixed seeds, manifests, clear parameters, and
  stable output paths matter for empirical work.

## What Usually Makes This Faster

### 1. Avoid repeated full raw-data scans

The raw Comtrade folder is large. Re-reading every `.gz` file for each exercise
is expensive.

Preferred pattern:

1. Read each raw file once.
2. Normalize and filter to leaf HS6 import/export partner records.
3. Write typed Parquet partitions.
4. Run analysis from those Parquet partitions.

Good partition keys are usually:

- `reporter_code`
- `year`
- possibly `flow`

Avoid writing one giant CSV as an intermediate. Parquet is faster, smaller, and
keeps column types.

### 2. Use faster data engines before changing languages

Python is not automatically the problem. Pandas and NumPy already execute many
operations in compiled code. For this repo, better engines are usually:

- DuckDB: best for SQL-shaped scans, joins, filters, and groupbys over Parquet.
- Polars: good for lazy DataFrame pipelines and parallel groupbys.
- PyArrow: good for schema control, Parquet writing, and columnar IO.

Use DuckDB or Polars when the task is mostly:

- filter rows
- select columns
- group by keys
- aggregate numeric columns
- join metadata
- scan many Parquet files

Keep pandas when the data is already small, the code is clearer, or the work is
plotting/report generation.

### 3. Process independent files in parallel

The raw Comtrade files are independent. Per-file aggregation is a natural unit
of work.

Preferred pattern:

- Use `ProcessPoolExecutor` for CPU-heavy parsing/grouping work.
- Use `ThreadPoolExecutor` mainly for network downloads or IO-bound work.
- Write one partial output per raw file.
- Make the runner resumable by skipping existing valid partials.
- Finalize by combining partials, not by holding everything in memory.

Do not parallelize by having many workers append to the same CSV. That creates
corruption and locking problems. Write separate partial files, then combine.

### 4. Keep checkpointing

Long runs should survive interruption.

Good checkpoint files:

- are deterministic from the raw input filename
- can be validated cheaply
- are safe to skip on resume
- include enough columns and types to finalize without re-reading raw data

`scripts/run_exercise_12_checkpointed.py` is a useful model: it writes per-file
aggregate Parquet files and later finalizes from them.

### 5. Reduce memory pressure

Avoid building massive lists of DataFrames and concatenating them at the end
unless each frame is known to be small.

Better options:

- write per-file Parquet partials
- stream chunks into aggregate tables
- aggregate early, then store smaller grouped results
- keep only necessary columns from raw files
- downcast types when safe, for example integer reporter/year codes
- avoid `.copy()` on huge frames unless needed to prevent chained assignment or
  mutation bugs

### 6. Use simulations carefully

Exercise 10 simulations can be a real CPU hotspot.

For draft or debugging runs:

```bash
python scripts/exercise10_hs2_benchmark.py --simulations 100 --max-files 10
```

For final runs, use the intended simulation count and checkpointing:

```bash
python scripts/exercise10_hs2_benchmark.py --simulations 1000
```

When optimizing simulation code:

- Keep the statistical null unchanged.
- Keep the random seed behavior reproducible.
- Prefer vectorized NumPy over Python loops.
- Consider Numba only for small hot numeric kernels after profiling.
- Do not change approximation logic without updating validation and memos.

## Profiling Checklist

Before making performance changes, capture a small benchmark:

```bash
time python scripts/run_exercises_02_12.py 10
time python scripts/run_exercise_12_checkpointed.py --max-files 10 --fresh
time python scripts/exercise10_hs2_benchmark.py --max-files 10 --simulations 100 --fresh
```

For function-level profiling:

```bash
python -m cProfile -o profile.out scripts/run_exercises_02_12.py 10
```

Then inspect with a profile viewer or summarize in Python. Optimize the top
few functions by cumulative time, not the most visible code.

Track:

- wall-clock runtime
- peak memory
- number of raw files processed
- rows read
- rows written
- output row counts
- whether results match previous outputs on a small fixture

## Implementation Patterns

### Prefer column pruning

When reading CSVs or Parquet, load only columns needed by the task. For raw
Comtrade files, common required fields are:

- reporter code
- period/year
- partner code
- commodity code
- flow
- primary/trade value
- classification code when relevant
- aggregate flag when present

### Normalize once

Column-name normalization is useful, but doing it repeatedly across many
stages wastes time and can hide schema drift. Normalize at ingestion, then use
canonical internal names.

Canonical names used in this repo include:

- `reporter_code`
- `year`
- `partner_code`
- `cmd_code`
- `flow`
- `trade_value`
- `classification_code`
- `hs2`

### Aggregate early

For many exercises, raw HS6 partner rows can be collapsed early into smaller
tables. For example:

- product totals: `reporter_code`, `year`, `flow`, `cmd_code`
- partner totals: `reporter_code`, `year`, `flow`, `partner_code`
- cell totals: `reporter_code`, `year`, `flow`, `cmd_code`, `partner_code`

Only keep the raw leaf-level table when a later step truly needs it.

### Validate optimized paths against old paths

For any speed rewrite, compare old and new outputs on a small subset:

```bash
python scripts/run_exercises_02_12.py 5
```

Then verify:

- same row counts where expected
- same key coverage
- numeric differences are zero or explainable floating-point noise
- generated memos/figures still build

Use strict comparisons for IDs and categories. Use tolerances only for floating
point metrics.

## Language Choices

Do not recommend a full rewrite just because Python is slow on CPU. Use this
decision order:

1. Better file format and caching: Parquet partitions.
2. Better query engine: DuckDB or Polars.
3. Better parallelism: process raw files independently.
4. Better numerical kernels: vectorized NumPy or Numba.
5. Compiled extensions: Rust/C++ only for isolated, proven hotspots.
6. Full rewrite: only if the whole project becomes a long-lived production
   system with clear maintenance owners.

Reasonable roles:

- Python: orchestration, plotting, reports, reproducibility glue.
- DuckDB: large scans, groupbys, joins, Parquet queries.
- Polars: lazy columnar DataFrame pipelines.
- NumPy: vectorized simulations and numeric metrics.
- Numba: tight custom loops after profiling.
- Rust/C++: small kernels or external tools only when profiling justifies it.

## Safety Rules for Agents

- Do not delete existing data or checkpoints unless the user explicitly asks.
- Do not overwrite canonical result files during experiments unless the script
  has a clear opt-in flag such as `--write-main`.
- Do not silently change the sample, countries, years, flow definitions, HS
  level, or exclusion rules.
- Do not weaken validation to make a run pass.
- Do not hide failed downloads or partial data as valid final results.
- Keep debug limits such as `--max-files` visible in manifests and memos.
- If a run uses fewer simulations or fewer files, label it as a debug run.

## Good Next Improvements

High-value improvements for this repo:

- Add a one-time raw-to-Parquet ingestion script for clean HS6 leaf records.
- Add a DuckDB version of the common aggregation layer.
- Parallelize `run_exercise_12_checkpointed.py` per raw file.
- Add a lightweight benchmark script that runs 5-10 files and compares output
  row counts/numeric summaries.
- Add schema validation for partial Parquet outputs.
- Add clearer manifests for CPU/debug/final runs.
- Add a short README section explaining which runner to use for each exercise.

## Quick Guidance for Future Agents

If the user says the code is slow, do not immediately rewrite it in another
language. First check whether the task is repeatedly scanning raw compressed
CSV files. If yes, move toward Parquet checkpoints, DuckDB/Polars aggregation,
and per-file multiprocessing. That is the most likely path to a real speedup
with the least risk to the empirical results.

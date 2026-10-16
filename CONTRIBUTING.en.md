# Contributing

[中文](CONTRIBUTING.md)

## Environment

Python 3.10 or newer and [uv](https://docs.astral.sh/uv/) are required. Install a `jsonnet` executable when you use `JsonnetToPrompt`.

```bash
uv sync --group dev
uv run ruff check
uv run pytest
```

`tests/test_contract.py` holds the contract tests for scheduling behaviour. When you change how entities, the comparison, clearing, retry, or sources behave, add a case there first. `make quality` and CI also run scripts under `examples/`, which are not in the repository yet.

## Where to change things

The runtime is in `src/docorder/`. `core/` holds entities, jobs, operators, and stage scheduling. `functions/` holds the source, map, reduce, and fanout base classes. Built-in implementations are in `functions/impl/`. `utils/` holds errors, module loading, home search, and retry.

Operator homes live in directories listed by `DOCORDER_HOMES`. They are not installed with the package. The path separator is the same as for `PATH`, and a directory earlier in the list wins. Prefer an existing function for a new transform. When the existing types cannot express it, implement the function base class that matches `type` in `props.json`, put the class in the home's `primary.py`, and set `class` to `primary:ClassName`. The runner owns retry and the thread pool. Do not build another copy inside the function. Chapter 6 of [docs/functions.en.md](docs/functions.en.md) shows how.

## Submitting

Contributions are released under the [MIT license](LICENSE). State the reason in the commit message. Do not commit secrets, access tokens, `runs/`, or real business data.

Record behavior changes in the Unreleased section of `CHANGELOG.md`. When a document changes, change the Chinese file and the `.en` file of the same name together. Run the commands and example code in a document on your machine before you submit it.

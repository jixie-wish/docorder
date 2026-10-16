# Docorder

[![CI](https://github.com/jixie-wish/docorder/actions/workflows/ci.yml/badge.svg)](https://github.com/jixie-wish/docorder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

[中文](README.md)

Docorder is a Python library for running several transform steps over a batch of objects that share one shape, for example rendering a prompt for every table and then calling a model on it. Each object is a directory on disk, called an entity. Transforms run stage by stage along a directed acyclic graph: one operator finishes the whole batch before its downstream starts. When a run is interrupted, run the same epoch again. Each entity's `tag.json` records the upstream it read, and the runner uses it to finish only what is missing, redo what changed upstream, and delete what is no longer expected.

A job is built in Python and started with `execute`. There is no working command-line entry point yet.

## Getting the code

```bash
git clone https://github.com/jixie-wish/docorder.git
cd docorder
```

The repository has no submodules and does not use Git LFS.

## Prerequisites

- [Python](https://www.python.org/downloads/) 3.10 or newer. `pyproject.toml` requires `>=3.10`, and CI runs on 3.10 and 3.12.
- [uv](https://docs.astral.sh/uv/getting-started/installation/). Install, tests, and lint all go through it. The commands on this page were checked with uv 0.8.14.

Check both:

```bash
python3 --version
uv --version
```

These external programs are needed only by the function that uses them:

- `JsonnetToPrompt` calls `jsonnet` on `PATH`. CI on Ubuntu installs it with `sudo apt-get install -y jsonnet`.
- `Command` and `PromptToLLM` run the commands you write in their configuration, so those commands must exist on the machine. The package ships no model tool presets.

## Install

From the repository root:

```bash
uv sync
```

This creates `.venv` and installs the library with its runtime dependencies, Jinja2 and PyYAML. To run the tests and Ruff, use `uv sync --group dev` instead.

> [!IMPORTANT]
> There is no `docorder` project on PyPI, so `pip install docorder` does not work. Install from the cloned repository.

## Quick start

The script below builds a two-stage job. A source turns every file in a directory into an entity, and a map renders one line of text for each entity with a Jinja template. It only needs Jinja2, which the install provides.

Save this as `quickstart.py` in the repository root:

```python
import json
import os
from pathlib import Path

from docorder.core.job import Job
from docorder.core.runner import execute


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    root = Path("quickstart").resolve()
    notes = root / "notes"
    hello = notes / "hello"
    hello.mkdir(parents=True, exist_ok=True)
    (hello / "data").write_text("hello\n", encoding="utf-8")
    (hello / "tag.json").write_text("{}\n", encoding="utf-8")

    homes = root / "homes"
    write_json(
        homes / "notes_source" / "props.json",
        {
            "type": "source",
            "class": "docorder.functions.impl.directory_source:DirectorySource",
            "directory": str(notes),
        },
    )
    write_json(
        homes / "prompt" / "props.json",
        {
            "type": "map",
            "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
            "template": "lib/note.jinja",
        },
    )
    (homes / "prompt" / "lib").mkdir(parents=True, exist_ok=True)
    (homes / "prompt" / "lib" / "note.jinja").write_text("Note: {{ data }}", encoding="utf-8")

    os.environ["DOCORDER_HOMES"] = str(homes)
    job = Job("quickstart", root / "runs")
    job.add_operator_node("notes", "notes_source")
    job.add_operator_node("prompt", "prompt", upstream="notes")
    execute(job, "demo", start_from_scratch=True)

    output = root / "runs" / "prompt" / "demo" / "hello" / "data"
    print(output.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
```

Run it:

```bash
uv run python quickstart.py
```

On success it prints:

```text
Note: hello
```

After the run, `quickstart/runs/` looks like this:

```text
quickstart/runs/
  notes/                    source node
    .docorder-output
    demo/hello/
      data                  "hello\n"
      tag.json              from the input entity's tag.json
  prompt/                   map node
    .docorder-output
    demo/hello/
      data                  "Note: hello\n"
      tag.json              includes upstream: node notes, entity hello, epoch demo, sha256 of the upstream body
```

The entity name `hello` is the name of the input directory `notes/hello`. `demo` is the epoch of this run, and also the name of the directory level that holds the entities.

> [!NOTE]
> The script puts its work in `main()` and calls it under `if __name__ == "__main__":`. That is ordinary script style. When `parallelism` is greater than 1, the runner slices the work across threads in the current process and does not start worker processes.

## Configuration

### Operator homes

An operator home is a directory whose `props.json` declares the operator's type, its function class, and its parameters. Homes are not shipped with the package. Before a run, list the directories that contain your homes in the `DOCORDER_HOMES` environment variable. Separate several directories with the system path separator, as for `PATH`. An earlier directory wins when two homes share a name. A home may sit directly in a listed directory, or one category directory below it.

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "parallelism": 4,
  "retry": { "max_attempts": 3, "backoff_seconds": 5 },
  "template": "lib/prompt.jinja"
}
```

`type` is one of `source`, `map`, `reduce`, `fanout`, and `output`. `class` is `module:Class`, or `primary:Class` when the class lives in the home's own `primary.py`. A job cannot change these two. `parallelism` defaults to 1, and `retry` defaults to a single attempt. Every other key is a function parameter. The parameters each function accepts are in [docs/functions.en.md](docs/functions.en.md). An `output` node writes upstream bodies as files under `.job_result` at the job root.

### Jobs

The second argument of `Job(name, root)` is the output root. `add_operator_node(node_name, home_name, upstream=..., config=..., parallelism=..., retry=...)` adds a node. A node writes to `output-root/node-name/epoch/entity-name/`. Every node except a source declares exactly one upstream, as a string.

`config` overrides same-named function parameters from the home. Override scheduling with the `parallelism=` and `retry=` arguments. Keys of the same name inside `config` only become function parameters and do not change scheduling. `retry=` takes `docorder.utils.retry.RetryPolicy(max_attempts=..., backoff_seconds=...)`. Adding a node name a second time replaces the earlier node without an error.

### Running

`execute(job, epoch, start_from_scratch=False)` runs the whole graph in topological order. `epoch` is joined into paths as is, so use a single directory name such as a date. A source rereads its input only when `start_from_scratch=True`. Otherwise the source leaves its output alone, and downstream stages read the entities already in that epoch. Each stage prints a progress bar on stderr, titled with the operator name.

| Environment variable | Purpose |
| --- | --- |
| `DOCORDER_HOMES` | Directories searched for operator homes. Set it before `add_operator_node`. |
| `DOCORDER_LLM` | The tool `PromptToLLM` uses when `tool` is not configured: a preset name in the home, or a path to a JSON file. |

## Example: running the same epoch again

After the quick start, save `rerun.py`. It reuses the homes and output under `quickstart/`, edits the source file, and runs the same epoch twice:

```python
import os
from pathlib import Path

from docorder.core.job import Job
from docorder.core.runner import execute


def main() -> None:
    root = Path("quickstart").resolve()
    os.environ["DOCORDER_HOMES"] = str(root / "homes")
    job = Job("quickstart", root / "runs")
    job.add_operator_node("notes", "notes_source")
    job.add_operator_node("prompt", "prompt", upstream="notes")
    output = root / "runs" / "prompt" / "demo" / "hello" / "data"

    (root / "notes" / "hello" / "data").write_text("changed\n", encoding="utf-8")
    execute(job, "demo")
    print(output.read_text(encoding="utf-8"), end="")
    execute(job, "demo", start_from_scratch=True)
    print(output.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
```

```bash
uv run python rerun.py
```

Output:

```text
Note: hello
Note: changed
```

The first call does not regenerate from scratch, so the source entity still holds the old body. The snapshot in `prompt/demo/hello` still matches its upstream, and the entity is kept as it is. The second call makes the source reread the file. The upstream body hash changes, so `prompt` clears that entity and renders it again. The runner compares only upstream bodies. An entity whose template or parameters changed while its upstream body stayed the same is not redone automatically. To force a redo, delete that entity directory, or use another epoch. The full rules are in [docs/design.en.md](docs/design.en.md).

Delete `quickstart/`, `quickstart.py`, and `rerun.py` when you are done.

Reduce and fanout have no ready-made functions. You implement them in a home's `primary.py`. The last chapter of [docs/functions.en.md](docs/functions.en.md) has two examples that run as written.

## Troubleshooting

| What you see | Cause and fix |
| --- | --- |
| `FileNotFoundError: operator home '…' not found in: …` | `DOCORDER_HOMES` does not point at a directory that contains that home, or that directory has no `props.json`. Set the variable before `add_operator_node`. |
| `FatalError: refuse to use … as an operator output` | The node's output directory already has files and no `.docorder-output` marker. The runner will not overwrite it. Use another output root, or another node name. |
| `FatalError: directory source path is not a directory` | `directory` points at a directory that does not exist. A relative path is resolved from the operator home, not from the current directory. |
| `FatalError: jsonnet is not on PATH` | `JsonnetToPrompt` cannot find `jsonnet` on this machine. This kind of error is not retried. |
| `DocorderError: command did not write …` | `output_file` of `Command` is a relative path. Docorder looks for it from the Python process's current directory, not from `cwd`. Use an absolute path, or `{entity.output}/file-name`. |
| A source file changed, but downstream did not | That `execute` call did not pass `start_from_scratch=True`, so the source did not reread its input. |
| A template changed, but the old result stayed | The upstream body did not change, so the snapshot still matches. Delete the node's `<epoch>/` directory or some entity directories in it, or use another epoch. |
| One entity is redone on every run | Its upstream body is an empty string. An empty body is recorded with an empty hash, and the comparison never passes. |
| Want to see which epochs an output root contains | `docorder status <output-root>`. It reports whether each epoch matches its upstream snapshots, and how many entities each stage has. A missing directory exits with status 1. |

`FatalError` means the configuration or the input is wrong. It is not retried. Examples are a missing parameter, a template variable that does not exist, and a missing executable. Other exceptions retry the current entity according to `retry`. When the attempts run out, the run stops at the current operator. Entities that already have `upstream` in `tag.json` stay on disk, and the next run of the same epoch continues with the rest. `JobValidationError` is raised before any operator runs and means the job graph itself is wrong, for example a cycle, an upstream that is not in the graph, or a node that depends on itself.

## Testing

This repository has no separate build or deploy step. During development, run:

```bash
uv sync --group dev
uv run ruff check
uv run pytest
```

`ruff check` lints the whole repository, and `pytest` runs `tests/`. `make quality` and CI also refer to scripts under `examples/`. Those scripts are not in the repository yet, so those two fail when run locally.

## Documentation

- [docs/functions.en.md](docs/functions.en.md): each function's parameters, template variables, and how to implement a function in a home.
- [docs/design.en.md](docs/design.en.md): what entities, operators, and jobs each hold, what one run writes to disk, and how the same epoch is judged on another run.
- [glossary.en.md](glossary.en.md): the terms the documents use.
- [docs/index.en.html](docs/index.en.html): the project introduction page.

Chinese pages use the same names without the `.en` suffix, for example `README.md` and `docs/design.md`.

## Contributing

Report bugs and request features in [GitHub Issues](https://github.com/jixie-wish/docorder/issues). The repository has bug and feature templates. Do not report security issues publicly. See [SECURITY.en.md](SECURITY.en.md). Conventions are in [CONTRIBUTING.en.md](CONTRIBUTING.en.md), and the code of conduct is in [CODE_OF_CONDUCT.en.md](CODE_OF_CONDUCT.en.md). The API may change during `0.x`. Changes are recorded in [CHANGELOG.en.md](CHANGELOG.en.md).

> [!WARNING]
> `JsonnetToPrompt`, `Command`, and `PromptToLLM` run content from the job configuration and from entity bodies on the local machine. Run a job only on directories you trust.

## License

[MIT](LICENSE).

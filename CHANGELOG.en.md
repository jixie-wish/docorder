# Changelog

[中文](CHANGELOG.md)

This file follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers follow Semantic Versioning.

## [Unreleased]

- `tag.json` no longer records `current`. A downstream snapshot is taken from the live upstream body and user tag. Editing an already written entity's `data` or `tag.json` redos dependents on the next run.
- `PromptToLLM` keeps a `data` file the tool wrote into the target entity. After checking that it is non-empty UTF-8 text, only `tag.json` is written. Without that file, the body is still standard output.
- The upstream snapshot now lives in `tag.json` as `upstream`. `upstream.json` is no longer written, and a leftover file is deleted on persist.
- Each stage prints a progress bar on stderr, titled with the operator name. Map, fanout, reduce, and output know the count for this run; a source advances as `emit` yields.
- `DirectorySource` reads child directories that already look like entities: the directory name is the entity name, the body comes from `data`, and the tag comes from `tag.json`. Loose files and incomplete directories are skipped.
- Add an `output` operator. `.job_result` under the job root is the overall job output. An output node writes each upstream entity's body for this epoch as a file there. The file name defaults to the entity name, or `name_template` rendered with the entity tag. `directory` selects another destination; a relative path is resolved from the operator home.
- `LLMTool` moves to `docorder.utils.llm_tool`.
- `Artifact` and `Environment` move to `docorder.core`.
- Built-in functions move to `docorder.functions.impl`. Base classes are renamed to `source_function`, `map_function`, `reduce_function`, `fanout_function`, and `rendered_map`. Write the new module path in `props.json` `class`.
- `Environment` now has only `operator_props` (function parameters) and `template_env` (`operator` / `job` / `entity` for templates). `config`, `bind`, `namespace`, `bindings`, and `format_named` are gone.
- Map and fanout `parallelism` now uses a thread pool instead of a process pool. The slice threads share the operator, so parameters need not be picklable, and the starting script no longer needs `if __name__ == "__main__":` for this.
- `OperatorNode` applies the node's `config` onto `props` at construction and then drops `config`; the public object is `props`. `Operator.of` then lifts the node's public fields onto the operator; after that the runner, the function, and the template environment read the operator, not the node. `Function` holds an `environment`: `environment.config` is the function parameters and `environment.operator` is the template view, both built from the operator. Rendering an entity calls `environment.bind` to fill `entity`. Contract tests cover it.
- Add the user guide `docs/guide.md`: background, core concepts, workflow, use cases, configuration, built-in functions by operator type, template variables of rendering functions and how to add more, writing your own function, and a complete example of using docorder in your own project. It is in Chinese only for now.
- The documents are checked against the current code and rewritten. The README now installs from the repository with `uv sync`, and adds getting the code, prerequisites, a runnable quick start and rerun example, configuration, and troubleshooting. `docs/design.md` corrects the behaviour for duplicate node names, a reduce with an empty upstream, stage-wide clearing, parallel failures, and a failing source `emit`, and adds a rerun decision table and an end-to-end example. `docs/functions.md` adds a failure and retry comparison, how `Command` resolves relative paths, and reduce and fanout implementation examples. `SECURITY.md` and the introduction page drop the `cursor` preset, which does not exist.
- `docs/design.md` is rewritten around the current stage scheduler: the state of entities, operators, and jobs, the epoch directory, and how one run compares upstreams and writes them.
- Documents are provided in Chinese and English. Chinese keeps the original file name. English uses the same name with an `.en` suffix. The README is rewritten around the current `Job` and `execute`.
- The project introduction page is `docs/index.html`.
- Function documentation is collected in `docs/functions.md`. Each function is one module under `src/docorder/functions/`.
- A source operator accepts only a function. The function yields each entity's data and tag from `emit`. `DirectorySource` produces entities from a directory of existing entity subdirectories (`data` and `tag.json`). `FilteredDirectorySource` selects them by name endings and `data` size in `filter`.
- The package no longer ships operator homes. Homes come from `DOCORDER_HOMES`. Concrete operators are implemented later.
- `execute` receives the epoch. One run walks the whole graph in topological order.
- Operator `props.json` uses `type`: `source`, `map`, `reduce`, `fanout`.
- Entities are stored in an epoch subdirectory. The upstream operator, entity name, epoch, and hash are written to `upstream.json` in the entity directory. Another run of the same epoch executes what is missing, deletes what is extra, and redoes what the upstream changed.
- The project name is docorder. The package, the command-line tool, and `DOCORDER_DG`, `DOCORDER_LLM`, and `DOCORDER_HOMES` all use that name.
- Reusable operator implementations live in `src/docorder/operators/`. Stage scheduling lives in `src/docorder/runner.py`.
- The data-governance documentation, data-quality, semantic-physical, and semantic-ontology jobs became scripts under `examples/data_governance/`, and are no longer installed through `docorder run`.
- `llm` / `llm_batch` call a model through a configurable tool. The built-in preset is `cursor`. A command JSON can be passed in as well.

## [0.1.0] - 2026-10-12

- Schedule directory entities by stage, with retry, epoch checkpoints, skipping an operator, and resuming from a named operator.
- Ship jsonnet, template prompt, Cursor, command, CSV fan-out, concatenation, and review operators with the package.
- Provide documentation, data-quality, semantic-physical, and semantic-ontology jobs. These jobs need an external repository with a matching layout. The path is given with `--dg` or `DOCORDER_DG`.

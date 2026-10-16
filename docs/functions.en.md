# Function

[中文](functions.md)

A function is the Python class an operator home loads. It is the code that actually reads upstream entities and fills in the body and tag of new ones. This page is the configuration reference for the functions in the package: what each one does, which keys go in `props.json`, which variables a template can read during a render, which failures are retried, and how to write your own function in a home when the package has none for the job.

The scheduling layer, meaning how the runner decides which entities to run, how parallel work is split, and how a failed run continues, is in [design.en.md](design.en.md). Installation and a first run are in the [README](../README.en.md).

The package has eight functions that can be written into `class` directly: two sources, five maps, and one output. Reduce and fanout have base classes only. Implement them in a home when you need them.

## Document structure

1. How a function relates to entities, operators, and jobs, and what an operator home contains.
2. Which keys in `props.json` belong to whom, how parameters enter one run, and which failures are retried.
3. Template variables of the rendering functions: which exist, where they come from, how to add one, and how to refer to it.
4. The two source functions.
5. The five map functions.
6. Implementing a function in a home, with complete reduce and fanout examples.
7. An appendix that lists the class names you can write into `class`.

Three structural sketches appear below: the layout of an operator home, which fields belong to the template environment during one render, and a comparison of how each function handles failure.

## 1. Where a function sits in a job

### Entity, operator, and function

The unit of one transform is an entity. An entity is one directory under an epoch directory, and the directory name is the entity name. A name cannot be empty, cannot contain `/` or `\`, and cannot start with `.` or `_`. Two files in that directory are the ones you read and write most: `data` is the body, and `tag.json` is a JSON object of traits that downstream stages use for filtering and for templates. Once an entity with an upstream is finished, the snapshot lives in `tag.json` as `upstream`. The runner writes it, and a function never touches it.

An operator is a reusable transform. Its static files live in a directory called the operator home. The home does not record where one run writes. A job joins several homes into a graph, and decides each node's output path and the parameters it overrides.

A function is the class named by `class` in the home. For each call, the runner constructs an instance and hands it the upstream entity and a target entity that has no body yet. The function only fills in the target's body and tag. Persisting, snapshots, retry, and parallelism are done by the runner. You usually do not call a function yourself. You prepare a home, then refer to it from a job.

### Layout of an operator home

```text
<a directory in DOCORDER_HOMES>/[optional category directory/]<home name>/
  props.json     required; type, function class, scheduling fields, and function parameters
  primary.py     optional; loaded when class is primary:ClassName
  lib/           optional; templates and other files shipped with the operator
  tools/         optional; PromptToLLM tool presets, one <name>.json per preset
```

`DOCORDER_HOMES` lists directories separated by the system path separator, as `PATH` is. When two homes share a name, the one in the earlier directory wins. The runner first looks for `<home name>/props.json` directly in each directory, then one category directory below it. Category directories whose names start with `.` or `_` are skipped. The package ships no homes, so the files in `lib/` and `tools/` are yours to provide.

When a function reads a file in the home, the path is resolved relative to the home and cannot leave it through `..` or an absolute path. A parameter such as `template` can therefore only name a file inside the home.

## 2. Configuration

### Keys in props.json

`props.json` is a JSON object whose keys fall into three groups.

```text
props.json
  type, class                 identity; required, and a job cannot change them
  parallelism, retry          scheduling; a job overrides them with same-named arguments when it adds the node
  every other key             function parameters; the node's config overrides same-named keys
```

`type` is one of `source`, `map`, `reduce`, `fanout`, and `output`. The first four decide how upstream entities correspond to output entities. `output` writes upstream bodies as job-result files. `class` is written as `module:Class`, for example `docorder.functions.impl.command:Command`, or as `primary:Class` to load it from the home's `primary.py`. The class must be a concrete subclass of the base class for that `type`, with every abstract method implemented. When `type` or `class` is missing or malformed, `add_operator_node` fails right away. When the class cannot be found, or is not a subclass of the right base, `execute` fails before any operator runs.

`parallelism` is the degree of parallelism for map and fanout, and defaults to 1. `retry` is an object. `max_attempts` is the most attempts one entity gets, default 1. `backoff_seconds` is the backoff base, default 0. A job overrides them with the `parallelism=` and `retry=` arguments of `add_operator_node`. Written into the node's `config`, these two keys have no scheduling effect and only become function parameters.

Every other key is a function parameter, such as a directory, a template path, or a filter. The node's `config` is merged on top of them, and the node wins on a shared name. A `class` key in `config` is dropped, so it cannot swap the function. When parallelism is greater than 1, map and fanout run the slices in threads, and the parameters stay in the current process's memory.

Below is the home configuration of a map operator. `template` is not a scheduling field. It is a parameter of this function, and a job can pass a different value when it adds the node.

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "parallelism": 4,
  "retry": { "max_attempts": 3, "backoff_seconds": 5 },
  "template": "lib/prompt.jinja"
}
```

### How parameters enter one run

At runtime a function holds one `environment` with two related pieces of data, for different purposes.

The first is `environment.operator_props`, the merged function parameters above. The function uses it to decide which directory, which template, and which command to use.

The second is `environment.template_env`, for templates: nested `operator`, `job`, and `entity`. `operator` starts from the merged function parameters and adds this run's `name` and `home`. `job` has the job name and epoch. `entity` has source/target fields only while an entity is being rendered.

`operator.output` is the node's output directory, `output-root/node-name`, without the epoch level. The directory of the entity being written is `entity.output`, `output-root/node-name/epoch/entity-name`. Use `entity.output` to place a file beside that entity.

### Failure and retry

The runner retries a call for one entity according to `retry`, except for `FatalError`. That error means the configuration or the input itself is wrong, and another attempt will not help, so the stage fails at once. Every other exception, including a non-zero status from an external process, is tried again after waiting `backoff_seconds × attempts so far` seconds, until `max_attempts` is used up.

| function | Fails at once, no retry | Retried according to `retry` |
| --- | --- | --- |
| `DirectorySource`, `FilteredDirectorySource` | `directory` missing, directory does not exist, malformed `filter`, `data` that is not UTF-8, `tag.json` that is not an object | none, see chapter 4 |
| `TemplateToPrompt` | `template` missing, template file not in the home, template refers to a variable that does not exist | none |
| `JinjaToJsonnet` | `template` missing, upstream body empty or not a JSON object, render is only whitespace | none |
| `JsonnetToPrompt` | `jsonnet` not found | the compiler exits with a non-zero status |
| `Command` | `argv` missing, first command not found, a brace variable that does not exist, an invalid `capture` value | the process exits with a non-zero status, the command did not write `output_file` |
| `PromptToLLM` | `workspace` missing or not a directory, tool not found, invalid tool definition, first command not found | the process exits with a non-zero status, the written `data` is empty, not UTF-8, or not a file |
| `Output` | `directory` is not a non-empty string, `name_template` is not a string or fails to render, the file name is invalid, two entities produce the same file name | a transient error while writing a job-result file |

## 3. Rendering and template variables

### The rendering process

The five map functions share one rendering process (`RenderedMap`). For each upstream entity it reads the upstream, produces the new body, then produces the new tag. By default it reads the upstream body, and the tag it writes is a copy of the upstream tag. Each concrete function replaces the read, the render, or the tag step. Each upstream entity is rendered once, and the body and tag come from that same render.

Each render builds a `template_env`. The fields belong as follows.

```text
template_env
  operator     function parameters, plus this run's name and home
  job          name, epoch
  entity       source_name, source_data, source_tag, source_data_path
               target_name, target_data_path, output
```

### Two ways to refer to values

`TemplateToPrompt` hands `template_env` to Jinja: `{{ operator.home }}`, `{{ job.epoch }}`, `{{ entity.source_data }}`. `Command` substitutes dotted paths such as `{operator.home}` and `{entity.output}`. The upstream tag is `entity.source_tag`.

The top-level names of `JinjaToJsonnet` come from the JSON object in the upstream body and from the `variables` parameter, and the upstream JSON wins on a shared key. `template_env` is merged after that, plus a top-level `home` that matches `operator.home`. `operator`, `job`, `entity`, and `home` inside the JSON do not replace the objects the environment provides.

`JsonnetToPrompt` and `PromptToLLM` go through the same rendering process, but their bodies get none of these substitutions. The first compiles the upstream body as a complete jsonnet program. The second hands the upstream body to the model tool unchanged. In the model tool's arguments, only the literal `{workspace}` is replaced, with the value of the `workspace` parameter.

### Adding a variable

Where a new variable appears in the template depends on where you write it.

Written in the upstream entity's `tag.json`, it is visible both at the top level and on `entity` to the next function that uses the flattened namespace. `name`, `data`, and `output` are filled by this render, and `operator`, `entity`, and `environment` are reserved for the environment objects, so tag keys with those names are hidden.

Written as a function parameter in the operator's `props.json`, or in the node's `config`, it is read in the template as `operator.key`. When both have it, the node's `config` wins. `name`, `home`, `class`, `type`, `parallelism`, `output`, `retry`, and `epoch` are filled by this run and override a parameter with the same name.

For `JinjaToJsonnet`, a key can also go in the JSON object of the upstream body, or in the `variables` parameter. Those keys become top-level Jinja names. `{{ key | jsonnet }}` writes the value as a jsonnet literal: a string is quoted, and an object or array is written as JSON. If the template refers to a name that was not provided, the render fails.

When this operator must compute a variable and hand it downstream, write it into the tag from a subclass. A directory source overrides `extract_tag(name, content, tag)`, whose arguments are the entity directory name, the `data` text, and the object loaded from `tag.json`. A rendering function overrides `generate_props` and adds fields to a copy of the upstream tag. A downstream render reads those fields on `entity` and at the top level of the flattened namespace.

### Referring to variables in a template

In a `TemplateToPrompt` Jinja template, `{{ name }}` is the entity name, `{{ data }}` is the upstream body, `{{ operator.home }}` is the operator home, and `{{ entity.output }}` is the directory of the entity being written. The same values can be written as `{{ environment.entity.data }}` and `{{ environment.operator.home }}`.

Each argument of `Command`, and its `output_file`, uses single braces with the names of the flattened namespace, such as `{name}`, `{operator.home}`, and `{entity.output}`.

In `JinjaToJsonnet`, `{{ title }}` reads `title` from the upstream JSON or from `variables`. The operator home is `{{ home }}` or `{{ environment.operator.home }}`, and the directory of the entity being written is `{{ environment.entity.output }}`.

## 4. Source functions

A source is the root of the graph and has no upstream. A source calls its function and rewrites this epoch's entities only when `execute` is called with `start_from_scratch=True`. Otherwise it leaves its output alone, and downstream stages read the entities already in that epoch. A source's `retry` covers only the step that writes one record to disk. An exception raised while reading the directory or a file fails the stage directly.

### DirectorySource

This function turns a directory that already exists into the first entities of the current epoch. It reads only direct child directories that already look like entities: the directory name is the entity name, and the directory holds `data` and `tag.json`. The body is the UTF-8 text of `data`. The tag is the JSON object in `tag.json`. Loose files, directories missing `data` or `tag.json`, and names that start with `.` or `_` are skipped.

In the home's `props.json`, `type` is `source`, `class` is `docorder.functions.impl.directory_source:DirectorySource`, and `directory` names the directory. A relative path is resolved from the operator home, not from the current working directory. An absolute path is used as given.

```json
{
  "type": "source",
  "class": "docorder.functions.impl.directory_source:DirectorySource",
  "directory": "/data/tables"
}
```

The default tag is the loaded `tag.json`. To change it, implement `extract_tag(name, content, tag)` in a subclass. To change which entity directories are emitted, implement `include(path)`, where `path` is that entity directory.

### FilteredDirectorySource

This function reads the same entity directories as `DirectorySource` and keeps a subset before emitting records. The rules for the entity name, the body, and the default tag are the same as in the previous section.

`type` is `source`, `class` is `docorder.functions.impl.directory_source:FilteredDirectorySource`, and `directory` means the same as in the previous section. The rules go in the `filter` parameter, an object that can live in `props.json` or be overridden by the node's `config`.

`disabled_suffix` lists forbidden endings. An entity directory whose name ends with any of them produces no entity. The value is one string or a list of strings. `enabled_suffix` lists allowed endings in the same form. Without it, every entity directory that was not disabled produces an entity. With it, only names that end with one of those endings are kept. `min_size` and `max_size` are inclusive byte bounds on the `data` file, and either one may be written alone. A lower bound greater than the upper bound is an invalid configuration.

The checks run in this order: drop disabled suffixes, keep allowed suffixes, then keep by the size of `data`. A home that drops backup names and limits body size can be written as:

```json
{
  "type": "source",
  "class": "docorder.functions.impl.directory_source:FilteredDirectorySource",
  "directory": "tables",
  "filter": {
    "disabled_suffix": [".bak", ".tmp"],
    "min_size": 1,
    "max_size": 1048576
  }
}
```

## 5. Map functions

Each of the five map functions writes one same-named entity for each upstream entity.

### TemplateToPrompt

This function renders one Jinja template from the home for each upstream entity, and the result becomes that entity's body. The operator supplies the template file. The upstream body is not the template. It enters the template as the variable `data`. The tag is a copy of the upstream tag.

`type` is `map`, and `class` is `docorder.functions.impl.template_to_prompt:TemplateToPrompt`. The `template` parameter is a path inside the home, for example `lib/prompt.jinja`. The template uses the flattened namespace. If it refers to a variable that does not exist, the entity fails and is not retried, because the template lacks a variable this render needs, and rendering again would give the same result.

### JinjaToJsonnet

This function uses a Jinja template in the home and the JSON carried by the upstream entity to produce jsonnet source. The upstream body must be a JSON object, and the object's keys are the template variables. The output body is the render. The tag defaults to an empty object. To hand traits downstream, implement `generate_props` in a subclass. A subclass can also implement `template_text` to supply the full template from code, and then `template` need not be configured.

`type` is `map`, and `class` is `docorder.functions.impl.jinja_to_jsonnet:JinjaToJsonnet`. `template` is a template path inside the home. `variables` is an optional object of default variables, and same-named keys in the upstream JSON override it. The entity fails when the upstream body is empty, is not a JSON object, or the render is only whitespace.

### JsonnetToPrompt

This function treats the upstream body as a jsonnet program and compiles it with the local `jsonnet -`. The program is given on standard input, and standard output becomes the new body. The tag is carried from the upstream. The program text gets no template substitution. `import` and `importstr` use the paths already written in the program. When a library file lives in the operator home, the program should name it by absolute path, which an upstream template step can build from `operator.home`.

`type` is `map`, and `class` is `docorder.functions.impl.jsonnet_to_prompt:JsonnetToPrompt`. This function has no parameters of its own. `jsonnet` must be on `PATH`.

### Command

This function runs one external command for each upstream entity. The command does not go through a shell. `argv` is passed as the process arguments. Each item of `argv`, and the optional `output_file`, is substituted from the flattened namespace, written as `{key}` or a dotted path such as `{operator.home}`. The tag is carried from the upstream, with `command` added. Its value is the substituted arguments joined by spaces. When `output_file` is configured, the tag also holds the substituted `output_file`.

`type` is `map`, and `class` is `docorder.functions.impl.command:Command`.

`argv` is the command and its arguments, with at least one item. `cwd` is the command's working directory. It is used as written, without brace substitution. When it is omitted, the Python process's current directory is used. `output_file` is the file the command is expected to write, and its parent directory is created before the command runs. When `output_file` is a relative path, docorder looks for it from the Python process's current directory, regardless of `cwd`. Write it as an absolute path, or as `{entity.output}/file-name`.

`capture` decides where the body comes from. `file` reads `output_file`, which must exist when the command finishes. `stdout` uses standard output. `none` makes the body an empty string. Without `capture`, it is `file` when `output_file` is configured and `stdout` otherwise. An entity with an empty body is redone by its downstream on every run. Chapter 4 of [design.en.md](design.en.md) explains why.

The command does not see the upstream body unless you put `{data}` into an argument. The configuration below follows a `DirectorySource` and counts the lines of each source entity's `data` file. `{name}` is the entity name, and `/data/notes` should be the same as the source's `directory`:

```json
{
  "type": "map",
  "class": "docorder.functions.impl.command:Command",
  "argv": ["wc", "-l", "/data/notes/{name}/data"]
}
```

When `argv` uses a shell such as `sh -c`, the tag values and body substituted into it run as shell code. Write it that way only for trusted input.

### PromptToLLM

This function treats the upstream body as a prompt and hands it to a command-line tool. The tag is carried from the upstream. The prompt gets no template substitution.

After the tool returns, a `data` file already in the target entity directory means the tool wrote the body itself. That file must be non-empty UTF-8 text; otherwise this call fails and is retried according to `retry`. When the check passes, `data` is left as it is and only `tag.json` is written. Without that file, the body is still the tool's standard output. A `data` file already present when the call starts is removed first, so a file left by a failed attempt is not taken as this attempt's result.

`type` is `map`, and `class` is `docorder.functions.impl.prompt_to_llm:PromptToLLM`.

`workspace` is the tool's working directory. It must be configured and must exist before the run. A relative path is resolved from the Python process's current directory. The tool process runs in that directory, and `{workspace}` in the tool's arguments is replaced with that path.

`tool` names the tool in one of three ways. A name first looks for `tools/<name>.json` in the home. If that file does not exist, the string is read as a path to a JSON file. An object gives the tool definition directly in the parameters. When `tool` is not configured, the value of the `DOCORDER_LLM` environment variable is used, read as a name or a file path. When neither gives a tool, the entity fails. The package ships no presets. The files in `tools/` are yours to write.

A tool definition is a JSON object. `run` is a non-empty array of strings: the command and its arguments. `prompt` is `stdin` or `arg`. `stdin` writes the body to the process's standard input, and `arg` appends the body as the last argument. Without `prompt`, `stdin` is used. `name` is optional and only appears in error messages.

```json
{
  "name": "my-llm",
  "run": ["my-llm-cli", "--cwd", "{workspace}"],
  "prompt": "stdin"
}
```

With that definition saved as `tools/my-llm.json` in the home, write `"tool": "my-llm"` in `props.json`. `my-llm-cli` is a placeholder. Replace it with the command you actually use on your machine.

### Output

`Output` writes the body of each upstream entity of this epoch as a file in the job result directory. The default directory is `.job_result` at the job root. `directory` selects another path; a relative path is resolved from the operator home. It does not produce entities for a downstream node. `type` is `output`. `class` is `docorder.functions.impl.output:Output`.

The file name defaults to the entity name. `name_template` is a Jinja template rendered with that entity's tag, for example `{{ table }}.sql`. The render must be one file name, with no `/` or `\`, and must not be empty. Two entities that produce the same name fail the stage with `FatalError`. Files this node wrote last time and no longer produces are deleted.

```json
{
  "type": "output",
  "class": "docorder.functions.impl.output:Output",
  "directory": "/data/out",
  "name_template": "{{ table }}.sql"
}
```

## 6. Implementing a function in a home

### Choosing a base class

When no ready-made function expresses a transform, write a class in the home's `primary.py` and set `class` to `primary:ClassName` in `props.json`. The base class follows from `type`, and all of them live under `docorder.functions`.

`SourceFunction` implements `emit()` and yields `SourceRecord(name, data, tag)` one record at a time. `MapFunction` and `FanoutFunction` implement `transform_data(source, target)` and `transform_props(source, target)`, which receive one upstream entity and one target entity. `ReduceFunction` implements the same two methods, but its first argument is the list of every upstream entity in this stage. `FanoutFunction` also has `output_names(source)`, which returns the list of output names this upstream entity produces. By default it returns only the upstream entity's own name. For a map that renders entity by entity, subclass `docorder.functions.rendered_map:RenderedMap` and implement only `apply_render`.

### Rules a function follows

`transform_data` must set `target.staging_data` to a string, and `transform_props` must set `target.tag` to a dict. Otherwise the entity fails with `FatalError`. When a `data` file is already in the target directory, `staging_data` may be left unset. The runner keeps that file and writes only `tag.json`. Read the upstream body with `source.read_text()` and the upstream tag with `source.tag`. `self.environment.operator_props` holds the merged parameters. A function does not write the snapshot, and does not retry or start a thread pool on its own. The runner does that.

The runner constructs a new function instance for every entity and every attempt, so attributes on the instance do not carry over to the next entity. `output_names` runs in the main process and may be called more than once per run, so its result should depend only on the upstream entity passed in. For problems that retrying cannot fix, such as bad configuration, raise `docorder.utils.errors.FatalError`. For problems that may clear up on their own, raise another exception and let `retry` handle it.

### Example: reduce

The reduce below joins the bodies of every upstream entity into one entity. `output` is a reserved parameter of reduce operators. It names the single output entity and defaults to `result`.

`homes/join/props.json`:

```json
{
  "type": "reduce",
  "class": "primary:JoinBodies",
  "output": "all",
  "separator": "\n---\n"
}
```

`homes/join/primary.py`:

```python
from docorder.functions.reduce_function import ReduceFunction


class JoinBodies(ReduceFunction):
    def transform_data(self, sources, target):
        separator = self.environment.operator_props.get("separator", "\n")
        target.staging_data = separator.join(entity.read_text() for entity in sources)

    def transform_props(self, sources, target):
        target.tag = {"count": len(sources), "names": [entity.name for entity in sources]}
```

With two upstream entities `a` and `b`, the output is `<epoch>/all/`. Its body is the two bodies with `---` between them, and its tag is `{"count": 2, "names": ["a", "b"]}`. When any upstream body changes, or an upstream entity appears or disappears, `all` is redone. When the upstream has no entities at all, the reduce still writes `all`, and the function receives an empty list.

### Example: fanout

The fanout below splits the upstream body into lines. Each line becomes an entity named `<upstream entity name>-<line number>`.

`homes/lines/props.json`:

```json
{
  "type": "fanout",
  "class": "primary:SplitLines"
}
```

`homes/lines/primary.py`:

```python
from docorder.functions.fanout_function import FanoutFunction


class SplitLines(FanoutFunction):
    def output_names(self, source):
        count = len(source.read_text().splitlines())
        return [f"{source.name}-{index}" for index in range(count)]

    def transform_data(self, source, target):
        index = int(target.name.rsplit("-", 1)[1])
        target.staging_data = source.read_text().splitlines()[index]

    def transform_props(self, source, target):
        target.tag = source.carried_tag()
```

When the upstream entity `hello` has two lines, the outputs are `hello-0` and `hello-1`. The output names produced from all upstream entities must be distinct within the stage, or the stage fails with `OperatorValidationError`. Each output depends on one upstream entity, so a fanout is split across processes by `parallelism` the same way a map is.

To try both examples on the README quick start, put the `join/` and `lines/` homes in `quickstart/homes/`, then add two lines in `main()` before `execute`:

```python
job.add_operator_node("joined", "join", upstream="notes")
job.add_operator_node("parts", "lines", upstream="notes")
```

## Appendix: class names

Use the forms in this table when configuring `class`. The built-in implementations live under `src/docorder/functions/impl/`.

| function | type | class |
| --- | --- | --- |
| DirectorySource | source | `docorder.functions.impl.directory_source:DirectorySource` |
| FilteredDirectorySource | source | `docorder.functions.impl.directory_source:FilteredDirectorySource` |
| TemplateToPrompt | map | `docorder.functions.impl.template_to_prompt:TemplateToPrompt` |
| JinjaToJsonnet | map | `docorder.functions.impl.jinja_to_jsonnet:JinjaToJsonnet` |
| JsonnetToPrompt | map | `docorder.functions.impl.jsonnet_to_prompt:JsonnetToPrompt` |
| Command | map | `docorder.functions.impl.command:Command` |
| PromptToLLM | map | `docorder.functions.impl.prompt_to_llm:PromptToLLM` |
| Output | output | `docorder.functions.impl.output:Output` |

Base classes: `docorder.functions.source_function:SourceFunction`, `docorder.functions.map_function:MapFunction`, `docorder.functions.reduce_function:ReduceFunction`, `docorder.functions.fanout_function:FanoutFunction`, `docorder.functions.output_function:OutputFunction`, and `docorder.functions.rendered_map:RenderedMap`.

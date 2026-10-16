# Design

[中文](design.md)

Docorder transforms a batch of directory entities that share one shape, stage by stage along a job graph, and keeps the progress inside each entity's own directory. This page covers the scheduling layer: what state an entity, an operator, and a job each hold; which files one run writes to disk, and in what order; how the runner decides whether each entity is executed, redone, kept, or deleted; and what state the disk is left in after failures and retries.

Each function's parameters and template variables are in [functions.en.md](functions.en.md). Installation and a first run are in the [README](../README.en.md). This page does not repeat them.

Two boundaries hold throughout this version. First, execution is by stage: an operator finishes the whole batch for this epoch before its downstream starts. Starting downstream as soon as one entity has been written is not in this version. Second, a node has exactly one upstream, so the graph is a set of trees rooted at sources.

On a first reading, take the chapters in order. Chapter 1 sets up three concepts, chapter 2 shows the disk layout, chapter 3 walks through one run in time order, chapter 4 gathers the rules for running again, and chapter 5 ties everything together with a two-stage job. Chapter 6 is for readers who will implement their own transforms.

## Document structure

1. The state held by an entity, an operator, and a job, and how the three stay apart.
2. The directory layout of one epoch, the output marker, and the write order of one entity.
3. One run from assembly through each stage: the expected names, the comparison with disk, clearing, filling, parallelism and retry, and the separate path of a source.
4. What happens to entities in each case when the same epoch runs again.
5. Three runs of a two-stage job, end to end.
6. Which duties stay with the runner when you add a transform.

Four structural sketches appear below: the fields of one record in `tag.json` `upstream`, which fields of an operator home belong to whom, the directory layout of one run, and how entities correspond across a two-stage job.

## 1. Entity, operator, and job

An entity, an operator, and a job hold different state. An entity remembers which upstream bodies this object read this time. An operator remembers what kind of transform it is, which class performs it, and its default parameters. A job remembers which transforms this run joins, and where they write. Their lifetimes differ: entities stay on disk under their epoch, an operator home is reused by many jobs, and a job object lives only inside one Python process. Because progress lives in the entity directories, another process, or even another job script, can continue where the last run stopped, as long as the output paths and the epoch are the same.

### Entity

#### Name and recognition

An entity is one object of one transform. On disk it is one directory under an epoch subdirectory of a node's output directory, and the directory name is the entity name. The name must be one visible directory segment: non-empty, unchanged by stripping surrounding whitespace, containing neither `/` nor `\`, neither `.` nor `..`, and not starting with `.` or `_`. Names starting with those two characters are reserved for markers and runtime files, and the next operator does not take them as input.

A subdirectory is recognized as an entity when it holds `data` or `tag.json`. Empty directories, directories with invalid names, and directories one level deeper are not entities.

#### Body and tag

`data` is the body, read and written as UTF-8 text. Its meaning depends on the operator: the original file text in a directory source, the rendered result in a template operator, the command output in a command operator. The scheduler only requires it to be a string and does not interpret the format.

`tag.json` is a JSON object used downstream for filtering and templates. Its keys are decided by the function. The runner also manages `upstream` and `global_prop`.

A downstream entity is given the upstream entity, and the tag is often copied whole, so it still holds that entity's `upstream` and may still hold a leftover `current`. Before writing, the runner always resets both keys. It drops `current`, and `upstream` becomes a live snapshot of the immediate upstream entities: that record when there is one upstream, and a list of those records when there are none or several. Values the function wrote on those two keys are replaced. A source has no upstream, does not write `upstream`, and drops `current`.

`global_prop` is merged at the same time. Before writing the target of a map, fanout, or reduce, the runner merges the `global_prop` object from the upstream tags into the target's `global_prop`. Keys the target wrote itself are kept. When a reduce has several upstream entities, they are taken in name order, and later ones overwrite earlier ones. When `tag.json` cannot be read or is not an object, the entity is treated as invalid and is redone at the next comparison.

#### Upstream snapshot

The snapshot lives in `tag.json` as `upstream`. One upstream is one record; none or several is a list of records. Each record has four string fields.

```text
tag.json  "upstream"
  { operator, name, epoch, hash }
  or [ { operator, name, epoch, hash }, ... ]
```

`operator` is the upstream node name, `name` is the upstream entity that was read, `epoch` is the epoch at the time of reading, and `hash` is the sha256 of that upstream entity's body together with its user tag (excluding `upstream` and a leftover `current`), written in hexadecimal. A map or fanout snapshot is one record. A reduce snapshot has one for every upstream entity that took part. All records of one entity must name the same upstream node. When the value is not a record or a list of records, a field is not a string, or two node names appear, the snapshot is invalid.

A snapshot covers the upstream body and user tag. Editing an upstream entity's `data` or `tag.json` by hand makes the snapshot mismatch, so dependents are redone on the next run. A change to this operator's parameters or template, or to the function code, does not make the snapshot mismatch.

A source has no upstream and does not write `upstream`. When an entity is written and the directory still holds an old `upstream.json`, that file is deleted.

#### What finished means

An entity with an upstream is finished when `upstream` in `tag.json` has been written and matches the current upstream. The body can appear first. Without a snapshot in the tag the entity is not finished, and the next run of the same epoch does it again. When the upstream body is an empty string or cannot be read, the hash in the snapshot is an empty string. An empty hash never passes the comparison, so an entity whose upstream body is empty is redone on every run.

Entity directories serve the scheduler. They do not replace the caller's own source files, which stay where they are and are read again by the source when needed.

### Operator

#### Homes and lookup

An operator is a reusable transform and does not record the output path of any one run. Its static files live in an operator home. The package ships no homes. The caller places homes in the directories listed by the `DOCORDER_HOMES` environment variable. The separator is the same as for `PATH`, and earlier directories win. A home may sit directly in a listed directory, or one category directory below it. Category directories whose names start with `.` or `_` are skipped. A directory is a home when it contains `props.json`.

Lookup happens at the moment `add_operator_node` is called, so the environment variable must be set before that. When the home is not found, a `FileNotFoundError` is raised, listing the directories that were searched.

#### Which fields of props.json belong to whom

```text
props.json
  type, class                 identity; a job cannot change them
  parallelism, retry          scheduling; a job overrides them with same-named arguments when it adds the node
  every other key             function parameters; the node's config overrides same-named keys
```

`type` is one of `source`, `map`, `reduce`, `fanout`, and `output`. The first four decide how upstream entities correspond to output entities. `output` does not write entities; it writes the upstream epoch's bodies as job-result files. `class` is the function to load, written as `module:Class`, or as `primary:Class` to load the home's own `primary.py`. When `props.json` is not an object, `class` is not a string containing a colon, or `type` is not one of the five, `add_operator_node` fails with `JobValidationError`.

`parallelism` defaults to 1. `retry` is an object with `max_attempts` and `backoff_seconds`. The first defaults to 1 and cannot be less than 1. The second defaults to 0.

A home can also hold directories such as `lib/` and `tools/` for templates and tool definitions that ship with the operator. Those files belong to the operator, not to the output of any one job.

#### The five types

All five types follow the rule that a node has one upstream. The first four differ in where the output names come from and which upstream entities each output depends on. `output` does not write entities.

A source has no upstream. Its function yields records through `emit`, each with an entity name, a body, and a tag.

A map writes one same-named entity for each upstream entity. The function receives one upstream entity and a target that has no body yet.

A reduce gathers the whole upstream batch into one entity. The entity name is the function parameter `output`, default `result`. The function receives the list of upstream entities and that one target.

A fanout splits one upstream entity into several. The function's `output_names` lists the output names this upstream entity produces, and by default returns only the upstream entity's own name. The output names produced from all upstream entities must be distinct within the stage. The function then receives, for each output, the upstream entity that produced it and the target.

An output reads every entity of the upstream epoch and writes each body as a file in the job result directory. The default directory is `.job_result` at the job root. `directory` selects another path; a relative path is resolved from the operator home. The file name defaults to the entity name. When `name_template` is set, that template is rendered with the entity tag to produce the file name. The name must be one file name. Two entities that produce the same name fail the stage with `FatalError`. Files this node wrote last time and no longer produces are deleted. The job result directory is the job's overall output, not an epoch directory of entities.

Each output of a map or a fanout depends on one upstream entity, so the work can be split across processes by entity. The single output of a reduce depends on every upstream entity, and is written once, in the current process. An output writes one file per upstream entity and is not sliced.

### Job

#### Nodes and output paths

A job is a directed acyclic graph. `Job(name, root)` takes a job name and an output root. `add_operator_node(name, home, upstream=..., config=..., parallelism=..., retry=...)` adds a node. Every node except a source names its one upstream node, and a list or tuple for `upstream` is rejected. The output path is decided by the job: `output-root/node-name`. It is not written into the home. The node name is joined into the path without the checks that entity names get.

Adding the same node name again replaces the earlier node without an error.

#### Merging config

When a node is constructed, the passed-in `config` is applied onto the home's function parameters and stored on `props`. A `class` key is dropped, so it cannot swap the function. After construction the node does not keep `config`; the public object is `props`. `parallelism` and `retry` written into `config` only become function parameters. Scheduling still follows the home, or the same-named arguments of `add_operator_node`.

When the job graph is assembled, `Operator.of` lifts the node's public fields (`name`, `props`, `type`, `operator_home`, `output_path`, `upstream`) onto the operator. After that the runner, the function, and the template environment read the operator, not the node. The node is only for declaring, validating, and ordering the job graph.

When parallelism is greater than 1 and more than one entity is waiting to be written, map and fanout run the slices in threads. The threads share the current process's memory, so the parameters need not be picklable.

The merged parameters live on `props`. They are both what the function reads and the base of the operator view inside templates. How that view is built is described in [functions.en.md](functions.en.md).

#### Validation and execution order

At the start of `execute`, the job graph is validated, and these cases are rejected: a cycle, an upstream name that is not in the graph, a node that depends on itself, two nodes whose output paths resolve to the same place, and two output paths where one contains the other. The last two can be caused by symbolic links or by node names that contain `/`.

Execution follows topological order. When several nodes are ready at the same time, the one added to the job first runs first.

## 2. Disk layout of one epoch

### Directory tree

```text
<output root>/
  .job_result/              overall job output, written by an output node
    <file name>             body of an upstream entity
  <node name>/
    .docorder-output        output marker
    <epoch>/
      <entity name>/
        data
        tag.json            includes upstream when the entity has an upstream
    <another epoch>/
      ...
```

### Epoch

An epoch is the name the caller passes to `execute`, and the name of the subdirectory that holds the entities. Within one run, every node's output uses this epoch, and so do the epochs recorded in snapshots. A different epoch is a different set of subdirectories: a new epoch starts from empty directories, and the entities of old epochs stay where they are. The runner neither reads nor cleans them. When the epoch recorded in a snapshot differs from the current one, the entity is redone.

The runner does not check the epoch name and joins it into paths as is. A name such as `2026/10` creates two directory levels. Pass a single directory name, such as a date or a version number.

### Output marker

At the start of each stage, the runner checks that node's output directory. When the directory exists, contains anything, and has no `.docorder-output`, the run stops with `FatalError`, so that someone else's directory is not taken as an output and cleaned up. After the check, the runner creates the directory and writes the marker. The marker starts with `.`, so it is not taken as an entity. Each node runs this check only when its own stage starts, so earlier nodes may already have finished.

### Write order of one entity

A successful write reaches disk in a fixed order. The entity directory is ensured first. Then the body is written, when this attempt actually produced one, then `tag.json`. Each file is first written to a `.tmp` file in the same directory and then replaces the real file, so no single file is ever half written. A leftover `upstream.json` in the directory is deleted after the write.

This order defines "finished" by the snapshot in `tag.json`. If the process dies between the body and the tag, the directory may already hold the new body and still have no valid snapshot. The next comparison treats the entity as unfinished, redoes it, and overwrites it.

## 3. One run

`execute(job, epoch, start_from_scratch=False)` has two parts. It assembles the whole graph first, then executes the stages one by one in topological order. When a stage raises an exception, the run stops there, and later nodes do not start.

### Assembly

Assembly validates the job graph, then loads the function class of every node and constructs one function instance. When a class cannot be found, is not a subclass of the base for its `type`, or still has unimplemented abstract methods, the run fails with `OperatorValidationError`. This happens before any stage, so a wrong class name on the last node does not waste the work of the nodes before it.

Assembly also creates one entity table for this epoch per output directory. Within one run each directory has exactly one table. A node updates it as it writes, and its downstream reads it as the upstream.

### Preparing a stage

#### The expected names

Every stage except a source first rereads the entities the upstream has in this epoch, and builds the expected names: "output name → the upstream entity names it depends on".

For a map, each upstream entity name points at itself. For a fanout, the list is expanded by `output_names`, and each output name points at the upstream entity that produced it. `output_names` runs in the main process and is called more than once per run. A reduce always has exactly one entry: its output name points at every upstream entity name, which is an empty list when the upstream is empty. A source has an empty list, because its input is the function, not another node's directory.

When the list is empty, the stage does not compare, does not delete, and does not call the function. The entities already in that epoch stay as they are. For a map or a fanout, this is what happens when the upstream has no entities at all. A reduce's list is never empty: with an empty upstream it still writes its one entity, and the function receives an empty list.

#### Comparison with disk

When the list is not empty, the runner rereads this node's entities in the epoch and puts them in three groups.

A name that is in the list and missing from the directory is created. An entity that is in the directory and absent from the list is deleted. An entity in both is compared, through `upstream` in its `tag.json`, with the current upstream, and is redone when any of these does not hold: the snapshot exists and is valid; the set of recorded names equals the list, without duplicates; every record names this upstream node; every record carries this epoch; and every record's hash is non-empty and equal to the hash of the current upstream body and user tag. An entity whose own `tag.json` is invalid is also redone. An entity that passes stays where it is, and the function is not called for it in this stage.

#### Clearing

After the comparison and before any function is called, the runner reorganizes the directory in one pass. It deletes the entities to be deleted, deletes the directories of the entities to be redone, and then places a directory that holds only an empty `tag.json` for every name to be created or redone. The names waiting to be written are the new names, sorted, followed by the redone names, sorted.

Clearing covers the whole stage at once, not one entity at a time. As soon as the stage starts executing, every entity to be redone has already lost its old body. If the stage fails partway, the entities not yet reached stay with only an empty `tag.json` until a later run writes them.

### Executing a stage

#### Filling and the snapshot

A map or a fanout calls the function once for each name waiting to be written: `transform_data` fills the body, then `transform_props` fills the tag. They must be a string and an object, otherwise that entity fails with `FatalError`. The runner then merges `global_prop`, drops `current`, computes the snapshot from the upstream body and user tag as they are at that moment, writes it as `upstream`, and writes everything in the order given in chapter 2. A reduce does the same for its one output, and its snapshot includes every upstream entity that took part. A source drops `current` and does not write `upstream`.

The function does not write the snapshot. When an upstream entity has no `data` file, for example because the upstream stopped partway last time and left only an empty directory, this call fails with `FatalError`. In normal order this does not happen, because the upstream stage runs first and finishes that entity.

The runner constructs a new function instance for every attempt at every entity, so instance state is never carried from one entity to the next.

#### Slices and processes

A map or a fanout cuts the names waiting to be written into contiguous slices by `parallelism`. The number of slices does not exceed the parallelism, and does not exceed the number of names. With one slice, the names are written in order in the current thread. With more than one, each slice gets its own worker thread, and execution inside a slice is still sequential. The threads share the operator and the function parameters. A reduce is not sliced. When `parallelism` is less than 1, the stage fails with `OperatorValidationError` as soon as there are names to write.

Worker threads are started through Python's `ThreadPoolExecutor`. They do not start another process, and the script that starts the job does not need `if __name__ == "__main__":` for this.

When an entity in one slice finally fails, the entities after it in that slice are not attempted. The other slices run to the end, and the exception is raised only after every slice has finished. After a parallel failure, therefore, the finished entities on disk may include more than the ones before the failure point.

#### Retry

The call for one entity follows `retry`. A `FatalError` is not retried, and the stage fails at once. Any other exception, including a non-zero status from an external process, is tried again after waiting `backoff_seconds × attempts so far` seconds, until `max_attempts` attempts have been made. When the last attempt still fails, the exception leaves the stage and the run stops at the current node.

Entities that already have `upstream` written in `tag.json` in this stage stay in the directory. On another run of the same job and the same epoch, those entities pass the comparison and are kept, and the runner writes only the rest, plus any whose upstream changed again.

### The source stage

A source does not build expected names and does not take part in the comparison above. Whether it rewrites depends only on whether this run passed `start_from_scratch=True`.

When it was not passed, the source does not call its function and does not change its output directory, apart from ensuring the directory and marker exist. Downstream stages read the entities already at that path. If the very first run does not pass it, downstream sees an empty epoch: maps and fanouts do nothing, and a reduce writes a result from empty input.

When it was passed, the runner reads the records yielded by `emit` one at a time and writes each as an entity as soon as it arrives. The entity name must be valid, the body must be a string, the tag must be an object, and no snapshot is written. Yielding the same name twice fails the stage with `OperatorValidationError`. When a source writes an entity, it overwrites `data` and `tag.json` directly, without clearing the entity directory first. After every record has been yielded, names in this epoch that were not yielded this time are deleted, so the entities in the directory match this run's records.

A source's `retry` covers only the step that writes one record to disk. An exception raised by `emit` itself, for example a source file that is not UTF-8, is not retried and fails the stage directly. Records yielded before that point have already been written, and old entities not yet yielded this time are not deleted. The next run that generates from scratch restores consistency.

## 4. Running the same epoch again

On another run, the runner applies the comparison from chapter 3 to every node except sources. All cases together:

| Case | What this stage does to the entity |
| --- | --- |
| In the list, missing from the directory | Created and executed |
| In the directory, absent from the list | Whole entity directory deleted |
| In both, snapshot matches the current upstream | Kept, function not called |
| In both, snapshot missing or invalid, or tag invalid | Cleared and redone |
| In both, recorded name set, node, epoch, or entity hash differs | Cleared and redone |
| Map or fanout whose upstream has no entities | No comparison, directory left as is |
| Reduce whose upstream has no entities | Compared as usual, function receives an empty list |

Several common situations follow from this table.

#### The last run stopped partway

In the stage that failed, entities whose snapshot was written are kept. Entities that only have an empty `tag.json` and no snapshot are redone. The downstream of the failed node never started last time, so it runs from the beginning now. Non-source nodes before the failed one pass the comparison, as long as their upstream did not change, and their functions are not called again.

#### An upstream entity changed

Downstream entities that depend on an upstream entity whose body or user tag changed are redone. If a redone entity writes the same body and user tag as before, its own downstream passes the comparison and the redo stops there. Otherwise the redo continues down the graph. For a reduce, a change to the body or user tag of any upstream entity, or an upstream entity appearing or disappearing, redoes its one output. Without `start_from_scratch`, editing `data` or `tag.json` in an already written upstream entity directory also redos dependents on the next run.

#### Upstream entities appeared or disappeared

A new upstream entity shows up as a creation in a map downstream, and a vanished upstream entity shows up as a deletion. The one exception is an upstream with no entities left at all: the expected names of a map or fanout are then empty, and the downstream directory is left as it is rather than emptied.

#### The operator itself changed

When a template, a parameter, the function code, or an external tool changed while the upstream entities did not, the snapshots still match and the old results are kept. To make the new logic take effect, delete that node's `<epoch>/` directory or some entity directories in it, or use another epoch. Deleting only `upstream` from an entity's `tag.json` also makes it redo, and keeps the directory available for inspection until the redo starts.

#### The source does not regenerate

Without `start_from_scratch=True`, changes to the source files do not reach the source's entities, so downstream does not see them either. Only when that flag is passed does the source reread its input, and the change starts propagating from the root of the graph.

## 5. End to end: a two-stage job

Take the job from the README quick start. The source node `notes` reads a directory, the map node `prompt` renders each entity with the template `Note: {{ data }}`, and the epoch is `demo`. The directory holds only the entity `hello`, whose `data` is `hello`.

```text
runs/notes/demo/hello/                 runs/prompt/demo/hello/
  data       "hello\n"                    data           "Note: hello\n"
  tag.json   the input entity's tag       tag.json       copy of the upstream tag,
                                                         with upstream:
                                                           { operator: "notes",
                                                             name: "hello",
                                                             epoch: "demo",
                                                             hash: body and user tag }
```

The first run passes `start_from_scratch=True`. Assembly loads both function classes. The `notes` stage checks and creates its output directory, writes the marker, and writes the input entity `hello` as an output entity, without a snapshot. The `prompt` stage reads the upstream and gets the list `hello → [hello]`. Its own directory is empty, so `hello` is created with an empty `tag.json`, rendered, and written in order: body, tag, and a snapshot that points at `notes/hello`.

Then the input entity's `data` is changed to `changed`, and the second run does not pass `start_from_scratch`. The `notes` stage does not call its function, so the entity `hello` still holds the old body. The `prompt` stage compares the snapshot: the node name, entity name, epoch, and hash all match the upstream, so `prompt/demo/hello` is kept and the function is not called. The output is still `Note: hello`.

The third run passes `start_from_scratch=True`. `notes` rereads the directory and overwrites the body of `hello` with `changed\n`. `prompt` finds that the hash no longer matches. Clearing deletes the old directory and puts back an empty `tag.json`, and the render then writes `Note: changed` with a new snapshot.

If the input entity `hello` is renamed to `bye` before the third run, `notes` writes `bye` and deletes `hello`. The list of `prompt` becomes `bye → [bye]`, so `bye` is created and `hello` is deleted. If the source directory is emptied instead, `notes` deletes `hello`, but the list of `prompt` is empty, and `prompt/demo/hello` stays as it is.

## 6. Adding a transform

The functions in the package cover two kinds of work: producing entities from a directory, and mapping existing entities one by one. Reduce and fanout have base classes only. Implement them in an operator home when you need them. Chapter 6 of [functions.en.md](functions.en.md) has two examples that run as written.

When a new transform is still "a batch of objects, one call per object", subclass the map base class, implement `transform_data` and `transform_props`, and set `type` and `class` in `props.json`. Files that ship with the operator live inside the home. One call handles only the upstream entity it was given and that entity's target, and hands the body and tag to the runner to persist. The thread pool, retry, clearing, and snapshot are done by the runner from the scheduling fields in the home. The function does not need its own copy of any of them.

A function should tell two kinds of failure apart. Problems that another attempt cannot fix, such as missing configuration or malformed input, should raise `FatalError` so the stage stops at once. Problems that may clear up on their own, such as a network or external process failure, should raise another exception and let `retry` handle them.

When a transform needs to read two results, a node in this version cannot declare two upstreams. The caller can first fold the two results into one with an operator, or the function can read a file the other result has already written. That second kind of read does not enter the snapshot, so when that file changes, the runner does not redo the entity because of the snapshot.

## Appendix A: implementation index

| Path | Responsibility |
| --- | --- |
| `src/docorder/core/artifact.py` | Read-only files in an operator home |
| `src/docorder/core/entity.py` | Entity name checks, reading and writing entity directories, snapshots and comparison |
| `src/docorder/core/environment.py` | Function parameters and template variables |
| `src/docorder/core/storage.py` | The entity table of one epoch directory, and creating, clearing, and deleting |
| `src/docorder/core/operator.py` | The home contract, nodes, expected names, one execution of each of the five operators, slicing |
| `src/docorder/core/job.py` | The job graph, validation, and topological order |
| `src/docorder/core/runner.py` | Assembly, stage execution, and the output marker |
| `src/docorder/utils/retry.py` | The retry policy and how it applies to one entity call |
| `src/docorder/utils/paths.py` | `DOCORDER_HOMES` and home lookup |
| `src/docorder/utils/modules.py` | Loading `primary:Class` and `module:Class` |
| `src/docorder/functions/` | Function base classes; built-in implementations are in `functions/impl/` |
| `tests/test_contract.py` | Contract tests for the behaviour above |

## Appendix B: further reading

- [concurrent.futures.ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor): the thread pool used to slice maps and fanouts.

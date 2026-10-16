# Glossary

[中文](glossary.md)

This page fixes the names that the documents and the code keep using. How an entity is stored, and how one stage advances, is in [docs/design.en.md](docs/design.en.md). How each function is configured is in [docs/functions.en.md](docs/functions.en.md).

## Entity

An entity is one object of one transform. On disk it is one directory under an epoch directory, and the directory name is the entity name. `data` is the body, and `tag.json` holds traits that downstream stages use for filtering and templates. Once an entity with an upstream is finished, the snapshot lives in `tag.json` as `upstream`.

## Upstream snapshot

The upstream snapshot is the `upstream` key in `tag.json`. It records every upstream entity this entity read: the upstream node name, the entity name, the epoch, and the sha256 of the body together with the user tag. One upstream is one record; none or several is a list. It covers the upstream body and user tag, not this operator's configuration. A source does not write this key.

## Operator and operator home

An operator is a reusable transform. Its static files live in an operator home, found through `DOCORDER_HOMES`, and the home does not record the output path of any one run. `type` and `class` in `props.json` decide the kind and the function to load, and a job cannot change those two. `type` is one of `source`, `map`, `reduce`, `fanout`, and `output`. An `output` node writes upstream bodies as files under `.job_result` at the job root.

## Function

A function is the Python class an operator home loads. It reads upstream entities and fills in the body and tag of the target entity. `class` is written as `module:Class`, or as `primary:Class` to load `primary.py` inside the home. Persisting, snapshots, retry, and parallelism belong to the runner, not to the function.

## Job and node

A job is a directed acyclic graph. `Job` takes a job name and an output root. A point in the graph is a node. It refers to one operator home and has its own name, parameter overrides, and, except for a source, exactly one upstream. A node's output path is its name under the output root.

## Epoch

An epoch is the name of the subdirectory that holds the entities. The caller of `execute` passes it in. A different epoch is a different set of subdirectories. On another run of the same epoch, the runner uses the upstream snapshots to decide whether each entity is executed, redone, kept, or deleted.

## Stage

A stage is one node's whole execution for one epoch. Downstream starts only after that execution has finished.

## Expected names

The expected names are what a stage computes from the upstream entities when it starts: "output name → the upstream entity names it depends on". The runner compares them with the entities already in this node's directory. Names in the list but missing from the directory are created, entities in the directory but absent from the list are deleted, and entities in both are kept or redone according to their upstream snapshot.

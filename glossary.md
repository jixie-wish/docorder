# 术语

[English](glossary.en.md)

这里固定文档和代码里反复出现的叫法。实体怎么存放、一次 stage 怎么推进，见 [docs/design.md](docs/design.md)。每个 function 怎么配置，见 [docs/functions.md](docs/functions.md)。

## 实体

实体是一次转换的一个对象，在磁盘上是 epoch 目录下的一层子目录，目录名就是实体名。`data` 是正文，`tag.json` 是给下游过滤和填模板的特性。有上游的实体完成后，快照写在 `tag.json` 的 `upstream` 里。

## 上游快照

上游快照是 `tag.json` 里的 `upstream`，记下这个实体读过的每个上游实体：上游节点名、实体名、epoch，以及正文连同用户 tag 的 sha256。一个上游时是一条记录，没有或多个上游时是列表。它覆盖上游正文和用户 tag，不覆盖本算子的配置。source 不写这个键。

## 算子与算子 home

算子是可复用的转换。它的静态文件放在算子 home 里，home 由 `DOCORDER_HOMES` 搜索到，不记录某一次运行的输出路径。`props.json` 里的 `type` 与 `class` 决定种类和要加载的 function，作业不能改这两项。`type` 取 `source`、`map`、`reduce`、`fanout`、`output`。`output` 把上游正文写成作业根目录下 `.job_result` 里的文件。

## Function

function 是算子 home 加载的 Python 类，负责读入上游实体并填写目标实体的正文和 tag。`class` 写成 `模块:类名`，或写成 `primary:类名` 以加载 home 下的 `primary.py`。落盘、快照、重试和并行由 runner 负责，不由 function 负责。

## 作业与节点

作业是一张有向无环图，`Job` 接收作业名和输出根目录。图中的一个点称为节点，它引用一个算子 home，有自己的名字、参数覆盖，以及除 source 以外的唯一上游。节点的输出路径是输出根目录下的节点名。

## Epoch

epoch 是实体所在的那层子目录名，由 `execute` 的调用方传入。换一个 epoch 等于换一套子目录。同一个 epoch 再跑时，runner 按上游快照决定每个实体执行、重做、留下还是删除。

## Stage

stage 是一个节点在一次 epoch 里的整段执行。下游要等这段结束才开始。

## 应得名单

应得名单是一个 stage 开始时根据上游实体算出的「输出名 → 它依赖的上游实体名」。runner 拿它和本节点目录里已有的实体比较：名单里有而目录里没有的新建，目录里有而名单里没有的删除，两边都有的按上游快照决定留下还是重做。

# Changelog

[English](CHANGELOG.en.md)

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

- `tag.json` 不再写入 `current`。下游快照按上游实体此刻的正文和用户 tag 计算；手动改已写出实体的 `data` 或 `tag.json`，下一次运行会重做依赖它的下游。
- `PromptToLLM` 在工具自己写出目标实体的 `data` 时保留该文件，检查它是非空 UTF-8 文本后只补 `tag.json`。没有这份文件时，正文仍是标准输出。
- 上游快照改写在 `tag.json` 的 `upstream` 里，不再写 `upstream.json`。写出时会删掉目录里残留的那份文件。
- 每个 stage 在标准错误输出上打印一条进度条，标题是节点名。map、fanout、reduce、output 的总数是这次要处理的个数；source 在 `emit` 时逐条推进。
- `DirectorySource` 读取已经符合实体约定的子目录：目录名是实体名，正文来自 `data`，tag 来自 `tag.json`。普通文件和残缺目录会被跳过。
- 新增 `output` 算子。作业根目录下的 `.job_result` 是作业整体输出。output 把上游本 epoch 每个实体的正文写成该目录下的文件；文件名缺省是实体名，也可由 `name_template` 用实体 tag 渲染。参数 `directory` 可以换成别的写出目录，相对路径相对算子 home 解析。
- `LLMTool` 移到 `docorder.utils.llm_tool`。
- `Artifact` 和 `Environment` 移到 `docorder.core`。
- 内置 function 移到 `docorder.functions.impl`。基类改名为 `source_function`、`map_function`、`reduce_function`、`fanout_function`、`rendered_map`。`props.json` 的 `class` 要写成新模块路径。
- `Environment` 只保留 `operator_props`（function 参数）和 `template_env`（模板用的 `operator` / `job` / `entity`）。去掉 `config`、`bind`、`namespace`、`bindings`、`format_named`。
- map 和 fanout 的 `parallelism` 改为线程池，不再使用进程池。分片线程共享算子，参数不必能被 pickle，也不再要求启动脚本写 `if __name__ == "__main__":`。
- `OperatorNode` 构造时把节点 `config` 覆盖进 `props`，之后不再保留 `config`，对外只暴露 `props`。`Operator.of` 再把节点的公开字段抬到算子上，此后 runner、function 和模板环境都读算子，不再经过节点。`Function` 持有 `environment`：`environment.config` 是 function 参数，`environment.operator` 是模板视图，都从 operator 生成。渲染某个实体时用 `environment.bind` 填上 `entity`。新增对应的契约测试。
- 新增 `docs/guide.md` 使用指南：背景、核心概念、工作流程、使用场景、配置、按算子类型列出的内置 function、渲染类 function 的模板变量及扩充方法、开发自己的 function，以及在自己的项目中使用 docorder 的完整示例。暂无英文版。
- 文档按当前代码核对并改写。README 改为从仓库用 `uv sync` 安装，补上获取代码、环境要求、可运行的快速开始与再跑示例、配置和排错。`docs/design.md` 更正了同名节点、reduce 空上游、整段清场、并行失败和 source `emit` 失败时的行为，并新增再跑判定表与端到端示例。`docs/functions.md` 补上失败与重试对照、`Command` 相对路径的解析方式，以及 reduce 与 fanout 的实现例子。`SECURITY.md` 与介绍页删去并不存在的 `cursor` 预设。
- `docs/design.md` 按当前的 stage 调度重写：实体、算子与作业的状态，epoch 目录，以及同一次运行如何比较上游并落盘。
- 文档提供中英两份。中文使用原文件名，英文使用同名加 `.en` 后缀。README 按当前的 `Job` 与 `execute` 重写。
- 项目介绍页在 `docs/index.html`。
- function 的说明集中在 `docs/functions.md`。每个 function 是 `src/docorder/functions/` 下的一个模块。
- source 算子只接收 function。function 用 `emit` 交出实体的 data 和 tag。`DirectorySource` 从目录产出实体，读取已有的实体子目录（`data` 与 `tag.json`）。`FilteredDirectorySource` 按 `filter` 的名字结尾和 `data` 大小筛选。
- 包内不再附带算子 home。home 由 `DOCORDER_HOMES` 提供，具体算子随后再实现。
- `execute` 只接收 epoch。一次运行按拓扑顺序跑完整张图。
- 算子 `props.json` 只用 `type`：`source`、`map`、`reduce`、`fanout`。
- 实体按 epoch 子目录存放。上游算子、实体名、epoch 和 hash 写在实体目录的 `upstream.json` 里。同一 epoch 再跑时执行未做的、删除多出来的、重做上游变了的。
- 项目名为 docorder。包、命令行，以及 `DOCORDER_DG`、`DOCORDER_LLM`、`DOCORDER_HOMES` 都使用这个名字。
- 可复用算子实现放在 `src/docorder/operators/`，stage 调度放在 `src/docorder/runner.py`。
- data-governance 的 documentation、data-quality、semantic-physical、semantic-ontology 改为 `examples/data_governance/` 下的脚本，不再通过 `docorder run` 打进安装包。
- `llm` / `llm_batch` 通过可配置工具调用模型。内置预设是 `cursor`，也可以传入一份命令 JSON。

## [0.1.0] - 2026-10-12

- 按 stage 调度目录实体，支持重试、epoch checkpoint、跳过算子和从指定算子恢复。
- 随包提供 jsonnet、模板 prompt、Cursor、命令、CSV fan-out、拼接和 review 算子。
- 提供 documentation、data-quality、semantic-physical、semantic-ontology 四类 job。这些 job 需要一份布局相符的外部仓库，路径用 `--dg` 或 `DOCORDER_DG` 指定。

# Docorder

[![CI](https://github.com/jixie-wish/docorder/actions/workflows/ci.yml/badge.svg)](https://github.com/jixie-wish/docorder/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)

[English](README.en.md)

Docorder 是一个 Python 库，用来对一批结构相同的对象做多步转换，例如每张表先渲染提示词、再调用模型。每个对象是磁盘上的一个目录，称为实体。转换沿一张有向无环图逐段执行，一个算子处理完整批实体，下游才开始。运行中断后，用同一个 epoch 再跑一次即可：每个实体的 `tag.json` 里记着它读过的上游，runner 据此只补没做完的、重做上游变了的、删掉多出来的。

作业从 Python 里构造并调用 `execute` 启动。目前没有可用的命令行入口。

## 获取代码

```bash
git clone https://github.com/jixie-wish/docorder.git
cd docorder
```

仓库没有子模块，也不用 Git LFS。

## 环境要求

- [Python](https://www.python.org/downloads/) 3.10 或更高版本。`pyproject.toml` 要求 `>=3.10`，CI 在 3.10 和 3.12 上运行。
- [uv](https://docs.astral.sh/uv/getting-started/installation/)。安装、测试和 lint 都通过它执行。本文的命令在 uv 0.8.14 上验证过。

确认两者可用：

```bash
python3 --version
uv --version
```

下面的外部程序只在用到对应 function 时才需要：

- `JsonnetToPrompt` 调用 `PATH` 上的 `jsonnet`。CI 在 Ubuntu 上用 `sudo apt-get install -y jsonnet` 安装。
- `Command` 和 `PromptToLLM` 运行你在配置里写的命令，需要这些命令在本机可用。包里不附带任何模型工具预设。

## 安装

在仓库根目录执行：

```bash
uv sync
```

这会创建 `.venv`，装上本库和运行时依赖 Jinja2、PyYAML。要跑测试和 Ruff，改用 `uv sync --group dev`。

> [!IMPORTANT]
> PyPI 上没有 `docorder` 这个项目，`pip install docorder` 不会成功。请从克隆下来的仓库安装。

## 快速开始

下面的脚本建一个两段作业：source 把目录里的每个文件变成一个实体，map 用 Jinja 模板为每个实体渲染一行文字。它只用到随安装装上的 Jinja2。

把内容存为仓库根目录下的 `quickstart.py`：

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

运行：

```bash
uv run python quickstart.py
```

成功时输出：

```text
Note: hello
```

运行结束后，`quickstart/runs/` 下是这样：

```text
quickstart/runs/
  notes/                    source 节点
    .docorder-output
    demo/hello/
      data                  "hello\n"
      tag.json              来自输入实体的 tag.json
  prompt/                   map 节点
    .docorder-output
    demo/hello/
      data                  "Note: hello\n"
      tag.json              含 upstream：上游算子 notes、实体 hello、epoch demo、上游正文的 sha256
```

实体名 `hello` 是输入目录 `notes/hello` 的目录名。`demo` 是这次运行的 epoch，也是实体所在的那层目录名。

> [!NOTE]
> 脚本把工作放在 `main()` 里，并用 `if __name__ == "__main__":` 调用。这是普通脚本的写法。`parallelism` 大于 1 时，runner 在当前进程里用线程分片，不再另起子进程。

## 配置

### 算子 home

算子 home 是一个目录，里面的 `props.json` 声明这个算子用哪种类型、哪个 function 类，以及参数。home 不随包分发。运行前把 home 所在的目录写进环境变量 `DOCORDER_HOMES`。多个目录用系统的路径分隔符隔开，和 `PATH` 一样，靠前的同名 home 优先。home 可以直接放在列出的目录下，也可以再放进一层分类目录。

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "parallelism": 4,
  "retry": { "max_attempts": 3, "backoff_seconds": 5 },
  "template": "lib/prompt.jinja"
}
```

`type` 取 `source`、`map`、`reduce`、`fanout`、`output` 之一。`class` 写成 `模块:类名`；类在 home 自己的 `primary.py` 里时，写成 `primary:类名`。这两项作业不能改。`parallelism` 缺省为 1，`retry` 缺省为只尝试一次。其余键都是 function 的参数，各 function 接受哪些参数见 [docs/functions.md](docs/functions.md)。`output` 把上游正文写成作业根目录下 `.job_result` 里的文件。

### 作业

`Job(name, root)` 的第二个参数是输出根目录。`add_operator_node(节点名, home名, upstream=..., config=..., parallelism=..., retry=...)` 加入一个节点。节点的输出写到 `输出根/节点名/epoch/实体名/`。除 source 以外，每个节点用一个字符串声明唯一的上游。

`config` 覆盖 home 里同名的 function 参数。调度字段要用 `parallelism=`、`retry=` 两个参数覆盖；写进 `config` 的同名键只会成为 function 参数，不改变调度。`retry=` 接收 `docorder.utils.retry.RetryPolicy(max_attempts=..., backoff_seconds=...)`。同一个节点名再次添加，会替换掉先前的节点，不会报错。

### 运行

`execute(job, epoch, start_from_scratch=False)` 按拓扑顺序跑完整张图。`epoch` 会直接拼进路径，应写成一层目录名，例如日期。只有 `start_from_scratch=True` 时，source 才会重新读取输入；否则 source 不改动自己的输出，下游读取该 epoch 里已有的实体。每个 stage 在标准错误输出上打印一条以节点名为标题的进度条。

| 环境变量 | 用途 |
| --- | --- |
| `DOCORDER_HOMES` | 查找算子 home 的目录列表，在 `add_operator_node` 之前就要设好 |
| `DOCORDER_LLM` | `PromptToLLM` 没有配置 `tool` 时使用的工具，取 home 里的预设名或一份 JSON 文件路径 |

## 示例：同一个 epoch 再跑

在快速开始之后，存一个 `rerun.py`。它沿用 `quickstart/` 里的 home 和输出，先改源文件，再跑两次同一个 epoch：

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

输出：

```text
Note: hello
Note: changed
```

第一次调用没有从头生成，source 的实体还是旧正文，`prompt/demo/hello` 的快照与上游一致，于是原样留下。第二次调用让 source 重读文件，上游正文的哈希变了，`prompt` 清空这个实体并重新渲染。runner 只比较上游正文：改了模板或参数、但上游正文没变的实体，不会自动重做。要强制重做，删掉对应的实体目录，或换一个 epoch。完整的判定规则见 [docs/design.md](docs/design.md)。

试完可以删掉 `quickstart/`、`quickstart.py` 和 `rerun.py`。

reduce 和 fanout 没有现成的 function，需要在 home 的 `primary.py` 里自己实现。[docs/functions.md](docs/functions.md) 的最后一章给出两个可以直接运行的例子。

## 排错

| 现象 | 原因与处理 |
| --- | --- |
| `FileNotFoundError: operator home '…' not found in: …` | `DOCORDER_HOMES` 没有指向含该 home 的目录，或那个目录里没有 `props.json`。环境变量要在 `add_operator_node` 之前设好。 |
| `FatalError: refuse to use … as an operator output` | 节点的输出目录已有内容，却没有 `.docorder-output` 标记。runner 不会覆盖它。换一个输出根，或换一个节点名。 |
| `FatalError: directory source path is not a directory` | `directory` 指向的目录不存在。相对路径按算子 home 解析，不按当前目录。 |
| `FatalError: jsonnet is not on PATH` | 用了 `JsonnetToPrompt`，但本机找不到 `jsonnet`。这类错误不重试。 |
| `DocorderError: command did not write …` | `Command` 的 `output_file` 是相对路径。docorder 按 Python 进程的当前目录找它，不按 `cwd`。改用绝对路径，或写成 `{entity.output}/文件名`。 |
| 改了源文件，下游没变 | 这次 `execute` 没有传 `start_from_scratch=True`，source 没有重读输入。 |
| 改了模板，旧结果没变 | 上游正文没变，快照仍然吻合。删掉该节点的 `<epoch>/` 目录或其中的实体目录，或换一个 epoch。 |
| 某个实体每次都重做 | 它的上游正文是空字符串。空正文的哈希记为空，比较总不通过。 |
| 想看输出根目录里有哪些 epoch | `docorder status <输出根目录>`。它列出每个 epoch 是否与上游快照一致，以及每个 stage 的实体数。目录不存在时命令以状态码 1 退出。 |

`FatalError` 表示配置或输入有问题，不会重试，例如缺参数、模板变量不存在、找不到可执行文件。其它异常按 `retry` 重试当前实体。重试用尽后运行停在当前算子，已经写好 `tag.json` 里 `upstream` 的实体留在磁盘上，下次用同一个 epoch 运行会从剩下的实体继续。`JobValidationError` 在任何算子执行前抛出，表示作业图本身有问题，例如有环、上游不在图中，或节点依赖自己。

## 测试

本仓库没有单独的构建或部署步骤。开发时运行：

```bash
uv sync --group dev
uv run ruff check
uv run pytest
```

`ruff check` 检查整个仓库，`pytest` 运行 `tests/`。`make quality` 和 CI 里还引用了 `examples/` 下的脚本，这些脚本目前不在仓库中，在本地跑这两处会失败。

## 文档

- [docs/guide.md](docs/guide.md)：使用指南。从背景、概念、工作流程讲到配置、内置 function、模板变量、开发自己的 function，以及在自己的项目中使用 docorder 的完整示例。
- [docs/functions.md](docs/functions.md)：每个 function 的参数、模板变量，以及如何在 home 里实现 function。
- [docs/design.md](docs/design.md)：实体、算子和作业各保存什么，一次运行在磁盘上写下什么，同一个 epoch 再跑时怎样判定。
- [glossary.md](glossary.md)：文档里固定使用的术语。
- [docs/index.html](docs/index.html)：项目介绍页。

英文版与中文同名，后缀为 `.en`，例如 `README.en.md`、`docs/design.en.md`。

## 参与贡献

问题和需求在 [GitHub Issues](https://github.com/jixie-wish/docorder/issues) 提交，仓库带有 bug 和 feature 模板。安全问题不要公开提交，做法见 [SECURITY.md](SECURITY.md)。开发约定见 [CONTRIBUTING.md](CONTRIBUTING.md)，行为准则见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。`0.x` 期间接口可能调整，变更记在 [CHANGELOG.md](CHANGELOG.md)。

> [!WARNING]
> `JsonnetToPrompt`、`Command` 和 `PromptToLLM` 会在本机执行作业配置和实体正文里的内容。只对受信任的目录运行作业。

## 许可证

[MIT](LICENSE)。

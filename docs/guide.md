# docorder 使用指南

**目录**

- [文档结构](#文档结构)
- [一、背景](#一背景)
  - [要解决的问题](#要解决的问题)
  - [一个最小的例子](#一个最小的例子)
  - [设计取舍](#设计取舍)
  - [本版边界](#本版边界)
- [二、核心概念与术语](#二核心概念与术语)
  - [实体](#实体)
  - [上游快照](#上游快照)
  - [算子与算子 home](#算子与算子-home)
  - [function](#function)
  - [作业与节点](#作业与节点)
  - [epoch 与 stage](#epoch-与-stage)
  - [runner 与应得名单](#runner-与应得名单)
  - [概念之间的关系](#概念之间的关系)
  - [术语对照](#术语对照)
- [三、工作流程](#三工作流程)
  - [装配](#装配)
  - [一个 stage 的经过](#一个-stage-的经过)
  - [并行与重试](#并行与重试)
  - [source 节点的 stage](#source-节点的-stage)
  - [再次运行时的判定](#再次运行时的判定)
  - [一次运行留下的目录](#一次运行留下的目录)
- [四、使用场景](#四使用场景)
  - [批量生成提示词并交给大模型](#批量生成提示词并交给大模型)
  - [从结构化数据生成配置文件](#从结构化数据生成配置文件)
  - [为每个文件运行命令行工具](#为每个文件运行命令行工具)
  - [汇总与拆分](#汇总与拆分)
  - [不适合的场景](#不适合的场景)
- [五、配置](#五配置)
  - [让 docorder 找到算子 home](#让-docorder-找到算子-home)
  - [props.json](#propsjson)
  - [作业与节点](#作业与节点-1)
  - [execute](#execute)
  - [function 读到的参数与模板读到的算子信息](#function-读到的参数与模板读到的算子信息)
  - [环境变量](#环境变量)
- [六、算子分类与内置 function](#六算子分类与内置-function)
  - [五种算子](#五种算子)
  - [source 算子](#source-算子)
  - [map 算子](#map-算子)
  - [reduce 算子](#reduce-算子)
  - [fanout 算子](#fanout-算子)
  - [output 算子](#output-算子)
  - [失败与重试](#失败与重试)
- [七、渲染类 function 与模板变量](#七渲染类-function-与模板变量)
  - [RenderedMap 的三个步骤](#renderedmap-的三个步骤)
  - [渲染环境](#渲染环境)
  - [内置模板变量](#内置模板变量)
  - [增加模板变量](#增加模板变量)
  - [变量同名时以谁为准](#变量同名时以谁为准)
- [八、开发自己的 function](#八开发自己的-function)
  - [选择基类](#选择基类)
  - [function 中可以使用的对象](#function-中可以使用的对象)
  - [必须遵守的约定](#必须遵守的约定)
  - [代码放在哪里](#代码放在哪里)
  - [示例：自定义 source](#示例自定义-source)
  - [示例：map](#示例map)
  - [示例：基于 RenderedMap](#示例基于-renderedmap)
  - [示例：reduce](#示例reduce)
  - [示例：fanout](#示例fanout)
  - [测试 function](#测试-function)
- [九、在自己的项目中使用 docorder](#九在自己的项目中使用-docorder)
  - [第一步：安装 docorder](#第一步安装-docorder)
  - [第二步：规划目录](#第二步规划目录)
  - [第三步：准备输入数据](#第三步准备输入数据)
  - [第四步：编写算子 home](#第四步编写算子-home)
  - [第五步：编写启动脚本](#第五步编写启动脚本)
  - [第六步：运行并查看结果](#第六步运行并查看结果)
  - [第七步：修改之后再次运行](#第七步修改之后再次运行)
  - [纳入版本管理](#纳入版本管理)
- [附录 A：内置 function 一览](#附录-a内置-function-一览)
- [附录 B：实现索引](#附录-b实现索引)
- [附录 C：相关文档](#附录-c相关文档)

---

docorder 是一个 Python 库，用来批量处理一组结构相同的对象。所谓「对象」，可以是一张表的定义、一篇笔记、一份配置文件，或者任何能用一段文本表示的东西。使用者先把要做的加工拆成几个先后相连的步骤，例如「读取文件」「套用模板生成提示词」「把提示词交给大模型」「把所有回答汇总成一份清单」，然后把这些步骤连成一张作业图交给 docorder 执行。docorder 会把每个对象在每一步的结果都写成磁盘上的一个目录，并在目录里记下这个结果是根据哪份上游内容算出来的；因此，当某一步中途失败，或者输入发生了变化时，再运行一次，docorder 只会补做失败的部分和受变化影响的部分，已经完成而且仍然有效的结果会原样保留。

本指南面向第一次使用 docorder 的读者，不要求事先了解项目里的任何术语。第一章先说明 docorder 想解决什么问题，并用一个只有两步的最小例子演示一个作业从配置到运行的全过程，后面各章会反复借用这个例子。第二章逐一定义例子里出现的概念，第三章按时间顺序讲一次运行内部发生了什么，第四章介绍适合使用 docorder 的场景，第五章到第七章分别讲配置项、docorder 自带的各种转换，以及模板里能使用的变量，第八章讲如何编写自己的转换，第九章用一个完整的项目示例，一步一步说明如何在自己的仓库里使用 docorder。

本指南的内容以当前代码为准。有两点需要事先说明：docorder 目前还没有发布到 PyPI，需要从源码仓库安装，安装步骤在第九章第一步；运行作业仍然在 Python 脚本里调用 `execute`。安装后的 `docorder status <输出根目录>` 用来查看这个目录里有哪些 epoch、每个 epoch 的结果是否与上游快照一致，以及每个 stage 在每个 epoch 下有多少实体。

如果你是第一次接触 docorder，建议按顺序读完前三章，建立整体印象之后，再根据需要查阅第五章到第七章；如果你打算编写自己的转换逻辑，请阅读第八章；如果你希望尽快在自己的项目中用起来，可以直接跳到第九章照着做，遇到不理解的名词时再回到前面对应的章节。

## 文档结构

1. 背景：docorder 要解决的问题，一个两步作业的最小例子，docorder 在设计上做了哪些取舍，以及当前版本有哪些能力边界。
2. 核心概念与术语：实体、上游快照、算子与算子 home、function、作业与节点、epoch 与 stage、runner 与应得名单，每个概念都说明它是什么、由谁创建、保存在哪里。
3. 工作流程：一次运行从检查作业图开始，到逐个节点执行结束，中间每一步做了什么；还包括并行执行、失败重试、source 节点的特殊处理，以及再次运行时 docorder 如何决定每个结果的去留。
4. 使用场景：几种典型的作业图分别适合什么任务，以及哪些任务不适合用 docorder。
5. 配置：docorder 如何找到算子、`props.json` 里每个键的含义、作业和节点的参数、运行函数 `execute` 的参数、转换代码和模板分别读到哪些配置，以及相关的环境变量。
6. 算子分类与内置 function：五种算子的区别，每种算子可以搭配哪些 docorder 自带的转换类，每个转换类有哪些配置项、产生什么结果、在什么情况下失败。
7. 渲染类 function 与模板变量：模板里可以直接使用的全部变量，以及在内置变量不够用时，六种增加模板变量的方法。
8. 开发自己的 function：应该继承哪个基类、需要实现哪些方法、在方法里可以使用哪些对象、必须遵守哪些约定、代码文件放在哪里，以及如何为它编写测试。
9. 在自己的项目中使用 docorder：从安装、规划目录、准备输入数据、编写算子、编写启动脚本，到运行、查看结果和修改后再次运行的完整步骤。

文中有几张结构示意图，分别展示最小例子的文件与运行结果、一个实体目录的组成、各个概念之间的关系、一次运行在磁盘上留下的目录、模板渲染时可用数据的组成，以及第九章示例项目的目录树。

## 一、背景

### 要解决的问题

很多批处理任务都有相同的形状：手里有一批对象，例如几百张数据表的定义、一批笔记或者一组服务的配置，需要对每个对象依次做几步加工，例如先把表定义渲染成一段提示词，再把提示词交给大模型生成说明文字，最后把所有表的说明汇总成一份清单。这样的任务有两个共同的麻烦。第一个麻烦是每一步都可能很慢，也可能失败：调用外部命令可能超时，大模型接口可能限流或者返回错误，模板里也可能有写错的地方。第二个麻烦是输入会不断变化：今天改了其中一张表的定义，明天又新增了几张表，每次变化之后都需要更新结果。

如果只写一个普通的脚本，用循环逐个处理这些对象，那么处理到第三百个对象时出了错，修好问题之后往往只能从头再跑一遍，前面已经花掉的时间和大模型调用费用都白白浪费了。为了避免这种情况，很多人会自己记录「哪些对象已经处理完」，但这份记录放在数据库里，就多了一个需要部署和维护的组件；放在内存里，进程一退出记录就丢失了。更难处理的是判断「已经算好的结果还能不能继续用」：修改了某个输入文件之后，到底哪些下游结果需要重新计算，哪些可以保留，普通脚本通常没有可靠的依据，只能全部重算，或者靠人工判断。

docorder 的做法是把每个对象在每一步的结果都写成磁盘上的一个目录，并在这个目录里记下这一步读取的上游内容的哈希值。哈希值是根据一段内容计算出来的一串固定长度的字符，内容只要有一点变化，哈希值就会完全不同，因此可以用它来判断内容是否被改动过。下次运行时，docorder 只需要把目录里记下的哈希值与上游当前内容的哈希值作比较，就能知道哪些对象还没有处理、哪些对象的结果已经过时需要重做、哪些对象的结果仍然有效可以保留。整个判断过程只依赖磁盘上的文件，不需要数据库，也不依赖上一次运行留在内存里的任何状态。

### 一个最小的例子

下面这个作业读取一个目录中的笔记文件，把每个文件的内容放进一个模板，生成一段提示词。它只有两个步骤，但已经包含了 docorder 的全部基本组成部分，后面各章会反复用它来解释概念。要实际运行这个例子，需要先按第九章第一步安装 docorder。

#### 准备文件

先在任意位置建立下面这样的目录结构。其中 `notes/` 是输入数据，`homes/` 存放描述「每一步做什么」的配置，`run.py` 是启动整个作业的 Python 脚本。

```text
hello-docorder/
  run.py                    启动脚本
  notes/
    hello/
      data                  输入正文，内容是 hello
      tag.json              输入附加信息
  homes/                    存放算子的目录
    notes_source/
      props.json
    prompt/
      props.json
      lib/note.jinja        模板文件，内容是 Note: {{ data }}
```

在 docorder 里，作业中的每一种步骤称为一个算子（operator），描述一个算子的那个目录称为算子 home。上面的 `homes/notes_source/` 和 `homes/prompt/` 就是两个算子 home：前者描述「从一个目录里读取文件」这个步骤，后者描述「用模板生成提示词」这个步骤。docorder 安装包里不附带任何算子 home，算子 home 总是由使用者自己放在项目里。每个算子 home 里都必须有一份名为 `props.json` 的 JSON 配置文件，docorder 正是通过它来认出一个目录是算子 home，并了解这个算子该怎么运行。

`homes/notes_source/props.json` 的内容如下：

```json
{
  "type": "source",
  "class": "docorder.functions.impl.directory_source:DirectorySource"
}
```

`homes/prompt/props.json` 的内容如下：

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "template": "lib/note.jinja"
}
```

`type` 说明这个算子属于哪一类。`source` 类型的算子位于作业的起点，它不读取其它步骤的结果，而是从外部（例如磁盘上的一个目录）产生最初的一批对象；`map` 类型的算子读取上一步的结果，并对其中的每个对象分别做一次转换，每个输入对象对应一个输出对象。`class` 指向真正执行转换的 Python 类，写法是「模块路径:类名」，这个类在 docorder 中称为 function。这里用到的两个 function 都是 docorder 自带的：`DirectorySource` 把一个目录中已经写成实体形状的子目录变成对象，`TemplateToPrompt` 用一个 Jinja 模板为每个对象渲染出一段文本。Jinja 是 Python 中常用的模板语言，模板里用两对花括号包住的部分，例如 `{{ data }}`，会在渲染时被替换成对应变量的值。`props.json` 中除 `type` 和 `class` 以外的键，都会作为参数交给 function 使用，例如 `template` 告诉 `TemplateToPrompt` 使用哪个模板文件，这个路径是相对于算子 home 的。

#### 配置并运行作业

`run.py` 的内容如下：

```python
import os
from pathlib import Path

from docorder.core.job import Job
from docorder.core.runner import execute

ROOT = Path(__file__).resolve().parent


def main() -> None:
    os.environ["DOCORDER_HOMES"] = str(ROOT / "homes")

    job = Job("hello", ROOT / "runs")
    job.add_operator_node("notes", "notes_source", config={"directory": str(ROOT / "notes")})
    job.add_operator_node("prompt", "prompt", upstream="notes")

    execute(job, "demo", start_from_scratch=True)


if __name__ == "__main__":
    main()
```

脚本的第一行实质性代码设置了环境变量 `DOCORDER_HOMES`，它告诉 docorder 到哪个目录里寻找算子 home。这里把它设为项目里的 `homes/` 目录，于是后面提到的 `notes_source` 和 `prompt` 这两个名字，就会分别对应到 `homes/notes_source/` 和 `homes/prompt/`。

`Job("hello", ROOT / "runs")` 创建一个作业。作业描述的是「这一次要把哪些步骤按什么顺序连起来执行，结果写到哪里」。第一个参数是作业的名字；第二个参数是输出根目录，这个作业所有步骤的结果都会写在这个目录下面。

`add_operator_node` 向作业中加入一个节点。节点是作业图中的一个点，它表示「在这个作业里使用某个算子执行一个步骤」。第一次调用加入了一个名为 `notes` 的节点，它使用 `notes_source` 这个算子 home；`config` 参数给这个节点补充了一个名为 `directory` 的参数，指明要读取的输入目录。输入目录的位置属于具体的项目，而不属于「读取目录」这个可以在许多项目中复用的步骤，所以它没有写进 `props.json`，而是在作业里传入。第二次调用加入了一个名为 `prompt` 的节点，它使用 `prompt` 这个算子 home，`upstream="notes"` 表示这个节点读取 `notes` 节点的结果作为输入，也就是说 `notes` 是 `prompt` 的上游。

`execute(job, "demo", start_from_scratch=True)` 真正开始执行这个作业。第二个参数 `"demo"` 称为 epoch，可以把它理解为「这一批结果的名字」，它会成为输出目录中的一层子目录。如果以后用同一个 epoch 再次运行，docorder 会在这批已有结果的基础上继续工作；如果换一个新的 epoch，docorder 就会在一个空目录里从头开始，原来那批结果保持不动。`start_from_scratch=True` 要求 source 类型的节点重新读取外部输入；如果不传这个参数，source 节点会保留上一次读到的内容，不去重新读取输入目录。

在已经安装了 docorder 的环境中，进入 `hello-docorder/` 目录，执行 `uv run python run.py` 就能运行这个作业。脚本最后的 `if __name__ == "__main__":` 是普通脚本的写法。并行执行用的是线程，不再另起子进程。

#### 运行留下的文件

运行结束后，输出根目录 `runs/` 中会出现下面这些文件：

```text
runs/
  notes/
    .docorder-output                  标记文件，表示这个目录由 docorder 管理
    demo/                             epoch 目录
      hello/                          一个实体，名字来自输入目录 hello
        data                          hello
        tag.json                      来自输入实体的 tag.json
  prompt/
    .docorder-output
    demo/
      hello/
        data                          Note: hello
        tag.json                      与上游的 tag.json 相同，并含 upstream
                                      {"operator": "notes", "name": "hello",
                                       "epoch": "demo", "hash": "5891b5b5…"}
```

每个节点在输出根目录下都有一个与节点同名的目录，例如 `runs/notes/` 和 `runs/prompt/`；节点目录下是以 epoch 命名的目录，这里是 `demo/`；epoch 目录下，每个被处理的对象各占一个子目录，docorder 把这样一个目录称为一个实体（entity）。在这个例子里，输入目录中只有 `hello` 一个实体目录，所以每个节点都只产生了一个名为 `hello` 的实体。

实体目录里的 `data` 文件称为正文，保存的是这一步的主要结果：在 `notes` 节点里，它是输入实体目录里 `data` 的原始内容；在 `prompt` 节点里，它是模板渲染后的文本 `Note: hello`。`tag.json` 保存的是正文之外的附加信息，格式是一个 JSON 对象：`DirectorySource` 把输入目录里的 `tag.json` 读进来；`TemplateToPrompt` 不产生新的附加信息，而是把上游实体的 `tag.json` 原样复制过来，传给下一步使用。

`tag.json` 里的 `upstream` 只出现在 `prompt` 节点的实体里，docorder 称它为上游快照。它记录了这个实体是根据哪个上游实体计算出来的：上游节点是 `notes`，上游实体是 `hello`，读取时的 epoch 是 `demo`，以及当时那份上游实体的正文连同用户 tag 算出的 sha256 哈希值（sha256 是一种常用的哈希算法，结果是 64 个十六进制字符，上图只显示了开头几位）。docorder 判断这个结果是否仍然有效，依靠的就是这份记录。`notes` 节点是 source 类型，它没有上游，所以它的实体里没有这个键。

#### 再跑一次

如果什么都不修改，再执行一次 `run.py`，会发生下面的事情：`notes` 节点重新读取输入目录，`hello` 的正文和 tag 仍然没有变化；轮到 `prompt` 节点时，docorder 把 `tag.json` 里 `upstream` 记录的哈希值，与 `runs/notes/demo/hello` 当前正文和用户 tag 的哈希值进行比较，发现两者一致，于是认为已有的结果仍然有效，直接保留它，不再重新渲染模板。

如果把已经写出的 `runs/notes/demo/hello/data` 改成 `changed`，或者改同一目录里的 `tag.json`，再执行一次且不传 `start_from_scratch`，`notes` 节点不会重读输入目录，但 `prompt` 节点比较时发现哈希不一致，于是删除旧的 `hello` 实体并重新处理。如果改的是输入目录里的源文件，则必须传入 `start_from_scratch=True`，`notes` 才会读到新内容。如果再往输入目录中放入一个 `bye` 实体目录并从头读取，两个节点都会新建一个名为 `bye` 的实体，而没有变化的 `hello` 会继续保持原样。

需要特别注意相反的情况：如果只修改了模板，而上游实体没有变化，`prompt` 节点的结果并不会更新，因为 `tag.json` 里的 `upstream` 只记录上游实体的正文和用户 tag，并不记录模板的内容。这是当前版本的一个重要边界，下文「本版边界」一节还会再讲。运行中途失败时，道理也是一样的：已经成功写下 `upstream` 的实体，在下一次运行时会因为比较通过而被保留，只有那些还没有完成的实体会被重新处理。

这个例子中出现的名词，包括算子、算子 home、`props.json`、function、作业、节点、epoch、实体、正文、tag 和上游快照，在第二章中都有更完整的定义，后面各章都以它们为基础。

### 设计取舍

第一个取舍是把处理进度保存在每个实体自己的目录里，而不是保存在一个集中的状态数据库里。在上面的例子中，`prompt` 节点的 `hello` 实体是否需要重做，只取决于它 `tag.json` 里的 `upstream` 和上游实体当前的正文与用户 tag，docorder 不需要查询任何数据库，也不依赖上一次运行留在内存中的信息。这样做的好处是，即使换了一个进程、甚至换了一份作业脚本，只要输出根目录和 epoch 不变，就能在上一次的进度上继续运行；使用者也可以直接打开 `runs/` 目录，查看每一步、每个对象的中间结果，排查问题非常方便。相应的代价是，所有状态都必须用文件来表达：docorder 以 `tag.json` 里的 `upstream` 作为一个实体处理完成的标志，它随 `tag.json` 最后写入，如果正文已经写好而 tag 还没来得及写入，进程就退出了，这个实体在下一次运行时会被当作未完成而重新处理。

第二个取舍是把转换逻辑放在可以复用的算子 home 里，而不是直接写在作业脚本里。在上面的例子中，模板文件和 `props.json` 都放在 `homes/prompt/` 中，而 `run.py` 只负责说明使用哪个算子 home、上游是哪个节点、结果写到哪里。这样，同一个算子 home 可以被许多不同的作业引用，每个作业可以通过节点的 `config` 参数覆盖其中的部分参数，例子中的输入目录就是用这种方式传进去的。

第三个取舍是把调度和转换分开。像 `TemplateToPrompt` 这样的 function 只负责一件事：拿到一个上游实体，计算出目标实体的正文和 tag。至于读写实体目录、比较 `tag.json` 里的 `upstream`、清理过时的结果、并行执行和失败重试，都由 docorder 中负责调度的部分完成，这部分称为 runner。由于这种分工，编写一种新的转换时，通常只需要实现一两个方法，而不必关心进度记录、并发和重试这些繁琐的细节。

### 本版边界

在设计作业时，需要了解当前版本的以下几项限制。

每个节点只能有一个上游节点，因此整张作业图由一棵或几棵以 source 节点为根的树组成，不能让一个节点同时读取两个上游节点的结果。如果某一步确实需要合并两路结果，只能在 function 的代码里自己去读取另一路结果的文件，而这部分读取不会被记进快照，另一路结果发生变化时，docorder 不会因此自动重做这个实体。

docorder 按节点逐个执行，一个节点的一次完整执行称为一个 stage。一个节点必须处理完本 epoch 中的全部实体，它的下游节点才会开始执行；docorder 不支持「上游刚处理完一个实体，下游就立即开始处理这个实体」这种流水线式的执行方式。

并行执行只发生在一台机器上，依靠的是 Python 标准库提供的线程池，也就是在当前进程里启动若干个线程分担工作；docorder 不支持把任务分发到多台机器上执行。

上游快照覆盖上游的正文和用户 tag，但不覆盖模板、参数或代码。如果修改了模板、`props.json` 中的参数、function 的代码或者它调用的外部工具，而上游实体没有变化，docorder 不会察觉到这些修改，旧的结果会被保留下来。要让这类修改生效，需要手动删除相应的输出目录，或者换一个新的 epoch 运行。

换一个新的 epoch，意味着所有节点都从空目录开始重新计算。旧 epoch 下的结果既不会被新 epoch 复用，也不会被自动清理，不再需要时要由使用者手动删除。

## 二、核心概念与术语

本章给出 docorder 中每个概念的准确定义。第一章的例子已经让这些概念各自露过面，这里会进一步说明它们由谁创建、保存在哪里、能存在多久，以及彼此之间是什么关系。

### 实体

实体是 docorder 处理的基本单位，它表示「某一个对象在某一个步骤中的结果」。同一个对象经过三个步骤，就会在三个节点下各有一个实体。在磁盘上，一个实体就是一个目录，它位于某个节点的输出目录下、某个 epoch 子目录之中，目录的名字就是实体的名字。

```text
<输出根目录>/<节点名>/<epoch>/<实体名>/
  data            正文，UTF-8 编码的文本
  tag.json        附加信息，一个 JSON 对象；有上游时含 upstream 快照
```

`data` 文件保存实体的正文。正文的含义取决于产生它的步骤：在读取目录的步骤里，它是原始文件的内容；在渲染模板的步骤里，它是渲染出来的文本；在运行外部命令的步骤里，它是命令的输出。docorder 在调度时只要求正文是一段文本，并不关心其中的格式，所以正文可以是普通文字、Markdown、JSON 或者任何其它文本格式，但不能是图片这样的二进制数据。

`tag.json` 保存实体的附加信息，它必须是一个 JSON 对象，也就是由若干「键: 值」组成的结构。附加信息里有哪些键，主要由产生这个实体的 function 决定，它的主要用途是给下游步骤提供额外的数据，例如在模板中引用原始文件名，或者根据某个字段做筛选。docorder 自己还管理两个键。`upstream` 是直接上游实体此刻的快照；下游实体会带上上游的整份附加信息，所以写出前一定要重置这个键，并丢掉可能残留的 `current`。`global_prop` 则把一些数据沿着作业图一路传到末端。第三章「填写与写出」一节会详细说明。

实体的名字必须能够安全地作为一层目录名使用，因此有以下要求：名字不能为空；名字的开头和结尾不能有空白字符；名字中不能含有斜杠 `/` 或反斜杠 `\`；名字不能是 `.` 或 `..`；名字也不能以 `.` 或 `_` 开头，因为以这两个字符开头的名字被留给了 docorder 的标记文件和运行时的临时文件。此外，只有包含 `data` 文件或 `tag.json` 文件的目录才会被认作实体，空目录和更深层的目录都不算。

### 上游快照

上游快照写在 `tag.json` 的 `upstream` 里，它记录了「这个实体是根据哪些上游实体的哪个版本计算出来的」。一个上游时是一条记录，没有或多个上游时是列表。每条记录有四个字段：`operator` 是上游节点的名字，`name` 是上游实体的名字，`epoch` 是读取时所在的 epoch，`hash` 是那份上游实体的正文连同用户 tag（不含 `upstream`）算出的 sha256 哈希值。大多数步骤的每个输出只依赖一个上游实体，所以快照里只有一条记录；只有把一批实体合并成一个的 reduce 类步骤，快照里才会有多条记录，每个参与合并的上游实体各占一条。

上游快照是 docorder 判断一个结果是否仍然有效的唯一依据。对于有上游的实体，只有当 `tag.json` 里的 `upstream` 已经写下，并且其中的记录与上游的当前状态完全吻合时，这个实体才被视为已经完成；即使正文已经写好，只要 tag 里还没有这份快照，这个实体仍然被视为未完成。有一种特殊情况需要留意：如果上游的正文是一个空字符串，记录中的哈希值也会是空的，而空的哈希值在比较时永远不会被认为一致，因此依赖空正文的实体在每次运行时都会被重新处理。

### 算子与算子 home

算子是一种可以重复使用的步骤，例如「读取一个目录中的文件」或者「用某个模板渲染文本」。描述一个算子所需要的文件都放在同一个目录中，这个目录称为算子 home。算子 home 里至少要有一份 `props.json`，其中写明算子的类型 `type`、负责转换的 Python 类 `class`、控制执行方式的调度参数，以及交给转换类使用的默认参数。除此之外，算子 home 里还可以放置这个算子需要的其它文件，按习惯，模板文件放在 `lib/` 子目录中，外部工具的定义放在 `tools/` 子目录中，使用者自己编写的转换代码放在 `primary.py` 文件中。

算子 home 只描述「这一步怎么做」，不记录结果写到哪里，也不属于某一次具体的运行，所以同一个算子 home 可以被很多作业重复使用。docorder 的安装包里不包含任何算子 home，使用者需要把算子 home 放在环境变量 `DOCORDER_HOMES` 所列出的目录中，docorder 会在这些目录里按名字查找它们，具体规则见第五章。

算子分为五种类型。source 类型没有上游，它从外部数据产生最初的一批实体；map 类型为上游的每一个实体产生一个同名的输出实体；reduce 类型把上游的全部实体合并成一个输出实体；fanout 类型把上游的每一个实体拆分成若干个输出实体；output 类型不写实体，把上游本 epoch 的正文写成作业结果目录里的文件。第六章会逐一介绍这五种类型。

### function

function 是算子 home 的 `props.json` 中 `class` 所指向的那个 Python 类，它承担真正的转换工作。在处理每个实体时，runner 会创建一个新的 function 对象，把上游实体和一个还没有填写内容的目标实体交给它；function 负责为目标实体填好正文和附加信息，然后由 runner 把它们写入磁盘。每种算子类型都有一个对应的 function 基类，使用者编写自己的转换时需要继承相应的基类。docorder 还自带了几个可以直接通过配置使用的 function，例如读取目录的 `DirectorySource` 和渲染 Jinja 模板的 `TemplateToPrompt`，第六章会完整列出它们。

### 作业与节点

作业描述的是「这一次要执行哪些步骤、它们之间的先后关系如何、结果写到哪里」，它是一张有向无环图。有向无环图的意思是：图中的每条连线都有方向，从上游指向下游，并且沿着连线的方向走，永远不会回到出发的地方，也就是说步骤之间不存在循环依赖。作业通过 `Job(name, root)` 创建，其中 `root` 是输出根目录。

作业中的每一个点称为节点，节点通过 `add_operator_node` 方法加入作业。每个节点引用一个算子 home，并且除 source 节点以外，必须指定唯一的一个上游节点。节点还可以通过 `config` 参数覆盖算子 home 中的转换参数，通过 `parallelism` 和 `retry` 参数覆盖调度参数。节点的输出目录总是「输出根目录/节点名」，不能另外指定。同一个算子 home 可以在同一个作业里被多个节点引用，例如用同一个模板算子分别处理两个不同的上游。

作业对象只存在于一次 Python 进程的内存中，它本身不保存任何处理进度，进度全部保存在各个实体的目录里。

### epoch 与 stage

epoch 是调用 `execute` 时传入的一个名字，通常使用日期或版本号，例如 `2026-10-16` 或 `v3`。它决定了每个节点输出目录下的那一层子目录，在同一次运行中，所有节点都使用同一个 epoch。换一个新的 epoch，相当于换了一套全新的空目录，所有结果从头计算；使用同一个 epoch 再次运行，则是在上一次的结果和进度上继续工作。

stage 指的是一个节点在一次运行中的执行过程。一次运行会按照作业图中的依赖顺序，依次执行每个节点的 stage；一个 stage 必须处理完本 epoch 中的全部实体，下一个 stage 才会开始。

### runner 与应得名单

runner 是 docorder 中负责调度的部分，调用 `docorder.core.runner.execute` 就是让 runner 开始工作。每个非 source 节点的 stage 开始时，runner 会先读取上游节点在本 epoch 中已有的全部实体，并据此列出应得名单。应得名单回答的问题是：「按照上游当前的状态，这个节点应该有哪些输出实体，每个输出实体又依赖哪些上游实体？」随后，runner 把应得名单与这个节点目录中已经存在的实体逐一比较，决定每个实体应该新建、重做、保留还是删除。第三章会详细讲解这个过程。

### 概念之间的关系

下面这张图用第一章的最小例子，展示上述概念是如何组合在一起的。

```text
DOCORDER_HOMES = homes/
  homes/notes_source/   算子 home：props.json（type=source, class=DirectorySource）
  homes/prompt/         算子 home：props.json（type=map, class=TemplateToPrompt）, lib/note.jinja
                          │ 被节点引用
                          ▼
作业 Job("hello", runs/)
  ├─ 节点 notes   ── 算子 home: notes_source ── config: directory ── 输出: runs/notes/
  └─ 节点 prompt  ── 算子 home: prompt       ── 上游: notes        ── 输出: runs/prompt/

execute(job, "demo")      epoch 为 demo，每个节点各执行一个 stage
  runs/notes/demo/hello/        实体：data, tag.json
  runs/prompt/demo/hello/       实体：data, tag.json（含 upstream）
                                  └─ 上游快照：记录 runs/notes/demo/hello 正文的哈希值
```

### 术语对照

| 术语 | 英文或代码中的名字 | 含义 |
| --- | --- | --- |
| 实体 | entity | 一个对象在某个节点、某个 epoch 下的结果，在磁盘上是一个目录 |
| 正文 | `data` | 实体的主要内容，一段文本 |
| tag | `tag.json` | 实体的附加信息，一个 JSON 对象 |
| 上游快照 | `tag.json` 的 `upstream` | 实体读取过的上游实体，以及当时上游正文与用户 tag 的哈希值 |
| 算子 | operator | 一种可以重复使用的步骤，属于四种类型之一 |
| 算子 home | operator home | 存放一个算子全部文件的目录，必须包含 `props.json` |
| function | function | `props.json` 中 `class` 指向的、执行转换的 Python 类 |
| 作业 | `Job` | 一次运行要执行的步骤及其先后关系 |
| 节点 | node | 作业中引用某个算子的一个步骤 |
| epoch | epoch | 一批结果的名字，也是输出目录中的一层子目录 |
| stage | stage | 一个节点在一次运行中的完整执行 |
| runner | runner | docorder 中负责调度的部分 |
| 应得名单 | expected names | 一个节点按上游当前状态应有的输出实体，以及每个输出依赖的上游实体 |

## 三、工作流程

本章按时间顺序讲解调用 `execute(job, epoch, start_from_scratch=False)` 之后发生的事情。整个过程分为两个阶段：第一阶段是装配，检查整个作业是否正确，并准备好每个节点要用的转换类；第二阶段是按依赖顺序逐个执行每个节点的 stage。在第二阶段中，只要任何一个 stage 抛出了异常，整次运行就会在这里停止，排在后面的节点不会开始执行。

### 装配

装配阶段首先检查作业图本身是否合理。以下几种情况会被拒绝：节点之间存在循环依赖；某个节点指定的上游节点在作业中并不存在；某个节点把自己指定为上游；两个节点的输出目录实际上是同一个目录；以及一个节点的输出目录位于另一个节点的输出目录之中。

作业图检查通过之后，runner 为每个节点加载 `props.json` 中 `class` 指向的 Python 类，并尝试创建一个对象。如果这个类找不到，或者它不是该算子类型对应基类的子类，或者它还有必须实现却没有实现的方法，运行就会以 `OperatorValidationError` 错误停止。由于这些检查都发生在任何节点开始执行之前，即使只是最后一个节点的类名写错了，也会在一开始就被发现，前面的节点不会白白执行一遍。

各节点的执行顺序由作业图决定：一个节点总是排在它的上游节点之后，这种顺序称为拓扑顺序。当有几个节点同时满足执行条件时，先加入作业的节点先执行。

### 一个 stage 的经过

source 节点的 stage 与其它节点有很大不同，本章最后单独说明。本节描述 map、reduce 和 fanout 节点的 stage，它依次经过以下几个步骤。

#### 检查输出目录

每个 stage 开始时，runner 首先检查这个节点的输出目录。docorder 在运行过程中会删除过时的实体目录，为了防止误删不属于它的文件，它会在每个由自己管理的输出目录中放置一个名为 `.docorder-output` 的标记文件。如果输出目录已经存在、里面已经有内容，却没有这个标记文件，说明这个目录很可能不是 docorder 创建的，此时运行会以 `FatalError` 错误停止。如果检查通过，runner 会在需要时创建输出目录，并写入标记文件。

#### 列出应得名单

接下来，runner 读取上游节点在本 epoch 中已有的全部实体，列出本节点的应得名单。不同类型的算子，应得名单的列法不同。对于 map 节点，上游的每个实体都对应一个同名的输出实体，这个输出实体只依赖那一个上游实体。对于 fanout 节点，runner 会调用 function 的 `output_names` 方法，询问每个上游实体要拆分出哪些输出实体，每个输出实体依赖产生它的那个上游实体。对于 reduce 节点，应得名单永远只有一项：一个名字由参数 `output` 决定的输出实体（未设置时名为 `result`），它依赖上游的全部实体。

如果应得名单是空的，这个 stage 就什么也不做，本节点已有的实体全部保持原样。map 和 fanout 节点在上游一个实体都没有的时候就会出现这种情况。reduce 节点的应得名单不会为空，即使上游一个实体都没有，它仍然会产生那一个输出实体，只是交给 function 的上游实体列表是空的。

#### 与磁盘上的实体比较

应得名单不为空时，runner 读取本节点目录中已有的实体，把它们与应得名单逐一比较，分成以下几类。应得名单中有、但目录里还没有的实体，需要新建。目录里有、但应得名单中已经没有的实体，例如上游已经删除了对应的对象，需要删除。两边都有的实体，则要用它 `tag.json` 里的 `upstream` 与上游的当前状态作比较，只要下面任意一条成立，就需要重做：`upstream` 不存在或者内容无效；快照中记录的上游实体名字与应得名单中列出的不一致；记录中的节点名不是当前的上游节点；记录中的 epoch 不是本次运行的 epoch；记录中的哈希值为空，或者与上游实体当前正文和用户 tag 的哈希值不同；这个实体自己的 `tag.json` 无法读取或者不是 JSON 对象。所有条件都不成立的实体比较通过，会被原样保留，本次运行不会为它调用 function。

#### 清理与预留

比较完成之后、开始调用任何 function 之前，runner 会对整个 stage 的目录做一次集中整理：先删除所有需要删除的实体目录和所有需要重做的实体目录，然后为每个需要新建或重做的实体建立一个只包含空 `tag.json` 的目录作为占位。这意味着，一旦 stage 开始执行，所有需要重做的实体都已经失去了它们的旧正文；如果这个 stage 在中途失败，那些还没有轮到处理的实体会停留在只有空 `tag.json` 的状态，它们的 `tag.json` 里没有 `upstream`，因此在下一次运行时会被识别为未完成并重新处理。

#### 填写与写出

对于每个等待处理的实体，runner 先调用 function 的 `transform_data` 方法填写正文，再调用 `transform_props` 方法填写附加信息。function 填写的正文必须是字符串，附加信息必须是字典（也就是 JSON 对象），否则这个实体会以 `FatalError` 错误失败。

function 填写完成后，runner 会处理附加信息中的 `global_prop` 和 `upstream`。如果上游实体的附加信息里有一个名为 `global_prop` 的对象，runner 会把它合并到目标实体附加信息的 `global_prop` 中；如果目标实体自己已经写了同名的键，以目标实体自己写的值为准。对于 reduce 节点，参与合并的上游实体有很多个，runner 按实体名字的顺序依次合并，排在后面的实体中的值会覆盖排在前面的。这个机制的意义在于，放进 `global_prop` 的数据可以从作业的起点一直传到末端，即使中间某个 function 没有把上游的附加信息复制下来，这些数据也不会丢失。

`upstream` 一定被重置，残留的 `current` 会被丢掉。上游实体会交给下游 function，function 常常把上游的整份附加信息复制过来，其中已经有上游自己的 `upstream`。runner 不保留这项：目标的 `upstream` 改成直接上游实体此刻的快照（只有一个上游时是这条记录，没有或多个上游时是这些记录组成的列表）。这条记录有四个字段：`operator` 是上游节点名，`name` 是上游实体名，`epoch` 是本次 epoch，`hash` 是上游实体正文连同用户 tag 的 sha256。source 节点没有上游，不写 `upstream`。

最后，runner 按固定顺序写入实体目录：先写 `data`，再写 `tag.json`。每个文件都先写到同一目录下的一个 `.tmp` 临时文件中，写完之后再替换成正式的文件名，所以不会出现一个文件只写了一半的情况。`tag.json` 最后写入，正是为了保证只有在正文和快照都写好之后，这个实体才会被视为完成。目录里若留着旧的 `upstream.json`，写出后会删掉。

每个 stage 在标准错误输出上打印一条进度条，标题是节点名。map、fanout、reduce 的总数是本段应得的实体个数，已经比较通过、本轮跳过的也会计入。output 的总数是这次写出的文件个数。source 在 `emit` 时逐条推进，开始时不知道总数。并行的 map 和 fanout 共用这一条进度条。

### 并行与重试

map 和 fanout 节点可以利用多个线程同时处理实体，以缩短总的运行时间。具体做法是：runner 把等待处理的实体列表切成连续的若干段，段数不超过节点的 `parallelism` 参数，也不超过等待处理的实体个数。如果只切出一段，就在当前线程中按顺序逐个处理；如果切出了多段，就为每一段启动一个工作线程，每个线程在自己那一段内按顺序处理。这些线程共享当前进程里的算子和参数。reduce 节点只有一个输出实体，source 节点的处理方式也不同，所以这两类节点不会被切分。

工作线程通过 Python 标准库中的 `ThreadPoolExecutor` 启动，不另起进程，因此启动作业的代码不必为了并行而写在 `if __name__ == "__main__":` 之下，`config` 也不必能被 pickle。

在并行执行时，如果某一段中有一个实体最终失败，这一段中排在它后面的实体就不会再被处理，但其它段会继续执行到结束，所有段都结束之后，异常才会被抛出。因此，并行运行失败之后，磁盘上已经完成的实体可能比你预想的要多一些。

每个实体的处理都按照节点的 `retry` 参数进行重试。如果 function 抛出的是 `FatalError`，说明出现了重试也无法解决的问题，例如配置缺失或者模板写错，此时不会重试，这个 stage 立即失败；如果抛出的是其它类型的异常，例如外部命令返回了错误，runner 会等待一段时间后再试一次，等待的秒数是 `backoff_seconds` 乘以已经尝试过的次数，直到尝试的总次数达到 `max_attempts` 为止。一个实体只要成功写下了 `tag.json` 里的 `upstream`，就会一直保留在目录中；用同一个作业和同一个 epoch 再次运行时，这些实体会因为比较通过而被跳过，runner 只会处理剩下的实体。

### source 节点的 stage

source 节点没有上游，所以它不列应得名单，也不做上面那样的比较。它是否重新产生实体，只取决于本次调用 `execute` 时是否传入了 `start_from_scratch=True`。

如果没有传入，source 节点不会调用 function，也不会改动已有的实体，只确保输出目录和标记文件存在，下游节点读取的是它上一次留下的实体。需要注意的是，如果在一个全新的 epoch 上第一次运行时就没有传入这个参数，source 节点的目录是空的，下游看到的也就是一个空的上游：map 和 fanout 节点什么都不会做，reduce 节点会产生一个基于空输入的结果。

如果传入了，runner 会调用 function 的 `emit` 方法，逐条读取它交出的记录，每读到一条就写成一个实体。每条记录的实体名必须符合命名规则，同一个名字不能出现两次，正文必须是字符串，附加信息必须是字典。写入时，runner 直接覆盖实体目录中原有的 `data` 和 `tag.json`，并删除可能残留的 `upstream.json`。source 不写 `upstream`。全部记录都写完之后，本 epoch 中这一次没有被交出的实体会被删除，这样 source 节点目录中的实体就与外部数据完全一致了。source 节点的 `retry` 参数只作用于「把一条记录写入磁盘」这一个动作；如果 `emit` 方法本身抛出了异常，例如某个输入文件不是合法的 UTF-8 文本，这个异常不会被重试，此时那些还没来得及交出的旧实体也不会被删除，等到下一次带 `start_from_scratch=True` 的运行成功完成时，目录内容才会恢复一致。

### 再次运行时的判定

下表把上面介绍的各种情况集中在一起，说明在同一个 epoch 上再次运行时，每个实体会被如何处理。

| 情况 | 处理方式 |
| --- | --- |
| 应得名单中有，目录中没有 | 新建，并调用 function 处理 |
| 目录中有，应得名单中没有 | 删除整个实体目录 |
| 两边都有，上游快照与上游当前状态吻合 | 保留，不调用 function |
| 两边都有，没有上游快照、上游快照无效或 `tag.json` 无效 | 清空后重新处理 |
| 两边都有，上游实体名字、节点名、epoch 或实体哈希值不一致 | 清空后重新处理 |
| map 或 fanout 节点的上游一个实体都没有 | 不做比较，目录保持原样 |
| reduce 节点的上游一个实体都没有 | 照常比较，function 收到一个空列表 |
| source 节点，未传入 `start_from_scratch=True` | 不调用 function，实体保持原样 |

从这张表可以推出几条日常使用中最常用的规则。第一，修改了外部输入文件之后，必须传入 `start_from_scratch=True`，source 节点才会读到新内容，变化才会从作业的起点向下游传递；已经写出的实体目录里的 `data` 或 `tag.json` 被手动改过，即使不传这个参数，依赖它们的下游也会重做。在传递过程中，只有正文或用户 tag 真正发生变化的实体才会引起下游重做，如果某个实体重做之后得到的正文和用户 tag 与原来完全相同，变化就不会再继续向下传递。第二，修改了模板、参数或代码之后，docorder 不会自动察觉，需要删除受影响节点的 epoch 目录或其中的部分实体目录，或者换一个新的 epoch 运行。第三，上一次运行中途失败时，修复问题后用同一个作业和同一个 epoch 再运行一次即可，已经完成的部分不会重复执行。

### 一次运行留下的目录

```text
<输出根目录>/
  <节点名>/
    .docorder-output          标记文件，表示这个目录由 docorder 管理
    <epoch>/
      <实体名>/
        data
        tag.json              有上游时含 upstream 快照
    <另一个 epoch>/
      ...
```

## 四、使用场景

docorder 最适合这样一类任务：有一批彼此独立的对象，每个对象都要经过几个步骤的加工，而其中某些步骤比较慢、比较贵，或者容易失败。在这类任务中，docorder 能够保证失败之后只补做失败的部分，输入变化之后只重做受影响的部分。下面介绍几种典型的作业图，它们都只需要使用 docorder 自带的 function，或者编写很少量的代码就能搭建出来。

### 批量生成提示词并交给大模型

这是 docorder 最典型的用法。作业的第一步是一个 source 节点，它读取一个目录，把其中的每个文件变成一个实体；第二步是一个使用 `TemplateToPrompt` 的 map 节点，它把每个实体套进模板，生成一段提示词；第三步是一个使用 `PromptToLLM` 的 map 节点，它把每段提示词交给一个命令行形式的大模型工具，工具在标准输出中打印的内容，或它自己写进目标实体的 `data`，就成为这一步的正文；最后还可以接一个自己编写的 reduce 节点，把所有回答汇总成一份清单。调用大模型的那个节点通常需要配置 `retry`，以便在接口偶尔出错时自动重试，并用 `parallelism` 控制同时发出的请求数量。如果有几个对象在多次重试后仍然失败，修复问题后用同一个 epoch 再运行一次，docorder 只会补做这几个对象，其余已经拿到回答的对象不会再次调用大模型。第九章的示例项目就是按这个结构搭建的。

### 从结构化数据生成配置文件

如果上游实体的正文是一个 JSON 对象，例如一张表的字段定义或者一个服务的描述，可以先用一个使用 `JinjaToJsonnet` 的 map 节点，把 JSON 对象中的每个键当作模板变量，渲染出一段 jsonnet 程序；再用一个使用 `JsonnetToPrompt` 的 map 节点，调用本机安装的 `jsonnet` 程序编译它，得到最终的 JSON 或文本。jsonnet 是一种专门用来生成 JSON 配置的语言，它支持变量、函数和列表推导等功能，比直接手写 JSON 更灵活。这种组合适合根据一批表定义或服务描述，批量生成格式统一的配置文件。

### 为每个文件运行命令行工具

使用 `Command` 的 map 节点会为每个实体运行一次外部命令。命令的参数里可以引用实体的附加信息、正文和输出目录，命令的结果可以取它在标准输出中打印的内容，也可以取它写到磁盘上的某个文件。这个 function 直接启动命令，不经过 shell，因此参数中的空格和特殊字符不会被 shell 另行解释。它适合批量调用代码格式化工具、格式转换工具或者团队内部的脚本。

### 汇总与拆分

reduce 节点把一批实体合并成一个实体，适合生成索引、目录、统计报告这类需要综合全部对象的结果。fanout 节点把一个实体拆成多个实体，适合把一篇长文档按段落或章节切开，再交给后续步骤分别处理。docorder 没有自带 reduce 和 fanout 类型的 function，需要按照第八章的说明自己编写，通常只需要十几行代码。

### 不适合的场景

有些任务并不适合使用 docorder。如果某一步需要同时读取两个不同上游节点的结果，并且希望其中任何一个发生变化时都能自动重做，当前版本无法表达这样的依赖关系。如果需要把任务分发到多台机器上执行，或者希望上游刚处理完一个对象、下游就立即开始处理它，docorder 也无法满足。如果对象的内容是图片、音频这类二进制数据，同样不适合，因为正文只能是文本。另外，如果对象的数量很少，每个步骤都很快，而且失败后从头再跑一遍也没有什么代价，那么直接写一个普通的 Python 脚本会更简单。

## 五、配置

本章集中介绍使用 docorder 时需要配置的所有内容，包括 docorder 如何找到算子 home、`props.json` 中每个键的含义、创建作业和添加节点时的参数、运行函数 `execute` 的参数，以及 function 和模板分别能读到哪些配置。

### 让 docorder 找到算子 home

docorder 通过环境变量 `DOCORDER_HOMES` 寻找算子 home。这个环境变量的值是一个或多个目录，多个目录之间的分隔符与系统环境变量 `PATH` 相同，在 macOS 和 Linux 上是冒号 `:`，在 Windows 上是分号 `;`。查找时，docorder 按列出的顺序依次搜索这些目录，排在前面的目录优先，一旦找到就不再继续搜索。

算子 home 既可以直接放在列出的目录下面，也可以放在列出的目录下的某个分类子目录里，但不能嵌套得更深。分类子目录可以帮助你按用途整理很多个算子 home，名字以 `.` 或 `_` 开头的分类子目录会被跳过。一个目录只要包含 `props.json` 文件，就会被认作算子 home，算子 home 的名字就是这个目录的名字，添加节点时就用这个名字引用它。

```text
homes/                        DOCORDER_HOMES 指向这里
  sources/                    分类子目录，可以没有
    table_source/             名为 table_source 的算子 home
      props.json
  render/
    table_prompt/             名为 table_prompt 的算子 home
      props.json
      lib/table.jinja
```

docorder 是在调用 `add_operator_node` 添加节点的那一刻查找算子 home 的，因此环境变量必须在构建作业之前设置好。如果找不到指定名字的算子 home，会抛出 `FileNotFoundError` 错误，错误信息中会列出搜索过的所有目录，便于排查。最简单的做法是在启动脚本中用 `os.environ["DOCORDER_HOMES"] = ...` 设置这个环境变量，并行线程在同一个进程里，会读到同一份环境变量。

### props.json

`props.json` 是一个 JSON 对象。下表列出了 docorder 自己会解读的键，表中没有列出的其它键都会作为参数交给 function 使用。表中最后一列说明这个键的值能否在作业中被覆盖，以及用什么方式覆盖。

| 键 | 类型与默认值 | 含义 | 作业中能否覆盖 |
| --- | --- | --- | --- |
| `type` | 必须填写 | 算子类型，取 `source`、`map`、`reduce`、`fanout`、`output` 之一 | 不能 |
| `class` | 必须填写 | function 类，写成 `模块路径:类名`；写成 `primary:类名` 表示算子 home 中 `primary.py` 文件里的类 | 不能 |
| `parallelism` | 整数，默认为 1 | map 和 fanout 节点最多同时使用的线程数 | 用 `add_operator_node` 的 `parallelism` 参数 |
| `retry.max_attempts` | 整数，默认为 1 | 每个实体最多尝试的次数，不能小于 1；默认值 1 表示不重试 | 用 `add_operator_node` 的 `retry` 参数 |
| `retry.backoff_seconds` | 数字，默认为 0 | 每次重试前等待的基础秒数，实际等待 `backoff_seconds × 已尝试次数` 秒 | 同上 |
| `output` | 字符串，默认为 `result` | 只对 reduce 节点有效，指定唯一那个输出实体的名字 | 用节点的 `config` |
| 其它键 | 任意 JSON 值 | function 的参数，例如 `template`、`directory` | 用节点的 `config` |

`retry` 写成一个嵌套的对象，例如 `"retry": {"max_attempts": 3, "backoff_seconds": 5}`，表示每个实体最多尝试三次，第一次失败后等待 5 秒，第二次失败后等待 10 秒。如果 `props.json` 不是一个 JSON 对象、`class` 中没有冒号，或者 `type` 不是上述五种之一，`add_operator_node` 会以 `JobValidationError` 错误失败。

### 作业与节点

`Job(name, root)` 用于创建一个作业，`name` 是作业的名字，`root` 是输出根目录。输出根目录建议使用绝对路径，这样无论从哪个目录启动脚本，结果都会写到同一个地方。节点通过下面的方法加入作业：

```python
job.add_operator_node(
    name,                 # 节点名，同时也是输出根目录下的子目录名
    operator_home,        # 算子 home 的名字，在 DOCORDER_HOMES 列出的目录中查找
    upstream=None,        # 上游节点名；source 节点不填，其它节点必须填，且只能是一个字符串
    config=None,          # 一个字典，覆盖算子 home 中的 function 参数
    parallelism=None,     # 覆盖 props.json 中的 parallelism
    retry=None,           # 覆盖 props.json 中的 retry，写成 RetryPolicy(max_attempts=..., backoff_seconds=...)
)
```

`RetryPolicy` 需要从 `docorder.utils.retry` 导入。使用这个方法时有几点需要注意：`upstream` 只能是一个字符串，传入列表或元组会被拒绝，这对应着「每个节点只有一个上游」的限制；如果用同一个节点名添加了两次节点，后一次会替换前一次，而且不会报错，所以要确保节点名互不相同；节点名会直接拼接到输出路径中，不做任何检查，应该使用由字母、数字、连字符或下划线组成的简单名字。

节点在构造时会把传入的 `config` 覆盖到算子 home 的 function 参数上，并写进 `props`。遇到同名的键时以 `config` 中的值为准，`config` 中的 `class` 会被忽略，因此不能通过 `config` 更换 function。构造完成之后节点不再保留 `config`，之后读参数都从 `props` 来。作业开始运行时，runner 会为每个节点构造一个算子，并把节点上的公开字段抬到算子上。此后读名字、参数、输出路径和上游，都走算子，不再回头去读节点。还有一点容易混淆：如果把 `parallelism` 或 `retry` 写进 `config`，并不会改变节点的并行度或重试策略，它们只会成为一个普通的 function 参数；要在作业中修改这两项调度参数，只能使用 `add_operator_node` 的同名参数。

### execute

```python
from docorder.core.runner import execute

execute(job, epoch, start_from_scratch=False)
```

`epoch` 会被直接用作一层目录名，docorder 不检查它的内容，所以应该使用日期、版本号这样的简单名字；如果传入 `2026/10` 这样带斜杠的名字，会建出两层目录。`start_from_scratch=True` 要求 source 节点调用 function 重新产生实体；不传入时，source 节点保持上一次留下的实体不变。在一个新的 epoch 上第一次运行时，通常都需要传入这个参数，否则 source 节点的目录是空的，整个作业也就没有任何输入。

### function 读到的参数与模板读到的算子信息

同一份参数会以两种形式提供给使用者，一种供 function 的代码读取，另一种供模板读取。两者包含的参数完全相同，都遵循「节点的 `config` 覆盖 `props.json`」这一约定，区别只在于模板读到的那一份还多了几项由 runner 填入的运行信息。

function 的代码通过 `self.environment.operator_props` 读取参数。它的内容是 `props.json` 去掉 `type`、`class`、`parallelism`、`retry` 这几个键之后剩下的部分，再用节点的 `config` 覆盖同名的键。function 根据这份参数决定具体怎么运行，例如 `TemplateToPrompt` 从这里读取 `template`，以确定使用哪个模板文件。模板读 `self.environment.template_env`，里面是 `operator`、`job`、`entity`。

模板通过名为 `operator` 的变量读取算子信息。它以 function 读到的那份参数为基础，也就是 `props.json` 中的参数被节点 `config` 覆盖之后的结果；在此之上，runner 还会填入本次运行的几项信息，包括 `name`、`home`、`class`、`type`、`parallelism`、`retry`、`output` 和 `epoch`，它们会覆盖同名的参数，具体含义见第七章的变量表。因此，在节点的 `config` 中覆盖了 `template` 之后，实际使用的模板文件和模板里 `{{ operator.template }}` 显示的值会一起改变；只写在节点 `config` 中、`props.json` 里没有的键，在模板里同样可以通过 `operator.<键>` 读到。runner 填入的那几项是唯一的例外：即使在 `config` 中写了 `name` 或 `epoch`，模板读到的仍然是节点名和本次运行的 epoch；写进 `config` 的 `parallelism` 和 `retry` 也不会改变 `operator.parallelism` 和 `operator.retry`，这两项反映的是经过 `add_operator_node` 参数覆盖之后实际生效的调度值。

### 环境变量

| 变量 | 由谁读取 | 含义 |
| --- | --- | --- |
| `DOCORDER_HOMES` | `add_operator_node` | 寻找算子 home 的目录列表 |
| `DOCORDER_LLM` | `PromptToLLM` | 节点没有配置 `tool` 参数时使用的大模型工具，值是工具名或工具定义文件的路径 |

## 六、算子分类与内置 function

### 五种算子

五种算子的区别在于输入实体与输出实体之间如何对应，以及作业结果写到哪里。下表从几个方面对它们作了比较。其中「function 基类」一列是编写这种算子的 function 时必须继承的类，「内置 function」一列是 docorder 自带、可以直接在 `props.json` 中使用的 function。

| 类型 | 输入与输出的对应关系 | 输出实体的名字从哪里来 | 能否并行 | function 基类 | 内置 function |
| --- | --- | --- | --- | --- | --- |
| source | 没有上游，从外部数据产生实体 | `emit` 方法交出的每条记录 | 否 | `SourceFunction` | `DirectorySource`、`FilteredDirectorySource` |
| map | 一个上游实体对应一个输出实体 | 与上游实体同名 | 是 | `MapFunction` | `TemplateToPrompt`、`JinjaToJsonnet`、`JsonnetToPrompt`、`Command`、`PromptToLLM` |
| reduce | 全部上游实体对应一个输出实体 | 参数 `output`，默认为 `result` | 否 | `ReduceFunction` | 无 |
| fanout | 一个上游实体对应多个输出实体 | `output_names` 方法的返回值 | 是 | `FanoutFunction` | 无 |
| output | 每个上游实体对应结果目录下的一个文件 | 实体名，或 `name_template` 用 tag 渲染 | 否 | `OutputFunction` | `Output` |

`props.json` 中 `class` 指向的类必须是 `type` 所对应基类的子类。例如 `type` 写的是 `map`，`class` 就只能是 `MapFunction` 或它的子类，写成一个 source 类型的 function 会在装配阶段报错。docorder 自带的五个 map function 都继承自 `RenderedMap`，它是 `MapFunction` 的一个子类，提供了「读取、渲染、生成附加信息」的三步结构，第七章会专门介绍。

### source 算子

source 算子位于作业图的起点，负责把外部数据变成最初的一批实体。正如第三章所说，source 节点只有在调用 `execute` 时传入了 `start_from_scratch=True`，才会运行 function 重新读取外部数据。

#### DirectorySource

`DirectorySource` 的完整写法是 `docorder.functions.impl.directory_source:DirectorySource`，它把一个目录中已经写成实体形状的子目录收成实体。它只处理该目录下直接包含的子目录，不会再往下走。子目录名就是实体名；子目录里必须有 `data` 和 `tag.json`，正文来自 `data`，附加信息来自 `tag.json`。普通文件、缺这两个文件之一的子目录，以及名字以 `.` 或 `_` 开头的子目录，都会被跳过。

| 参数 | 是否必须 | 含义 |
| --- | --- | --- |
| `directory` | 必须 | 要读取的输入目录；如果写的是相对路径，会相对于算子 home 解析 |

以下几种情况会导致失败。如果某个 `data` 不是合法的 UTF-8 文本，或 `tag.json` 不是 JSON 对象，这个 stage 会失败，而且不会重试。如果 `directory` 指定的目录不存在，会以 `FatalError` 错误失败。

输入数据通常属于具体的项目，而不属于算子，所以一般不会把输入目录放在算子 home 里，而是在添加节点时通过 `config` 传入一个绝对路径：

```python
job.add_operator_node("tables", "table_source", config={"directory": str(ROOT / "data" / "tables")})
```

如果需要改变 `DirectorySource` 的部分行为，可以编写它的子类，并覆盖以下三个方法中的一个或几个：`extract_tag(name, content, tag)` 决定每个实体目录的附加信息，参数 `name` 是目录名，`content` 是 `data` 的文本，`tag` 是读到的 `tag.json`；`include(path)` 决定一个实体目录是否要收成记录，返回 `True` 表示保留；`generate(directory)` 则完全替换「从目录产生记录」的过程。第九章的 `TableSource` 就是覆盖 `extract_tag` 的一个例子。

#### FilteredDirectorySource

`FilteredDirectorySource` 的完整写法是 `docorder.functions.impl.directory_source:FilteredDirectorySource`。它在 `DirectorySource` 的基础上增加了一个 `filter` 参数，用来按实体目录名的结尾和 `data` 文件大小挑选需要的实体，其余行为与 `DirectorySource` 完全相同。

| 参数 | 是否必须 | 含义 |
| --- | --- | --- |
| `directory` | 必须 | 与 `DirectorySource` 相同 |
| `filter.disabled_suffix` | 可选 | 一个字符串或字符串列表；实体目录名以其中任意一个结尾时，排除这个目录 |
| `filter.enabled_suffix` | 可选 | 一个字符串或字符串列表；设置之后，只保留目录名以其中任意一个结尾的实体 |
| `filter.min_size` | 可选 | 非负整数，`data` 文件大小的下限，单位是字节，等于下限的会被保留 |
| `filter.max_size` | 可选 | 非负整数，`data` 文件大小的上限，单位是字节，等于上限的会被保留 |

对每个实体目录，判断的顺序是：先检查它是否命中 `disabled_suffix`，命中就排除；再检查是否设置了 `enabled_suffix`，设置了而目录名没有命中也排除；最后检查 `data` 文件大小是否在范围之内。如果 `filter` 不是一个对象、某个后缀是空字符串、大小不是非负整数，或者 `min_size` 大于 `max_size`，会以 `FatalError` 错误失败。

下面的配置只读取算子 home 下 `inputs/` 目录中、`data` 不超过 64 KB 的实体：

```json
{
  "type": "source",
  "class": "docorder.functions.impl.directory_source:FilteredDirectorySource",
  "directory": "inputs",
  "filter": { "max_size": 65536 }
}
```

### map 算子

map 算子为上游的每一个实体产生一个同名的输出实体，是最常用的一种算子。docorder 自带的五个 map function 都属于渲染类，也就是都继承自 `RenderedMap`，它们在模板或命令参数中能够使用哪些变量，会在第七章统一说明。

#### TemplateToPrompt

`TemplateToPrompt` 的完整写法是 `docorder.functions.impl.template_to_prompt:TemplateToPrompt`。它用算子 home 中的一个 Jinja 模板渲染每个实体，渲染得到的文本就是输出实体的正文，输出实体的附加信息是上游实体附加信息的一份副本。

| 参数 | 是否必须 | 含义 |
| --- | --- | --- |
| `template` | 必须 | 模板文件相对于算子 home 的路径，这个路径不能指向算子 home 之外 |

这个 function 使用 Jinja 的严格模式渲染模板：如果模板中引用了一个不存在的变量，渲染会直接失败，而不会悄悄地把它替换成空字符串，这样可以尽早发现模板中的拼写错误。模板语法错误和变量缺失都会以 `FatalError` 错误失败，不会重试，因为再试多少次结果都一样。

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "template": "lib/note.jinja"
}
```

如果 `lib/note.jinja` 的内容是 `Note: {{ data }}`，而上游实体的正文是 `hello`，那么输出实体的正文就是 `Note: hello`。这里的 `data` 是 docorder 内置的模板变量，代表上游实体的正文。

#### JinjaToJsonnet

`JinjaToJsonnet` 的完整写法是 `docorder.functions.impl.jinja_to_jsonnet:JinjaToJsonnet`。它要求上游实体的正文是一个 JSON 对象，并把这个对象中的每个键作为 Jinja 模板的变量，渲染算子 home 中的模板，渲染结果是一段 jsonnet 程序，作为输出实体的正文。它产生的附加信息是一个空对象，不过 runner 仍会照常把上游的 `global_prop` 合并进去。

| 参数 | 是否必须 | 含义 |
| --- | --- | --- |
| `template` | 必须 | 模板文件相对于算子 home 的路径 |
| `variables` | 可选 | 一个 JSON 对象，为模板变量提供默认值；上游正文中的同名键会覆盖这里的值 |

在模板中，直接写 `{{ table }}` 会把变量的值作为普通文本插入；写成 `{{ columns | jsonnet }}`，则会通过 `jsonnet` 过滤器把变量的值转换成 jsonnet 能识别的字面量，例如字符串会带上引号，列表和对象会写成相应的语法。过滤器是 Jinja 的一种语法，用竖线 `|` 把一个值交给一个函数处理。如果上游正文为空、不是合法的 JSON、不是 JSON 对象，`variables` 不是对象，模板有错误，或者渲染结果全是空白，都会以 `FatalError` 错误失败。

下面是一个模板的例子：

```text
{
  table: {{ table | jsonnet }},
  owner: {{ owner | jsonnet }},
  columns: [c.name for c in {{ columns | jsonnet }}],
  column_count: std.length(self.columns),
}
```

假设上游实体的正文是 `{"table": "orders", "columns": [...]}`，其中 `columns` 列出了三个字段，`variables` 参数是 `{"owner": "data-team"}`。这个模板会渲染出一段 jsonnet 程序，再交给下一节介绍的 `JsonnetToPrompt` 编译，最终得到 `{"column_count": 3, "columns": ["order_id", "user_id", "amount"], "owner": "data-team", "table": "orders"}` 这样的 JSON。

如果需要定制它的行为，可以编写子类：覆盖 `template_text()` 方法可以由代码直接提供模板内容，而不必从文件读取；覆盖 `generate_props` 方法可以从渲染结果中提取信息，作为输出实体的附加信息。

#### JsonnetToPrompt

`JsonnetToPrompt` 的完整写法是 `docorder.functions.impl.jsonnet_to_prompt:JsonnetToPrompt`。它把上游实体的正文当作一段 jsonnet 程序，通过标准输入交给命令 `jsonnet -` 编译，编译器在标准输出中打印的结果就是输出实体的正文，输出实体的附加信息是上游附加信息的副本。这个 function 没有任何参数，但要求本机已经安装了 `jsonnet`，并且它所在的目录在环境变量 `PATH` 中。

如果找不到 `jsonnet` 命令，会以 `FatalError` 错误失败；如果编译过程返回了非零的退出码，会抛出普通的异常，并按节点的 `retry` 参数重试。如果 jsonnet 程序中用 `import` 引入了其它文件，路径会按照程序中写的样子解析；在 `JinjaToJsonnet` 的模板中，可以用 `{{ home }}` 得到算子 home 的绝对路径，从而拼出算子 home 中某个文件的完整路径。

#### Command

`Command` 的完整写法是 `docorder.functions.impl.command:Command`。它为每个实体运行一次外部命令，命令直接启动，不经过 shell。

| 参数 | 是否必须 | 含义 |
| --- | --- | --- |
| `argv` | 必须 | 一个列表，第一项是命令，后面各项是参数；每一项中的 `{名字}` 占位符会被替换成对应的值 |
| `cwd` | 可选 | 运行命令时的工作目录；其中的占位符不会被替换 |
| `output_file` | 可选 | 命令写出的结果文件；其中的占位符会被替换；相对路径相对于运行 Python 脚本时的当前目录 |
| `capture` | 可选 | 从哪里取得正文，可以是 `file`、`stdout` 或 `none`；设置了 `output_file` 时默认为 `file`，否则默认为 `stdout` |

`capture` 为 `file` 时，命令结束后读取 `output_file` 的内容作为正文；为 `stdout` 时，取命令在标准输出中打印的内容作为正文；为 `none` 时，正文是一个空字符串，适用于只关心命令副作用的场合。输出实体的附加信息是上游附加信息的副本，再加上一个 `command` 键，记录替换完占位符之后的完整命令行；如果设置了 `output_file`，还会加上一个 `output_file` 键，记录替换后的文件路径。

```json
{
  "type": "map",
  "class": "docorder.functions.impl.command:Command",
  "argv": ["cp", "/data/tables/{filename}", "{entity.output}/copy.json"],
  "output_file": "{entity.output}/copy.json"
}
```

这个例子中，`{filename}` 会被替换成上游附加信息中的文件名，`{entity.output}` 会被替换成正在写出的实体目录。命令把源文件复制到这个实体目录中，然后 `Command` 读取复制出来的文件作为正文。由于命令不经过 shell，参数中不能直接使用管道 `|` 或重定向 `>`；如果确实需要，可以显式写成 `["sh", "-c", "..."]`，但这时要注意，替换进命令行的值会被 shell 解释，如果这些值来自不可信的输入，可能带来命令注入的风险。

以下情况会以 `FatalError` 错误失败，不会重试：命令找不到；`argv` 为空；`capture` 的值无法识别；`capture` 为 `file` 却没有设置 `output_file`；占位符引用了一个不存在的名字。以下情况会抛出普通的异常，并按 `retry` 参数重试：命令返回了非零的退出码；`capture` 为 `file` 时命令没有写出 `output_file`。

#### PromptToLLM

`PromptToLLM` 的完整写法是 `docorder.functions.impl.prompt_to_llm:PromptToLLM`。它把上游实体的正文作为提示词，交给一个以命令行形式运行的大模型工具。工具返回后，如果目标实体目录里已经有 `data` 文件，这份文件就是正文：它必须是非空的 UTF-8 文本，通过检查后不再改写，只补上 `tag.json`。没有这份文件时，工具在标准输出中打印的内容就是正文。输出实体的附加信息是上游附加信息的副本。调用开始前若已有 `data`，会先删掉。docorder 不附带任何大模型工具的预设配置，工具需要由使用者自己定义。

| 参数 | 是否必须 | 含义 |
| --- | --- | --- |
| `workspace` | 必须 | 一个已经存在的目录，作为大模型工具进程的工作目录 |
| `tool` | 可选 | 要使用的工具，可以是工具名、工具定义文件的路径，或者直接写一个工具定义对象；不填时读取环境变量 `DOCORDER_LLM` |

当 `tool` 是一个字符串时，docorder 首先在算子 home 中寻找 `tools/<名字>.json` 文件，找不到时再把这个字符串当作一个文件路径。工具定义是一个 JSON 对象，包含以下字段：

| 字段 | 是否必须 | 含义 |
| --- | --- | --- |
| `run` | 必须 | 一个非空的字符串列表，表示要运行的命令及其参数；其中的 `{workspace}` 会被替换成工作目录 |
| `prompt` | 可选 | 提示词的传递方式：`stdin`（默认）表示通过标准输入传入，`arg` 表示追加为命令的最后一个参数 |
| `name` | 可选 | 工具的名字，出现在错误信息中，便于辨认 |

```json
{ "name": "my-llm", "run": ["my-llm-cli", "--cwd", "{workspace}"], "prompt": "stdin" }
```

上面的 `my-llm-cli` 只是一个占位的名字，实际使用时要换成你所用的大模型命令行工具。以下情况会以 `FatalError` 错误失败：没有设置 `workspace` 或者它指向的目录不存在；找不到指定的工具；工具定义的格式不正确；工具的可执行文件不在 `PATH` 中。如果工具运行后返回了非零的退出码，会抛出普通的异常，并按 `retry` 参数重试。由于大模型接口偶尔会因为限流或网络问题出错，使用 `PromptToLLM` 的算子通常都应该在 `props.json` 中配置 `retry`。

### reduce 算子

reduce 算子把上游在本 epoch 中的全部实体合并成一个输出实体，输出实体的名字由参数 `output` 决定，未设置时为 `result`。function 会收到一个按实体名字排序的上游实体列表，以及这一个目标实体。由于这个输出依赖全部上游实体，上游中任何一个实体的正文发生变化、新增了实体或者删除了实体，都会导致这个输出被重新计算。docorder 没有自带 reduce 类型的 function，第八章给出了编写方法和示例。

### fanout 算子

fanout 算子把上游的每一个实体拆分成多个输出实体。拆分出哪些输出实体，由 function 的 `output_names(source)` 方法决定：它接收一个上游实体，返回一个由输出实体名字组成的列表，默认只返回上游实体自己的名字。整个 stage 中，所有上游实体拆分出的名字必须互不相同，否则会以 `OperatorValidationError` 错误失败。`output_names` 方法在主进程中调用，而且在一次运行中可能被调用不止一次，因此它的结果应该只取决于传入的上游实体，也不应该产生写文件之类的副作用。docorder 没有自带 fanout 类型的 function，第八章给出了编写示例。

### output 算子

output 算子把上游本 epoch 的每个实体写成作业结果目录里的一个文件，作为作业整体的输出。缺省目录是作业根目录下的 `.job_result`；参数 `directory` 可以换成别的路径，相对路径相对算子 home 解析。它不产生给下游读取的实体。文件的内容是上游实体的正文。文件名缺省是实体名；如果配置了 `name_template`，就用该实体的 tag 渲染这段 Jinja 模板，渲染结果作为文件名。渲染结果必须是一层文件名。两个实体得到同一个文件名时，这一段以 `FatalError` 失败。这个节点上次写出、这次不再产生的文件会被删掉。内置 function 是 `docorder.functions.impl.output:Output`。

### 失败与重试

下表汇总了各种失败情况会抛出的异常，以及这些异常是否会按节点的 `retry` 参数重试。

| 情况 | 异常 | 是否按 `retry` 重试 |
| --- | --- | --- |
| 作业图中有循环依赖、上游节点不存在、输出目录冲突 | `JobValidationError` | 不适用，在开始执行前就失败 |
| function 类找不到，或者不是对应基类的子类 | `OperatorValidationError` | 不适用，在开始执行前就失败 |
| 找不到算子 home | `FileNotFoundError` | 不适用，在构建作业时就失败 |
| 输出目录中已有内容，却没有 `.docorder-output` 标记 | `FatalError` | 否 |
| 配置缺失、模板错误、模板变量缺失、输入格式不正确 | `FatalError` | 否 |
| 外部命令、jsonnet 或大模型工具返回非零退出码 | `DocorderError` | 是 |
| function 抛出的其它异常 | 原来的异常 | 是 |

这些异常类都定义在 `docorder.utils.errors` 中，其中 `DocorderError` 是 `JobValidationError`、`OperatorValidationError` 和 `FatalError` 的共同父类。

## 七、渲染类 function 与模板变量

本章说明 docorder 自带的 map function 在渲染模板或替换命令参数时，可以使用哪些数据，以及当这些内置数据不够用时，如何加入新的模板变量。

### RenderedMap 的三个步骤

`RenderedMap` 的完整写法是 `docorder.functions.rendered_map:RenderedMap`，它是 `MapFunction` 的子类，把处理一个实体的过程拆成三个先后进行的步骤。第一步是 `read_source`，读取上游实体，默认返回上游实体的正文；第二步是 `apply_render`，把第一步读到的内容转换成输出实体的正文，这是一个抽象方法，每个子类都必须实现它，例如 `TemplateToPrompt` 在这里渲染模板，`Command` 在这里运行命令；第三步是 `generate_props`，根据第二步的结果生成输出实体的附加信息，默认是上游实体附加信息的一份副本。这三个步骤都会收到同一个名为 `Environment` 的对象，称为渲染环境，它汇集了渲染时可以使用的全部数据。

普通的 `MapFunction` 需要分别实现 `transform_data` 和 `transform_props` 两个方法，runner 会先后调用它们。`RenderedMap` 已经替子类实现了这两个方法，并且保证对同一个上游实体和目标实体，上述三个步骤只执行一次，正文和附加信息都来自同一次执行的结果。因此，像外部命令或大模型这样耗时较长的调用，每个实体只会发生一次。

### 渲染环境

渲染环境是 `environment.template_env`，一份嵌套字典，模板和命令都读它。

```text
template_env
  operator                        function 参数，外加本次运行的 name、home
  job                             name、epoch
  entity                          正在渲染的实体
    source_name, source_data, source_tag, source_data_path
    target_name, target_data_path, output
```

`TemplateToPrompt` 把这份字典交给 Jinja。`Command` 按 `{operator.home}`、`{entity.output}` 这种点路径替换。`JinjaToJsonnet` 也用它，并另外把 `home` 放到最外层。实体的附加信息在 `entity.source_tag` 里，不再提升到最外层。

### 内置模板变量

下表列出了 `TemplateToPrompt` 的模板和 `Command` 的占位符可以使用的变量。Jinja 写成 `{{ operator.name }}`，`Command` 写成 `{operator.home}`。

| 变量 | 内容 |
| --- | --- |
| `operator.name` | 当前节点的名字 |
| `operator.home` | 当前算子 home 的绝对路径 |
| `operator.<参数名>` | function 的参数，例如 `operator.template` |
| `job.name`、`job.epoch` | 作业名和本次 epoch |
| `entity.source_name`、`entity.source_data`、`entity.source_tag`、`entity.source_data_path` | 上游实体 |
| `entity.target_name`、`entity.target_data_path`、`entity.output` | 正在写出的实体 |

不同的渲染类 function 使用这些变量的方式有所不同，下面分别说明。

`TemplateToPrompt` 使用 Jinja 渲染模板，因此可以使用 Jinja 的全部语法，例如用 `{% for column in columns %} ... {% endfor %}` 遍历一个列表，用 `{{ name | upper }}` 把文本转换成大写。正如第六章所说，它使用严格模式，引用不存在的变量会导致失败。

`Command` 不使用 Jinja，它只识别 `{名字}` 形式的占位符。名字中可以用点号逐层访问嵌套的对象，例如 `{global_prop.project}` 表示 `global_prop` 对象中的 `project`。占位符的名字只能由字母、数字、下划线和点号组成。`Command` 会替换 `argv` 中的每一项和 `output_file`，但不会替换 `cwd`。如果占位符引用的名字不存在，会以 `FatalError` 错误失败。

`JinjaToJsonnet` 也使用 Jinja，但最外层的变量不同：最外层是上游正文这个 JSON 对象中的各个键和 `variables` 参数中的各个键，再加上 `operator`、`entity`、`environment` 和 `home` 四个键，其中 `home` 就是 `operator.home`。上游附加信息中的键不在最外层，需要写成 `entity.<键>` 来访问。如果上游 JSON 中恰好有名为 `operator`、`entity`、`environment` 或 `home` 的键，它们会被这四个内置的键覆盖。此外，它还额外提供了 `jsonnet` 过滤器。

`JsonnetToPrompt` 不渲染任何模板。`PromptToLLM` 也不渲染提示词，它只在工具定义的 `run` 中替换 `{workspace}` 这一个占位符。

### 增加模板变量

当内置的变量不能满足需要时，可以用下面六种方法加入新的变量。它们按照所需改动从小到大的顺序排列，通常应该优先考虑排在前面的方法。

#### 在 props.json 或节点 config 中加入参数

function 参数中任何不属于保留键的键，都会出现在 `operator` 中。例如在 `props.json` 中写入 `"audience": "业务分析师"`，模板中就可以用 `{{ operator.audience }}` 引用它，`Command` 中可以用 `{operator.audience}` 引用它。同一个键也可以在添加节点时通过 `config` 指定，或者覆盖 `props.json` 中的默认值，例如 `config={"audience": "数据工程师"}`，模板读到的就是 `数据工程师`。这种方法适合放置固定不变的数据：写在 `props.json` 中，适合「同一个模板，在不同的算子 home 中取不同的值」；写在节点的 `config` 中，适合「同一个算子 home，在不同的作业或节点中取不同的值」。

#### 让上游把数据写进 tag.json

上游实体附加信息中的每个键，都会出现在模板的最外层，因此可以让上游步骤把需要的数据写进它的 `tag.json`。如果上游是一个 source 节点，可以编写 `DirectorySource` 的子类并覆盖 `extract_tag` 方法，把从文件内容中解析出来的字段放进附加信息，下游的模板就能直接引用这些字段。例如第九章的 `TableSource` 把 JSON 格式的表定义解析成 `table`、`description`、`columns` 三个键，于是下游的模板中可以直接写 `{% for column in columns %}`。

#### 用 generate_props 产生新的键

如果上游本身是一个渲染类的 map 节点，可以覆盖它的 `generate_props` 方法，在上游附加信息的副本上添加新的键，这样它的下游模板就能读到这些新键。下面的例子统计上游正文中的单词数，把这个数字作为正文，同时把它记录在附加信息的 `words` 键中：

```python
from docorder.functions.rendered_map import RenderedMap


class WordCount(RenderedMap):
    def apply_render(self, source, source_entity, environment):
        return str(len(source.split()))

    def generate_props(self, rendered, source, source_entity, environment):
        props = source_entity.carried_tag()
        props["words"] = int(rendered)
        return props
```

在这个节点的下游，模板中就可以写 `{{ words }}` 了。这里的 `carried_tag()` 返回上游附加信息的一份副本，在副本上修改不会影响上游实体本身。

#### 用 global_prop 跨越多个步骤传递数据

附加信息中的 `global_prop` 对象会被 runner 自动合并到每一个下游实体中，即使中间某个 function 产生的附加信息没有包含它，例如 `JinjaToJsonnet` 产生的附加信息是一个空对象，它也不会丢失。这种方法适合放置「从作业起点开始，后面每一步都可能用到」的数据，例如项目名称或批次编号。在 source 节点的附加信息中写入 `"global_prop": {"project": "订单域"}`，之后任何一个下游节点的模板都可以用 `{{ global_prop.project }}` 引用它，`Command` 中则写成 `{global_prop.project}`。

#### 利用 JinjaToJsonnet 的上游 JSON 和 variables 参数

对于 `JinjaToJsonnet`，上游正文这个 JSON 对象中的每个键都是最外层的变量，`variables` 参数为这些变量提供默认值。因此，要为它加入新的变量，可以让上游在 JSON 中多写一个键，也可以在 `props.json` 或节点的 `config` 中往 `variables` 里加一项。`variables` 是一个普通的 function 参数，所以节点的 `config` 可以覆盖它。

#### 继承渲染类并覆盖 apply_render

如果需要的值必须在渲染时才能计算出来，例如当天的日期、正文的行数，或者需要从其它地方查询得到的数据，可以编写 `TemplateToPrompt` 的子类并覆盖 `apply_render` 方法：先调用 `environment.template_env` 取得全部内置变量，再往里面加入新的键，然后交给父类提供的 `render` 方法完成渲染。

```python
from datetime import date

from docorder.functions.impl.template_to_prompt import TemplateToPrompt


class DatedPrompt(TemplateToPrompt):
    def apply_render(self, source, source_entity, environment):
        values = environment.template_env
        values["today"] = date.today().isoformat()
        values["line_count"] = len(source.splitlines())
        template = self.artifact.read_text(self.environment.operator_props["template"])
        return self.render(template, values, source_entity.name)
```

把这个类放进算子 home 的 `primary.py` 文件，在 `props.json` 中写上 `"class": "primary:DatedPrompt"` 和 `"template": "lib/p.jinja"`，模板中就可以使用 `{{ today }}` 和 `{{ line_count }}`，原有的内置变量也照样可以使用。方法中的 `source` 是 `read_source` 返回的上游正文，`self.artifact.read_text` 用于读取算子 home 中的文件，第八章会介绍它。需要注意的是，这些在渲染时注入的值不会被记进上游快照，例如日期变了，已经完成的实体并不会因此被重新处理。

对于 `JinjaToJsonnet`，做法与此类似：编写它的子类并覆盖 `read_source` 方法，在它返回的字典中加入新的键即可，因为这个字典中的键就是模板最外层的变量。

### 变量同名时以谁为准

当不同来源的变量重名时，按照以下规则决定最终生效的值。在 `entity` 中，runner 填入的 `name`、`data` 和 `output` 会覆盖上游附加信息中的同名键。提升到最外层之后，`operator`、`entity` 和 `environment` 这三个名字总是指向渲染环境本身，如果上游附加信息中也有这三个名字的键，只能通过 `entity.<键>` 访问到它们。在 `operator` 中，节点 `config` 中的参数先覆盖 `props.json` 中的同名参数，然后 runner 填入的 `name`、`home`、`class`、`type`、`parallelism`、`retry`、`output` 和 `epoch` 再覆盖这两处的同名键。在 `JinjaToJsonnet` 中，上游 JSON 中的键会覆盖 `variables` 中的同名键，而 `operator`、`entity`、`environment` 和 `home` 这四个内置的键又会覆盖上游 JSON 中的同名键。

## 八、开发自己的 function

当 docorder 自带的 function 不能满足需要时，可以自己编写 function。编写 function 的基本方式是：定义一个 Python 类，让它继承 docorder 提供的某个基类，并实现基类规定的几个方法；然后在算子 home 的 `props.json` 中，把 `class` 指向这个类。本章依次说明应该选择哪个基类、方法中可以使用哪些对象、必须遵守哪些约定、代码文件放在哪里，并给出每种算子类型的完整示例和测试方法。本章的所有示例代码都已经实际运行验证过。

### 选择基类

下表按照「你要做的事情」列出了应该继承的基类，以及必须实现和可以选择覆盖的方法。「必须实现」的方法是基类中的抽象方法，也就是基类只声明了名字、没有提供实现的方法，如果子类没有实现它们，装配阶段会以 `OperatorValidationError` 错误失败；「可以覆盖」的方法在基类中已经有默认实现，只有需要改变默认行为时才需要重写。

| 要做的事情 | `type` | 继承的基类 | 必须实现 | 可以覆盖 |
| --- | --- | --- | --- | --- |
| 从任意外部数据产生实体 | source | `docorder.functions.source_function:SourceFunction` | `emit()` | 无 |
| 从目录产生实体，但需要修改附加信息或挑选文件 | source | `DirectorySource` 或 `FilteredDirectorySource` | 无 | `extract_tag(name, content, tag)`、`include(path)`、`generate(directory)` |
| 逐个转换实体，正文和附加信息可以分别计算 | map | `docorder.functions.map_function:MapFunction` | `transform_data(source, target)`、`transform_props(source, target)` | 无 |
| 逐个转换实体，附加信息依赖转换的结果 | map | `docorder.functions.rendered_map:RenderedMap` | `apply_render(source, source_entity, environment)` | `read_source`、`generate_props` |
| 在自带的渲染类 function 上增加功能 | map | `TemplateToPrompt` 等自带的类 | 无 | `apply_render`、`generate_props` 等 |
| 把全部实体合并成一个 | reduce | `docorder.functions.reduce_function:ReduceFunction` | `transform_data(sources, target)`、`transform_props(sources, target)` | 无 |
| 把一个实体拆成多个 | fanout | `docorder.functions.fanout_function:FanoutFunction` | `transform_data(source, target)`、`transform_props(source, target)` | `output_names(source)` |
| 把上游正文写成作业结果文件 | output | `docorder.functions.output_function:OutputFunction` | 无 | 无 |

`SourceFunction` 的 `emit` 方法应该写成一个生成器，也就是在方法中用 `yield` 逐个交出结果，每次交出一个 `SourceRecord(name, data, tag)` 对象，三个参数分别是实体名、正文和附加信息。`SourceRecord` 同样定义在 `docorder.functions.source_function` 中。

### function 中可以使用的对象

在 function 的方法中，可以通过 `self` 访问以下属性：

| 属性 | 内容 |
| --- | --- |
| `self.operator` | 正在运行的算子。`name`、`props`、`output_path`、`operator_home`、`upstream` 都在算子上，不要再经过节点 |
| `self.environment` | 由 operator 构造。`operator_props` 是 function 参数；`template_env` 是模板里的 `operator` / `job` / `entity` |
| `self.artifact` | 对算子 home 的只读访问：`home` 是算子 home 的路径；`path(rel)` 把一个相对路径解析成算子 home 中的完整路径；`exists(rel)` 判断算子 home 中的某个文件是否存在；`read_text(rel)` 读取算子 home 中的某个文件。传入的路径都不能指向算子 home 之外 |
| `self.operator_name` | 当前节点的名字 |
| `self.epoch` | 本次运行的 epoch |

传给方法的上游实体和目标实体都是 `Entity` 对象，它们提供以下成员：

| 成员 | 内容 |
| --- | --- |
| `name` | 实体的名字 |
| `directory` | 实体目录的路径 |
| `read_text()` | 读取实体的正文；如果没有 `data` 文件，返回空字符串 |
| `tag` | 实体的附加信息，一个字典 |
| `carried_tag()` | 返回附加信息的一份浅拷贝，用于传给下游 |
| `staging_data` | 目标实体等待写入的正文，function 在 `transform_data` 中给它赋值 |

### 必须遵守的约定

`transform_data` 必须给 `target.staging_data` 赋一个字符串，`transform_props` 必须给 `target.tag` 赋一个字典，否则这个实体会以 `FatalError` 错误失败。如果目标目录里已经有 `data` 文件，可以不设 `staging_data`，runner 会保留该文件，只写 `tag.json`。如果要在上游附加信息的基础上做修改，应该先调用 `carried_tag()` 取得一份副本再修改，不要直接修改上游实体的 `tag`。`carried_tag()` 返回的是浅拷贝，也就是说只复制了最外层，嵌套在里面的列表和字典仍然与上游共用，所以如果要修改嵌套的内容，应该先自己复制一份。

function 不需要、也不应该自己写 `data` 和 `tag.json`，它们都由 runner 负责写入。function 也不需要自己创建线程池或者实现重试逻辑，并行和重试分别由节点的 `parallelism` 和 `retry` 参数控制。

function 中出现错误时，应该区分两类情况。第一类是重试也无法解决的问题，例如缺少必需的配置、输入的格式不正确，这时应该抛出 `docorder.utils.errors.FatalError`，让 stage 立即停止，避免白白浪费重试的时间。第二类是可能自行恢复的问题，例如网络错误、外部服务暂时不可用、外部进程偶尔失败，这时应该抛出其它类型的异常，交给 `retry` 机制自动重试。

runner 在处理每个实体的每一次尝试时，都会创建一个新的 function 对象，因此不要在对象的属性中保存需要跨实体使用的状态。并行执行时，function 运行在工作线程中，和算子共享同一份内存。

function 可以在 `target.directory` 也就是目标实体的目录中写入一些辅助文件，例如 `Command` 就会把命令的输出文件写在这里。这些辅助文件会在实体被重做或删除时随着实体目录一起被清除。

function 读取的、不属于上游实体的任何内容，例如算子 home 中的模板、其它节点的结果文件、外部服务返回的数据，都不会被记进上游快照，它们发生变化时，runner 不会自动重做已经完成的实体。

### 代码放在哪里

function 的代码有两种放置方式。

第一种方式是放在算子 home 自己的 `primary.py` 文件中，并在 `props.json` 中写 `"class": "primary:类名"`。这是最简单的方式，代码和配置、模板一起放在算子 home 里，复制算子 home 时代码也随之带走。一个算子 home 只能有一个 `primary.py`，但其中可以定义多个类。需要注意的是，`primary.py` 是按照文件路径直接加载的，算子 home 所在的目录并不在 Python 的模块搜索路径 `sys.path` 中，所以 `primary.py` 不能用 `import` 引入同一个算子 home 中的其它 Python 文件；不过它可以正常引入 docorder 和其它已经安装的包。

第二种方式是放在你自己项目的 Python 包中，并在 `props.json` 中写 `"class": "包名.模块名:类名"`。当多个算子 home 需要共用同一段代码，或者 function 的代码较多、需要拆分成多个模块时，适合使用这种方式。这个包必须能够被 Python 导入，例如已经安装在同一个虚拟环境中，或者与启动脚本位于同一个目录下。并行执行也在同一进程里，用的是同一份导入。

### 示例：自定义 source

下面的 source function 从一个 JSON Lines 文件中产生实体。JSON Lines 是一种每行一个 JSON 对象的文本格式，常用于存放一批记录。这个 function 为文件中的每一行产生一个实体：

```python
import json
from pathlib import Path

from docorder.functions.source_function import SourceFunction, SourceRecord
from docorder.utils.errors import FatalError


class JsonLinesSource(SourceFunction):
    def emit(self):
        raw = self.environment.operator_props.get("file")
        if not raw:
            raise FatalError("jsonl source config missing file")
        path = Path(raw)
        if not path.is_absolute():
            path = self.artifact.home / path
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            yield SourceRecord(
                name=record["id"],
                data=json.dumps(record, ensure_ascii=False),
                tag={"kind": record.get("kind", "")},
            )
```

对应的 `props.json`：

```json
{ "type": "source", "class": "primary:JsonLinesSource", "file": "items.jsonl" }
```

这个 function 从参数 `file` 读取文件路径，相对路径按算子 home 解析；参数缺失时抛出 `FatalError`，因为这是重试也无法解决的配置问题。`items.jsonl` 中每一行的 `id` 字段成为实体的名字，整行 JSON 成为实体的正文，`kind` 字段被记入附加信息。每行的 `id` 必须符合实体命名规则，而且彼此不能重复，否则这个 stage 会以 `OperatorValidationError` 错误失败。

### 示例：map

下面的 map function 把上游正文转换成大写，并在附加信息中加上一个标记：

```python
from docorder.functions.map_function import MapFunction


class Uppercase(MapFunction):
    def transform_data(self, source, target):
        target.staging_data = source.read_text().upper()

    def transform_props(self, source, target):
        tag = source.carried_tag()
        tag["uppercased"] = True
        target.tag = tag
```

对应的 `props.json`：

```json
{ "type": "map", "class": "primary:Uppercase" }
```

runner 会先调用 `transform_data`，再调用 `transform_props`，两者是分开调用的。如果两个方法都需要用到同一个中间结果，特别是需要一次耗时的外部调用才能得到的结果，就不适合直接继承 `MapFunction`，因为那样的话这个调用可能要做两次；这时应该改为继承 `RenderedMap`，它保证每个实体只计算一次。

### 示例：基于 RenderedMap

第七章「用 generate_props 产生新的键」一节中的 `WordCount`，就是一个完整的 `RenderedMap` 子类：`apply_render` 返回输出实体的正文，`generate_props` 在上游附加信息的副本上加入 `words` 键作为输出实体的附加信息。如果在转换之前需要先读取其它内容，例如把上游正文解析成 JSON，可以覆盖 `read_source` 方法，它的返回值会作为第一个参数 `source` 传给 `apply_render`。

### 示例：reduce

下面的 reduce function 把上游全部实体的正文用一个分隔符连接起来，合并成一个实体：

```python
from docorder.functions.reduce_function import ReduceFunction


class JoinBodies(ReduceFunction):
    def transform_data(self, sources, target):
        separator = self.environment.operator_props.get("separator", "\n")
        target.staging_data = separator.join(entity.read_text() for entity in sources)

    def transform_props(self, sources, target):
        target.tag = {"count": len(sources), "names": [entity.name for entity in sources]}
```

对应的 `props.json`：

```json
{ "type": "reduce", "class": "primary:JoinBodies", "output": "all", "separator": "\n---\n" }
```

输出实体的名字由 `output` 参数决定，这里是 `all`；`separator` 是这个 function 自己定义的参数，通过 `self.environment.operator_props` 读取。传入的 `sources` 是按实体名字排序的上游实体列表；如果上游一个实体都没有，`sources` 是一个空列表，function 仍然会被调用一次，所以代码要能正确处理空列表的情况。

### 示例：fanout

下面的 fanout function 把上游的每个实体按行拆开，每一行成为一个新的实体：

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

对应的 `props.json`：

```json
{ "type": "fanout", "class": "primary:SplitLines" }
```

如果上游实体 `notes` 的正文有三行，这个 function 会产生 `notes-0`、`notes-1`、`notes-2` 三个实体。由于整个 stage 中所有输出实体的名字必须互不相同，这里在名字前面加上了上游实体的名字作为前缀，以免不同上游实体拆出的名字发生冲突。`output_names` 必须返回一个列表；`transform_data` 根据目标实体名字中的序号，取出对应的那一行作为正文。

### 测试 function

测试 function 最直接的方法，是在一个临时目录中搭建一个只有几个节点的小作业，运行之后检查输出文件的内容。下面的 pytest 测试用例检查第九章中的 `TableIndex`：它把项目中的 `homes/` 目录复制到 pytest 提供的临时目录 `tmp_path` 中，用 pytest 的 `monkeypatch` 工具设置 `DOCORDER_HOMES` 环境变量（测试结束后会自动恢复），写入一个输入文件，然后运行 source 和 reduce 两个节点，最后检查汇总结果中是否包含这张表。

```python
import json
import shutil
from pathlib import Path

from docorder.core.job import Job
from docorder.core.runner import execute

PROJECT = Path(__file__).resolve().parents[1]


def test_index_lists_every_table(tmp_path, monkeypatch):
    homes = tmp_path / "homes"
    shutil.copytree(PROJECT / "homes", homes)
    data = tmp_path / "tables"
    data.mkdir()
    (data / "orders.json").write_text(
        json.dumps({"table": "orders", "description": "订单", "columns": []}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOCORDER_HOMES", str(homes))

    job = Job("test", tmp_path / "runs")
    job.add_operator_node("tables", "table_source", config={"directory": str(data)})
    job.add_operator_node("index", "table_index", upstream="tables")
    execute(job, "t", start_from_scratch=True)

    index = (tmp_path / "runs" / "index" / "t" / "index" / "data").read_text(encoding="utf-8")
    assert "- orders：订单" in index
```

这个测试中的节点都没有设置 `parallelism`，所以全部在当前进程中运行，出错时异常信息和调用栈都比较直观，也方便设置断点调试。代码中的 `PROJECT` 假定这个测试文件位于项目的 `tests/` 目录下，`parents[1]` 就是项目的根目录。

## 九、在自己的项目中使用 docorder

本章用一个完整的例子，说明在自己的项目中使用 docorder 的全部步骤。假设项目名为 `my-docs`，其中有一批用 JSON 文件描述的数据表定义，我们希望为每张表生成一段提示词，交给命令行形式的大模型工具，让它写出这张表的说明，最后把所有表汇总成一份表清单。这个作业由四个节点组成，依次是 source、map、map 和 reduce，其中用到了两个 docorder 自带的 function 和两个自己编写的 function。本章的所有文件和命令都已经实际运行验证过。

### 第一步：安装 docorder

docorder 目前没有发布到 PyPI，所以不能直接用 `pip install docorder` 安装，需要先从源码仓库构建出安装包。下面的命令会克隆仓库，并用 uv 构建安装包。uv 是一个 Python 的包和项目管理工具，可以在它的官网找到安装方法。

```bash
git clone https://github.com/jixie-wish/docorder.git
cd docorder
uv build
```

构建完成后，仓库的 `dist/` 目录下会生成一个名为 `docorder-0.1.0-py3-none-any.whl` 的文件，这是 Python 的标准安装包格式。接下来创建自己的项目，并把这个安装包安装进去：

```bash
mkdir my-docs && cd my-docs
uv init --bare
uv add /path/to/docorder/dist/docorder-0.1.0-py3-none-any.whl
```

`uv init --bare` 只在当前目录生成一个最基本的 `pyproject.toml`，也就是 Python 项目的配置文件；`uv add` 会创建项目自己的虚拟环境，把 docorder 安装进去，并把这个依赖记录到 `pyproject.toml` 中。命令中的 `/path/to/docorder` 要换成你实际克隆仓库的位置。

如果你在使用 docorder 的同时还会修改 docorder 本身的代码，可以改用 `uv add --editable /path/to/docorder`，这种方式安装的 docorder 直接指向源码目录，修改源码后立即生效，不需要重新构建和安装。如果不使用 uv，也可以在自己的虚拟环境中执行 `pip install /path/to/docorder-0.1.0-py3-none-any.whl`。docorder 要求 Python 3.10 或更高的版本，它依赖的 jinja2 和 pyyaml 两个包会在安装时一并装好。

### 第二步：规划目录

在开始编写文件之前，先规划好项目的目录结构。下面是这个示例项目最终的样子：

```text
my-docs/
  pyproject.toml
  run.py                          启动脚本：构建作业并执行
  data/
    tables/                       输入数据，每张表一个 JSON 文件
      orders.json
      users.json
  homes/                          DOCORDER_HOMES 指向这里
    sources/
      table_source/               source 算子：读取 data/tables
        props.json
        primary.py                自己编写的 function：TableSource
    render/
      table_prompt/               map 算子：渲染提示词
        props.json
        lib/table.jinja
    llm/
      ask_llm/                    map 算子：调用大模型工具
        props.json
        tools/echo.json
    summary/
      table_index/                reduce 算子：汇总表清单
        props.json
        primary.py                自己编写的 function：TableIndex
  workspace/                      大模型工具的工作目录，由 run.py 自动创建
  runs/                           输出根目录，不纳入版本管理
```

这个结构中的每个部分各有分工。输入数据放在 `data/` 目录中，它属于项目本身，由 source 节点读取，docorder 不会修改其中的任何文件。算子放在 `homes/` 目录中，按用途分在几个分类子目录下，每个算子 home 一个目录，自己编写的 function 放在各自算子 home 的 `primary.py` 文件中。运行结果全部写在 `runs/` 目录中，它完全由 docorder 管理，可以随时删除后重新生成。`run.py` 是整个作业唯一的入口，负责设置 `DOCORDER_HOMES`、构建作业和启动运行。

### 第三步：准备输入数据

在 `data/tables/` 目录中，为每张表写一个 JSON 文件。下面是 `orders.json` 的内容：

```json
{
  "table": "orders",
  "description": "每笔订单一行",
  "columns": [
    {"name": "order_id", "type": "bigint", "comment": "订单号"},
    {"name": "user_id", "type": "bigint", "comment": "下单用户"},
    {"name": "amount", "type": "decimal(10,2)", "comment": "订单金额"}
  ]
}
```

`users.json` 的结构与它相同，只是描述的是用户表，有 `user_id` 和 `city` 两个字段。文件名去掉后缀就是实体的名字，所以文件名需要符合实体命名规则，特别是不能以 `.` 或 `_` 开头。这个目录中如果还有其它不以 `.json` 结尾的文件，例如一份说明文档，它们会被下一步配置的后缀过滤条件排除，不会变成实体。

### 第四步：编写算子 home

#### table_source：读取表定义

这个算子负责读取 `data/tables/` 中的 JSON 文件，并把文件中的字段解析出来，放进实体的附加信息中，供下游的模板使用。

`homes/sources/table_source/props.json` 的内容如下：

```json
{
  "type": "source",
  "class": "primary:TableSource",
  "filter": { "enabled_suffix": ".json" },
  "project": "订单域"
}
```

`homes/sources/table_source/primary.py` 的内容如下：

```python
import json

from docorder.functions.impl.directory_source import FilteredDirectorySource
from docorder.utils.errors import FatalError


class TableSource(FilteredDirectorySource):
    def extract_tag(self, name, content, tag):
        tag = dict(tag)
        try:
            spec = json.loads(content)
        except json.JSONDecodeError as exc:
            raise FatalError(f"{name} is not valid JSON: {exc}") from exc
        tag["table"] = spec["table"]
        tag["description"] = spec.get("description", "")
        tag["columns"] = spec.get("columns", [])
        tag["global_prop"] = {"project": self.environment.operator_props.get("project", "")}
        return tag
```

`TableSource` 继承了 `FilteredDirectorySource`，因此「读取实体目录」和「按 `filter` 参数筛选」这两项功能都直接沿用父类的实现，`props.json` 中的 `filter` 就是交给父类使用的参数。它只覆盖了 `extract_tag` 方法：先拿到输入目录里的 `tag.json`，再解析 `data` 的 JSON，把 `table`、`description` 和 `columns` 三个字段加进去；如果正文不是合法的 JSON，就抛出 `FatalError`，因为这种错误重试也无法解决。最后，它把 `props.json` 中自定义的参数 `project` 放进 `global_prop`，这样项目名称会被 runner 一路传递到最后的汇总节点。你可能注意到 `props.json` 中没有写 `directory` 参数，这是因为输入目录属于项目而不属于算子，它会由 `run.py` 通过节点的 `config` 传入，这样这个算子 home 就可以原样复制到其它项目中使用。

#### table_prompt：渲染提示词

这个算子直接使用 docorder 自带的 `TemplateToPrompt`，不需要编写任何代码，只需要准备 `props.json` 和模板文件。

`homes/render/table_prompt/props.json` 的内容如下：

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "template": "lib/table.jinja",
  "audience": "业务分析师"
}
```

`homes/render/table_prompt/lib/table.jinja` 的内容如下：

```text
请为{{ operator.audience }}写一段 {{ table }} 表的说明。

项目：{{ global_prop.project }}
用途：{{ description }}

| 字段 | 类型 | 含义 |
| --- | --- | --- |
{% for column in columns -%}
| {{ column.name }} | {{ column.type }} | {{ column.comment }} |
{% endfor %}
```

模板中用到的变量来自三个不同的地方。`table`、`description` 和 `columns` 来自上游实体的附加信息，也就是 `TableSource` 解析出来的字段；`global_prop.project` 同样来自上游附加信息中的 `global_prop`；`operator.audience` 则来自这个算子 home 的 `props.json` 中自定义的参数 `audience`。模板中的 `{% for column in columns -%}` 遍历字段列表，为每个字段输出一行表格，`-%}` 中的减号用于去掉这个标签之后的换行，使输出的表格行之间不留空行。

#### ask_llm：调用大模型工具

这个算子使用 docorder 自带的 `PromptToLLM`，把上一步生成的提示词交给大模型工具。

`homes/llm/ask_llm/props.json` 的内容如下：

```json
{
  "type": "map",
  "class": "docorder.functions.impl.prompt_to_llm:PromptToLLM",
  "tool": "echo",
  "retry": { "max_attempts": 3, "backoff_seconds": 5 }
}
```

`homes/llm/ask_llm/tools/echo.json` 的内容如下：

```json
{
  "name": "echo",
  "run": ["cat"],
  "prompt": "stdin"
}
```

`tool` 参数的值 `echo` 会让 `PromptToLLM` 去读取这个算子 home 中的 `tools/echo.json`。这个工具定义使用系统命令 `cat`，把从标准输入收到的提示词原样打印出来，它只是为了让这个示例不依赖任何真实的大模型服务也能完整运行。在实际使用时，你需要在 `tools/` 目录中另外新建一个工具定义文件，把其中的 `run` 换成你所用的大模型命令行工具，再把 `props.json` 中的 `tool` 改成这个新工具的名字。`retry` 配置表示每个实体最多尝试三次，这对于偶尔出错的大模型接口很有必要。`PromptToLLM` 必需的 `workspace` 参数同样由 `run.py` 通过节点的 `config` 传入。

#### table_index：汇总表清单

这个算子是一个自己编写的 reduce function，它把所有表的信息汇总成一份 Markdown 格式的表清单。

`homes/summary/table_index/props.json` 的内容如下：

```json
{
  "type": "reduce",
  "class": "primary:TableIndex",
  "output": "index",
  "title": "表清单"
}
```

`homes/summary/table_index/primary.py` 的内容如下：

```python
from docorder.functions.reduce_function import ReduceFunction


class TableIndex(ReduceFunction):
    def transform_data(self, sources, target):
        lines = [f"# {self.environment.operator_props.get('title', '表清单')}", ""]
        for entity in sources:
            lines.append(f"- {entity.tag.get('table', entity.name)}：{entity.tag.get('description', '')}")
        target.staging_data = "\n".join(lines) + "\n"

    def transform_props(self, sources, target):
        target.tag = {"tables": [entity.name for entity in sources]}
```

这个 reduce 节点的上游是 `ask_llm` 节点。由于 `TemplateToPrompt` 和 `PromptToLLM` 都会把上游的附加信息原样复制给下游，`TableSource` 最初解析出来的 `table` 和 `description` 一直被保留到了这里，所以 `TableIndex` 可以直接从每个上游实体的 `tag` 中读取它们。`title` 是这个 function 自定义的参数，用作清单的标题。输出实体的名字由 `output` 参数决定，即 `index`。

### 第五步：编写启动脚本

`run.py` 的内容如下：

```python
import argparse
import os
from pathlib import Path

from docorder.core.job import Job
from docorder.core.runner import execute

ROOT = Path(__file__).resolve().parent


def build_job() -> Job:
    job = Job("table-docs", ROOT / "runs")
    job.add_operator_node(
        "tables",
        "table_source",
        config={"directory": str(ROOT / "data" / "tables")},
    )
    job.add_operator_node("prompts", "table_prompt", upstream="tables", parallelism=2)
    job.add_operator_node(
        "answers",
        "ask_llm",
        upstream="prompts",
        config={"workspace": str(ROOT / "workspace")},
    )
    job.add_operator_node("index", "table_index", upstream="answers")
    return job


def main() -> None:
    parser = argparse.ArgumentParser(description="为 data/tables 下的表生成说明")
    parser.add_argument("epoch", help="本次运行的 epoch，例如 2026-10-16")
    parser.add_argument("--scratch", action="store_true", help="让 source 重新读取 data/tables")
    args = parser.parse_args()

    homes = [str(ROOT / "homes"), os.environ.get("DOCORDER_HOMES", "")]
    os.environ["DOCORDER_HOMES"] = os.pathsep.join(path for path in homes if path)
    (ROOT / "workspace").mkdir(exist_ok=True)

    execute(build_job(), args.epoch, start_from_scratch=args.scratch)
    print((ROOT / "runs" / "index" / args.epoch / "index" / "data").read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
```

这个脚本有几处值得说明。`build_job` 函数构建了一个包含四个节点的作业：`tables` 节点使用 `table_source` 算子，并通过 `config` 传入输入目录；`prompts` 节点以 `tables` 为上游，使用 `table_prompt` 算子，并设置 `parallelism=2`，允许最多两个线程同时渲染；`answers` 节点以 `prompts` 为上游，使用 `ask_llm` 算子，并通过 `config` 传入大模型工具的工作目录；`index` 节点以 `answers` 为上游，使用 `table_index` 算子。

`main` 函数用 Python 标准库 `argparse` 解析命令行参数：第一个参数是 epoch，可选的 `--scratch` 开关决定是否传入 `start_from_scratch=True`。设置 `DOCORDER_HOMES` 的代码必须放在调用 `build_job()` 之前，因为算子 home 是在添加节点时查找的；这里把项目自己的 `homes/` 放在最前面，使项目中的算子 home 优先于环境中原有的同名算子 home，同时保留环境变量中原有的目录。`os.pathsep` 是当前系统的路径分隔符，这样写可以同时适用于 macOS、Linux 和 Windows。脚本中的所有路径都从 `ROOT`，也就是脚本所在的目录出发计算，所以无论从哪个目录执行这个脚本，结果都相同。

项目特有的路径，也就是输入目录和工作目录，都通过节点的 `config` 传入，算子 home 中不包含任何与项目有关的路径，因此这些算子 home 可以原样复制到其它项目中使用。`prompts` 节点的 `parallelism=2` 会在当前进程里用两个线程同时渲染，不另起子进程。

### 第六步：运行并查看结果

在一个新的 epoch 上第一次运行时，需要加上 `--scratch`，让 source 节点读取输入数据：

```bash
uv run python run.py 2026-10-16 --scratch
```

运行结束后，脚本会打印汇总节点的结果：

```text
# 表清单

- orders：每笔订单一行
- users：注册用户
```

此时 `runs/` 目录的结构如下，每个节点都有一个与节点同名的目录，其中的 `2026-10-16/` 是 epoch 目录：

```text
runs/
  tables/   .docorder-output  2026-10-16/{orders,users}/  data, tag.json
  prompts/  .docorder-output  2026-10-16/{orders,users}/  data, tag.json
  answers/  .docorder-output  2026-10-16/{orders,users}/  data, tag.json
  index/    .docorder-output  2026-10-16/index/           data, tag.json
```

打开 `runs/prompts/2026-10-16/orders/data`，可以看到渲染好的提示词，模板中的各个变量都已经被替换成了实际的值：

```text
请为业务分析师写一段 orders 表的说明。

项目：订单域
用途：每笔订单一行

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| order_id | bigint | 订单号 |
| user_id | bigint | 下单用户 |
| amount | decimal(10,2) | 订单金额 |
```

再打开 `runs/index/2026-10-16/index/tag.json`，可以看到除了 `TableIndex` 写入的 `tables` 之外，还有从 source 节点一路传下来的 `global_prop`，尽管 `TableIndex` 并没有主动复制它：

```json
{
  "global_prop": {
    "project": "订单域"
  },
  "tables": [
    "orders",
    "users"
  ]
}
```

### 第七步：修改之后再次运行

项目投入使用之后，输入数据、模板和代码都会不断修改。不同的修改需要用不同的方式再次运行，这些方式都源自第三章「再次运行时的判定」一节中的规则。

如果运行中途失败了，例如大模型工具在用完全部重试次数后仍然报错，先修复导致失败的问题，然后用同一个 epoch 再运行一次，不需要加 `--scratch`：`uv run python run.py 2026-10-16`。已经完成的实体会因为比较通过而被保留，docorder 只会补做失败的实体，以及受它们影响的下游实体。

如果修改了输入数据，也就是在 `data/tables/` 中新增、修改或删除了文件，再次运行时必须加上 `--scratch`，source 节点才会重新读取目录。之后，只有正文真正发生变化的表会沿着作业图被重新处理，新增的表会被新建，删除的表会从下游各个节点中被删除，而汇总节点由于上游发生了变化，会重新生成表清单。例如新增一个 `payments.json` 后加上 `--scratch` 再运行，表清单中会多出一行 `payments`；如果忘了加 `--scratch`，source 节点不会读取新文件，表清单也不会有任何变化。

如果修改了模板、`props.json` 中的参数或者 function 的代码，docorder 不会察觉到这些修改，需要先删除受影响节点的 epoch 目录，再运行一次。例如修改了 `table.jinja` 之后，执行 `rm -rf runs/prompts/2026-10-16` 删除提示词节点的结果，再执行 `uv run python run.py 2026-10-16`：`prompts` 节点会重新渲染所有提示词，由于提示词的内容变了，`answers` 和 `index` 两个节点也会随之重新处理。如果只希望个别实体被重新处理，可以只删除对应的实体目录，例如 `runs/prompts/2026-10-16/orders`。

如果希望保留当前的全部结果，另外完整地重新运行一遍，可以换一个新的 epoch，例如 `uv run python run.py 2026-10-17 --scratch`。旧 epoch 的目录不会被自动清理，不再需要时要手动删除。

### 纳入版本管理

项目中的 `data/`、`homes/`、`run.py`、`pyproject.toml` 和 `uv.lock`（uv 生成的依赖锁定文件）都应该纳入版本管理。`runs/` 和 `workspace/` 是运行时产生的文件，应该写进 `.gitignore`，避免被提交：

```text
runs/
workspace/
```

另外，不要把访问令牌、密码之类的凭据写进 `props.json` 或工具定义文件，因为这些文件会随项目一起被提交到代码仓库中。大模型工具需要的凭据应该放在环境变量中，由工具自己读取。

## 附录 A：内置 function 一览

| 类 | `class` 的写法 | `type` | 参数 |
| --- | --- | --- | --- |
| `DirectorySource` | `docorder.functions.impl.directory_source:DirectorySource` | source | `directory` |
| `FilteredDirectorySource` | `docorder.functions.impl.directory_source:FilteredDirectorySource` | source | `directory`、`filter` |
| `TemplateToPrompt` | `docorder.functions.impl.template_to_prompt:TemplateToPrompt` | map | `template` |
| `JinjaToJsonnet` | `docorder.functions.impl.jinja_to_jsonnet:JinjaToJsonnet` | map | `template`、`variables` |
| `JsonnetToPrompt` | `docorder.functions.impl.jsonnet_to_prompt:JsonnetToPrompt` | map | 无 |
| `Command` | `docorder.functions.impl.command:Command` | map | `argv`、`cwd`、`output_file`、`capture` |
| `PromptToLLM` | `docorder.functions.impl.prompt_to_llm:PromptToLLM` | map | `workspace`、`tool` |

编写 function 时用到的基类和辅助类分别定义在以下模块中：`SourceFunction` 和 `SourceRecord` 在 `docorder.functions.source_function` 中，`MapFunction` 在 `docorder.functions.map_function` 中，`RenderedMap` 在 `docorder.functions.rendered_map` 中，`ReduceFunction` 在 `docorder.functions.reduce_function` 中，`FanoutFunction` 在 `docorder.functions.fanout_function` 中，`OutputFunction` 在 `docorder.functions.output_function` 中。`Artifact` 在 `docorder.core.artifact` 中，`Environment` 在 `docorder.core.environment` 中。异常类 `DocorderError`、`JobValidationError`、`OperatorValidationError` 和 `FatalError` 都在 `docorder.utils.errors` 中，重试策略 `RetryPolicy` 在 `docorder.utils.retry` 中。

## 附录 B：实现索引

| 路径 | 职责 |
| --- | --- |
| `src/docorder/core/artifact.py` | 算子 home 的只读文件入口 |
| `src/docorder/core/entity.py` | 检查实体名字，读写实体目录，计算和比较上游快照 |
| `src/docorder/core/storage.py` | 管理一个 epoch 目录中的实体，负责新建、清理和删除 |
| `src/docorder/core/operator.py` | 解读 `props.json`，表示节点，列出应得名单，执行五种算子并切分并行任务 |
| `src/docorder/core/job.py` | 作业图的构建、检查和拓扑排序 |
| `src/docorder/core/runner.py` | 装配作业，逐个执行 stage，管理输出目录标记 |
| `src/docorder/utils/paths.py` | 解析 `DOCORDER_HOMES`，查找算子 home |
| `src/docorder/utils/modules.py` | 加载 `primary:类名` 和 `模块:类名` 形式的 function 类 |
| `src/docorder/core/environment.py` | 渲染环境：`operator_props` 与 `template_env` |
| `src/docorder/functions/` | function 基类；内置实现在 `functions/impl/` |
| `tests/test_contract.py` | 以上各项行为的契约测试 |

## 附录 C：相关文档

- [README](../README.md)：安装、快速开始和常见问题排查。
- [glossary.md](../glossary.md)：术语表。
- [Jinja 模板文档](https://jinja.palletsprojects.com/en/stable/templates/)：`TemplateToPrompt` 和 `JinjaToJsonnet` 使用的模板语法。
- [Jsonnet](https://jsonnet.org/)：`JsonnetToPrompt` 编译的配置语言。
- [concurrent.futures.ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor)：map 和 fanout 节点并行执行时使用的线程池。

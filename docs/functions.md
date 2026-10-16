# Function

[English](functions.en.md)

function 是算子 home 加载的 Python 类，真正读入上游实体、写出新实体的正文和 tag 的就是它。本文是包内 function 的配置参考：每个 function 做什么、`props.json` 里要写哪些键、渲染时模板能读到哪些变量、失败时会不会重试，以及包里没有现成实现时，如何在 home 里自己写一个。

调度这一层，即 runner 如何决定哪些实体要执行、并行怎样切分、失败后怎样续跑，写在 [design.md](design.md)。安装和第一次运行见 [README](../README.md)。

包内可以直接写进 `class` 的 function 有八个：两个 source，五个 map，一个 output。reduce 和 fanout 只有基类，要用时在 home 里实现。

## 文档结构

1. function 与实体、算子、作业的关系，以及算子 home 的组成。
2. `props.json` 的字段归属，参数怎样进入一次运行，哪些失败会重试。
3. 渲染类 function 的模板变量：有哪些、从哪里来、怎样增加、怎样引用。
4. 两个 source function。
5. 五个 map function。
6. 在 home 里实现 function，附 reduce 与 fanout 的完整例子。
7. 附录列出可以写进 `class` 的类名。

文中有三处结构说明：算子 home 的目录组成，一次渲染时模板环境的字段归属，以及各 function 的失败处理对照。

## 一、function 在作业里的位置

### 实体、算子与 function

一次转换的单位是实体。实体是 epoch 目录下的一层子目录，目录名就是实体名。名字不能为空，不能含 `/` 或 `\`，不能以 `.` 或 `_` 开头。使用者最常读写目录里的两份文件：`data` 是正文，`tag.json` 是一个 JSON 对象，放给下游过滤和填模板用的特性。有上游的实体完成后，快照写在 `tag.json` 的 `upstream` 里，由 runner 写，function 不碰它。

算子是可复用的转换，它的静态文件放在一个目录里，这个目录称为算子 home。home 不记录某次运行的输出位置。作业把若干 home 连成一张图，并为每个节点决定输出路径和要覆盖的参数。

function 是 home 里 `class` 指向的那个类。runner 为一次调用构造它的实例，把上游实体和一个尚未写入正文的目标实体交给它。function 只负责给目标填上正文和 tag，落盘、快照、重试和并行都由 runner 完成。使用者通常不直接调用 function，而是准备 home，再在作业里引用它。

### 算子 home 的组成

```text
<DOCORDER_HOMES 中的某个目录>/[可选的分类目录/]<home 名>/
  props.json     必需。类型、function 类、调度字段与 function 参数
  primary.py     可选。class 写 primary:类名 时从这里加载
  lib/           可选。模板等随算子分发的文件
  tools/         可选。PromptToLLM 的工具预设，一个预设一份 <名字>.json
```

`DOCORDER_HOMES` 用系统路径分隔符列出若干目录，和 `PATH` 一样，列表中靠前的同名 home 优先。runner 先在每个目录下直接找 `<home 名>/props.json`，找不到时再看一层分类目录；名字以 `.` 或 `_` 开头的分类目录会被跳过。包内不附带 home，`lib/`、`tools/` 里的文件都由使用者自己准备。

function 读 home 内的文件时，路径相对 home 解析，并且不能用 `..` 或绝对路径跳出 home。`template` 这类参数因此只能指向 home 里的文件。

## 二、配置

### props.json 的字段

`props.json` 是一个 JSON 对象，键分三类。

```text
props.json
  type, class                 身份。必须书写，作业不能改
  parallelism, retry          调度。作业添加节点时用同名参数覆盖
  其余键                      function 参数。节点的 config 覆盖同名键
```

`type` 取 `source`、`map`、`reduce`、`fanout`、`output` 之一。前四种决定上游实体和输出实体如何对应；`output` 把上游正文写成作业结果文件。`class` 写成 `模块:类名`，例如 `docorder.functions.impl.command:Command`；写成 `primary:类名` 时，从 home 下的 `primary.py` 加载。这个类必须是该 `type` 对应基类的具体子类，抽象方法都要实现。`type` 或 `class` 缺失、格式不对时，`add_operator_node` 当场失败；类找不到或不是对应子类时，`execute` 在执行任何算子之前失败。

`parallelism` 是 map 与 fanout 的并行度，缺省为 1。`retry` 是一个对象，`max_attempts` 是单个实体最多尝试的次数，缺省为 1，`backoff_seconds` 是退避基数，缺省为 0。作业在 `add_operator_node` 上用 `parallelism=` 和 `retry=` 两个参数覆盖它们。这两个字段写进节点的 `config` 不起调度作用，只会成为 function 参数。

其余键都是 function 参数，例如目录、模板路径、筛选条件。节点的 `config` 与它们合并，同名时以节点为准。`config` 里的 `class` 会被丢掉，不能用来更换 function。并行度大于 1 时，map 和 fanout 在线程里分片，参数留在当前进程的内存中。

下面是一个 map 算子的 home 配置。`template` 不是调度字段，而是这个 function 的参数，也可以由作业在添加节点时传入别的值。

```json
{
  "type": "map",
  "class": "docorder.functions.impl.template_to_prompt:TemplateToPrompt",
  "parallelism": 4,
  "retry": { "max_attempts": 3, "backoff_seconds": 5 },
  "template": "lib/prompt.jinja"
}
```

### 参数怎样进入一次运行

function 在运行时持有一份 `environment`，上面有两份相关的数据，用途不同。

第一份是 `environment.operator_props`，即上面合并后的 function 参数。function 用它决定读哪个目录、哪份模板、哪条命令。

第二份是 `environment.template_env`，给模板用，里面是嵌套的 `operator`、`job`、`entity`。`operator` 以合并后的 function 参数为底，并写入本次运行的 `name` 和 `home`。`job` 有作业名和 epoch。`entity` 在渲染某个实体时才有 source/target 字段。

`operator.output` 是这个节点的输出目录，即 `输出根/节点名`，不含 epoch 那一层。正在写出的实体自己的目录是 `entity.output`，即 `输出根/节点名/epoch/实体名`。要在实体旁边放文件时，用 `entity.output`。

### 失败与重试

runner 对单个实体的调用按 `retry` 重试，但 `FatalError` 例外：它表示配置或输入本身有问题，再试一次也不会好，所以直接让这一段失败。其余异常，包括外部进程返回非零状态，都会在等待 `backoff_seconds × 已尝试次数` 秒之后再试，直到用完 `max_attempts`。

| function | 立即失败，不重试 | 按 `retry` 重试 |
| --- | --- | --- |
| `DirectorySource`、`FilteredDirectorySource` | 缺 `directory`、目录不存在、`filter` 写错、`data` 不是 UTF-8、`tag.json` 不是对象 | 无，见第四章 |
| `TemplateToPrompt` | 缺 `template`、模板文件不在 home 里、模板引用了不存在的变量 | 无 |
| `JinjaToJsonnet` | 缺 `template`、上游正文为空或不是 JSON 对象、渲染结果只有空白 | 无 |
| `JsonnetToPrompt` | 找不到 `jsonnet` | 编译器返回非零状态 |
| `Command` | 缺 `argv`、找不到第一项命令、花括号变量不存在、`capture` 取值不对 | 进程返回非零状态、命令没有写出 `output_file` |
| `PromptToLLM` | 缺 `workspace` 或目录不存在、找不到工具、工具定义不合法、找不到第一项命令 | 进程返回非零状态、写出的 `data` 为空、不是 UTF-8，或 `data` 不是文件 |
| `Output` | `directory` 不是非空字符串、`name_template` 不是字符串或渲染失败、得到的文件名不合法、两个实体得到同一个文件名 | 写出作业结果文件时的瞬时错误 |

## 三、渲染与模板变量

### 渲染过程

五个 map function 共用一个渲染过程（`RenderedMap`）。对每个上游实体，它先读取上游，再得到新的正文，最后得到新的 tag。默认情况下，读取的是上游正文，写出的 tag 是上游 tag 的副本。具体 function 替换其中的读取、渲染或 tag 步骤。每个上游实体只渲染一次，正文和 tag 来自同一次渲染。

每次渲染构造一份 `template_env`，字段归属如下。

```text
template_env
  operator     function 参数，外加本次运行的 name、home
  job          name、epoch
  entity       source_name、source_data、source_tag、source_data_path
               target_name、target_data_path、output
```

### 两种引用方式

`TemplateToPrompt` 把 `template_env` 交给 Jinja，写 `{{ operator.home }}`、`{{ job.epoch }}`、`{{ entity.source_data }}`。`Command` 按 `{operator.home}`、`{entity.output}` 这种点路径替换。上游 tag 在 `entity.source_tag` 里。

`JinjaToJsonnet` 的顶层名字来自上游正文里的 JSON 对象，以及参数 `variables`，同名时以上游 JSON 为准。之后再并上 `template_env`，并加上顶层 `home`（与 `operator.home` 相同）。JSON 里的 `operator`、`job`、`entity`、`home` 不会替换环境提供的对象。

`JsonnetToPrompt` 与 `PromptToLLM` 同样经过渲染过程，但正文不做上述替换。前者把上游正文当作完整的 jsonnet 程序编译，后者把上游正文原样交给模型工具。模型工具的参数里，只有字面量 `{workspace}` 会换成参数 `workspace` 的值。

### 增加变量

新变量出现在模板里的什么位置，取决于它写在哪里。

写在上游实体的 `tag.json` 里时，下一个使用铺平命名空间的 function 会在顶层和 `entity` 里同时见到它。`name`、`data`、`output` 由本次渲染填写，`operator`、`entity`、`environment` 留给环境对象，tag 里用这些名字会被遮住。

写在算子 `props.json` 的 function 参数里，或写在节点的 `config` 里时，模板通过 `operator.键名` 读取，两处都有时以节点 `config` 为准。`name`、`home`、`class`、`type`、`parallelism`、`output`、`retry`、`epoch` 由本次运行填写，会覆盖同名的参数。

对 `JinjaToJsonnet`，还可以把键放进上游正文的 JSON 对象，或放进参数 `variables`。这些键成为 Jinja 的顶层名字。`{{ 键 | jsonnet }}` 把值写成 jsonnet 字面量：字符串带引号，对象和数组按 JSON 写出。模板引用了没有提供的名字时，渲染失败。

变量要由本算子算出来再交给下游时，在子类里写进 tag。目录类 source 覆盖 `extract_tag(name, content, tag)`，参数是实体目录名、`data` 正文，以及从 `tag.json` 读出的对象。渲染类 function 覆盖 `generate_props`，在上游 tag 的副本上追加字段。下游渲染时，会在 `entity` 和铺平命名空间的顶层读到这些字段。

### 在模板中引用

在 `TemplateToPrompt` 的 Jinja 模板里，`{{ name }}` 是实体名，`{{ data }}` 是上游正文，`{{ operator.home }}` 是算子 home，`{{ entity.output }}` 是正在写出的实体目录。同样的信息也可以写成 `{{ environment.entity.data }}`、`{{ environment.operator.home }}`。

`Command` 的每个参数以及 `output_file` 使用单层花括号，名字与铺平命名空间相同，例如 `{name}`、`{operator.home}`、`{entity.output}`。

在 `JinjaToJsonnet` 里，`{{ title }}` 读取上游 JSON 或 `variables` 里的 `title`。算子 home 写作 `{{ home }}` 或 `{{ environment.operator.home }}`，正在写出的实体目录写作 `{{ environment.entity.output }}`。

## 四、source function

source 是图的起点，没有上游。只有 `execute` 传入 `start_from_scratch=True` 时，source 才调用 function 重写本 epoch 的实体；否则它不改动自己的输出，下游读取该 epoch 里已有的实体。source 的 `retry` 只作用于把一条记录写到磁盘这一步；读取目录、读取文件时抛出的异常直接让这一段失败。

### DirectorySource

本 function 把一个已经存在的目录收成当前 epoch 的第一批实体。它只读取该目录下直接包含的、已经符合实体约定的子目录：子目录名是实体名，里面要有 `data` 和 `tag.json`。正文是 `data` 的 UTF-8 文本，tag 是 `tag.json` 里的 JSON 对象。普通文件、缺 `data` 或 `tag.json` 的子目录、以及名字以 `.` 或 `_` 开头的子目录都会被跳过。

在 home 的 `props.json` 里，`type` 为 `source`，`class` 为 `docorder.functions.impl.directory_source:DirectorySource`，`directory` 给出目录。相对路径相对算子 home 解析，不相对当前工作目录；绝对路径按原样使用。

```json
{
  "type": "source",
  "class": "docorder.functions.impl.directory_source:DirectorySource",
  "directory": "/data/tables"
}
```

默认直接使用读到的 `tag.json`。需要改写 tag 时，在子类里实现 `extract_tag(name, content, tag)`；要改变哪些实体目录被收成记录，实现 `include(path)`，`path` 是那个实体目录。

### FilteredDirectorySource

本 function 读取与 `DirectorySource` 相同的实体目录，在收成记录之前按规则留下一部分。实体名、正文和默认 tag 的规则与上一节相同。

`type` 为 `source`，`class` 为 `docorder.functions.impl.directory_source:FilteredDirectorySource`，`directory` 的含义与上一节相同。筛选规则写在参数 `filter` 里，它是一个对象，可以写在 `props.json`，也可以由节点 `config` 覆盖。

`disabled_suffix` 列出禁止的结尾，实体目录名以其中任一项结尾时，该目录不产生实体。值可以是一个字符串，或一个字符串列表。`enabled_suffix` 列出允许的结尾，形式相同；没有这一项时，未被禁用的实体目录都产生实体，有这一项时，只保留名字以其中某项结尾的目录。`min_size` 与 `max_size` 是包含边界的字节数，针对的是 `data` 文件；可以只写其中一项；下限大于上限时，配置无效。

判定顺序是：先排除禁用后缀，再按允许后缀保留，最后按 `data` 文件大小保留。排除备份名、并限制正文体积时，home 可以写成：

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

## 五、map function

五个 map function 都为上游的每个实体写出一个同名实体。

### TemplateToPrompt

本 function 为每个上游实体渲染一份 home 里的 Jinja 模板，结果成为该实体的正文。模板文件由算子提供，上游正文不是模板，而是以变量 `data` 进入模板。tag 是上游 tag 的副本。

`type` 为 `map`，`class` 为 `docorder.functions.impl.template_to_prompt:TemplateToPrompt`。参数 `template` 是 home 内的相对路径，例如 `lib/prompt.jinja`。模板使用铺平命名空间。引用了不存在的变量时，该实体失败，并且不重试，因为模板本身缺少这次渲染需要的变量，再渲染一次也一样。

### JinjaToJsonnet

本 function 用 home 里的 Jinja 模板和上游实体携带的 JSON，生成一份 jsonnet 源文。上游正文必须是一个 JSON 对象，对象的键就是模板变量。输出正文是渲染结果。tag 默认为空对象；要把特性交给下游，在子类里实现 `generate_props`。子类还可以实现 `template_text`，由代码提供模板全文，此时可以不配置 `template`。

`type` 为 `map`，`class` 为 `docorder.functions.impl.jinja_to_jsonnet:JinjaToJsonnet`。`template` 是 home 内的模板路径。`variables` 是可选的默认变量对象，上游 JSON 里的同名键覆盖它。上游正文为空、不是 JSON 对象，或渲染结果只有空白时，该实体失败。

### JsonnetToPrompt

本 function 把上游正文当作 jsonnet 程序，调用本机的 `jsonnet -` 编译。程序经标准输入交给编译器，标准输出成为新正文。tag 沿用上游。程序文本不做模板替换。`import` 与 `importstr` 使用程序里已经写好的路径；库文件放在算子 home 里时，程序里应写它的绝对路径，可以在上游的模板步骤里用 `operator.home` 拼出来。

`type` 为 `map`，`class` 为 `docorder.functions.impl.jsonnet_to_prompt:JsonnetToPrompt`。本 function 没有自己的参数。`PATH` 上需要有 `jsonnet`。

### Command

本 function 对每个上游实体执行一条外部命令。命令不经过 shell，`argv` 原样作为进程参数。`argv` 的每一项以及可选的 `output_file` 都按铺平命名空间替换，写法为 `{键}` 或点路径，例如 `{operator.home}`。tag 沿用上游，并增加 `command`，值是替换后实际执行的参数用空格连起来的结果；配置了 `output_file` 时，tag 里还有替换后的 `output_file`。

`type` 为 `map`，`class` 为 `docorder.functions.impl.command:Command`。

`argv` 是命令和参数，至少一项。`cwd` 是命令的工作目录，原样使用，不做花括号替换；省略时使用 Python 进程的当前目录。`output_file` 是命令应当写出的文件，执行前会创建它的父目录。`output_file` 为相对路径时，docorder 按 Python 进程的当前目录找它，与 `cwd` 无关，所以宜写成绝对路径，或写成 `{entity.output}/文件名`。

`capture` 决定正文从哪里来。`file` 读取 `output_file`，命令结束后这份文件必须存在；`stdout` 用标准输出；`none` 让正文为空字符串。不写 `capture` 时，配置了 `output_file` 就是 `file`，否则是 `stdout`。正文为空的实体，下游每次运行都会重做它，原因见 [design.md](design.md) 第四章。

命令拿不到上游正文，除非把 `{data}` 写进某个参数。下面的配置接在 `DirectorySource` 之后，对每个源实体的 `data` 文件统计行数。`{name}` 是实体名，`/data/notes` 应与 source 的 `directory` 相同：

```json
{
  "type": "map",
  "class": "docorder.functions.impl.command:Command",
  "argv": ["wc", "-l", "/data/notes/{name}/data"]
}
```

`argv` 用了 `sh -c` 这类 shell 时，替换进去的 tag 值和正文会被当作 shell 代码执行。只对受信任的输入这样写。

### PromptToLLM

本 function 把上游正文当作 prompt，交给一个命令行工具。tag 沿用上游。prompt 不做模板替换。

工具返回之后，如果目标实体目录里已经有 `data` 文件，就表示工具自己把正文写到了磁盘。这份文件必须是非空的 UTF-8 文本，否则这次调用失败，并按 `retry` 重试。检查通过后不再改写 `data`，只补上 `tag.json`。没有这份文件时，正文仍是工具的标准输出。调用开始前若目录里已有 `data`，会先删掉，避免把上一次失败留下的文件当成这次的结果。

`type` 为 `map`，`class` 为 `docorder.functions.impl.prompt_to_llm:PromptToLLM`。

`workspace` 是工具的工作目录，必须配置，并且在运行前已经存在；相对路径按 Python 进程的当前目录解析。工具进程的当前目录就是它，工具参数里的 `{workspace}` 会换成这个路径。

`tool` 指定工具，有三种写法。写一个名字时，先找 home 里的 `tools/<名字>.json`；没有这份文件，再把这个字符串当作 JSON 文件路径读取。写一个对象时，直接在参数里给出工具定义。没有配置 `tool` 时，使用环境变量 `DOCORDER_LLM` 的值，按名字或文件路径解释。两处都没有时，该实体失败。包里不附带任何预设，`tools/` 里的文件由使用者自己写。

工具定义是一个 JSON 对象。`run` 是非空的字符串数组，即要执行的命令和参数。`prompt` 取 `stdin` 或 `arg`：`stdin` 把正文写进进程的标准输入，`arg` 把正文追加为最后一个参数；不写时按 `stdin`。`name` 可选，只用于错误信息。

```json
{
  "name": "my-llm",
  "run": ["my-llm-cli", "--cwd", "{workspace}"],
  "prompt": "stdin"
}
```

上面这份定义放在 home 的 `tools/my-llm.json` 里时，`props.json` 写 `"tool": "my-llm"` 即可。`my-llm-cli` 只是占位名，换成你本机实际使用的命令。

### Output

`Output` 把上游本 epoch 每个实体的正文写成作业结果目录里的一个文件。缺省目录是作业根目录下的 `.job_result`；参数 `directory` 可以换成别的路径，相对路径相对算子 home 解析。它不产生给下游读的实体。`type` 为 `output`，`class` 为 `docorder.functions.impl.output:Output`。

文件名缺省是实体名。参数 `name_template` 是一段 Jinja 模板，用该实体的 tag 渲染后作为文件名，例如 `{{ table }}.sql`。渲染结果必须是一层文件名，不能含 `/` 或 `\`，也不能是空的。两个实体得到同一个文件名时，这一段以 `FatalError` 失败。这个节点上次写出、这次不再产生的文件会被删掉。

```json
{
  "type": "output",
  "class": "docorder.functions.impl.output:Output",
  "directory": "/data/out",
  "name_template": "{{ table }}.sql"
}
```

## 六、在 home 里实现 function

### 选哪个基类

现成的 function 表达不了某种转换时，在 home 的 `primary.py` 里写一个类，`props.json` 的 `class` 写成 `primary:类名`。基类由 `type` 决定，都在 `docorder.functions` 下。

`SourceFunction` 实现 `emit()`，逐条 `yield SourceRecord(name, data, tag)`。`MapFunction` 与 `FanoutFunction` 实现 `transform_data(source, target)` 和 `transform_props(source, target)`，参数是一个上游实体和一个目标实体。`ReduceFunction` 也实现这两个方法，但第一个参数是本段全部上游实体组成的列表。`FanoutFunction` 另有 `output_names(source)`，返回这个上游实体要产生的输出名列表，缺省只返回上游实体自己的名字。要做逐实体渲染的 map，可以继承 `docorder.functions.rendered_map:RenderedMap`，只实现 `apply_render`。

### function 要遵守的约定

`transform_data` 必须把 `target.staging_data` 设成字符串，`transform_props` 必须把 `target.tag` 设成字典，否则这个实体以 `FatalError` 失败。如果调用期间目标目录里已经有 `data` 文件，可以不设 `staging_data`，runner 会保留该文件，只写 `tag.json`。读上游正文用 `source.read_text()`，读上游 tag 用 `source.tag`；`self.environment.operator_props` 是合并后的参数。function 不写快照，也不自己重试或开线程池，这些由 runner 完成。

runner 每处理一个实体、每尝试一次，都会重新构造 function 实例，实例上的属性不会带到下一个实体。`output_names` 在主进程里被调用，一次运行中可能不止调用一次，它的返回值应只取决于传入的上游实体。配置错误这类重试也无济于事的问题，抛 `docorder.utils.errors.FatalError`；可能自行恢复的问题，抛其它异常，交给 `retry`。

### 例子：reduce

下面的 reduce 把上游全部实体的正文拼成一个实体。`output` 是 reduce 算子的保留参数，决定唯一那个输出实体的名字，缺省为 `result`。

`homes/join/props.json`：

```json
{
  "type": "reduce",
  "class": "primary:JoinBodies",
  "output": "all",
  "separator": "\n---\n"
}
```

`homes/join/primary.py`：

```python
from docorder.functions.reduce_function import ReduceFunction


class JoinBodies(ReduceFunction):
    def transform_data(self, sources, target):
        separator = self.environment.operator_props.get("separator", "\n")
        target.staging_data = separator.join(entity.read_text() for entity in sources)

    def transform_props(self, sources, target):
        target.tag = {"count": len(sources), "names": [entity.name for entity in sources]}
```

上游有 `a`、`b` 两个实体时，输出是 `<epoch>/all/`，正文为两段正文中间夹着 `---`，tag 为 `{"count": 2, "names": ["a", "b"]}`。上游任一实体正文变化，或实体增减，`all` 都会重做。上游一个实体都没有时，reduce 仍会写出 `all`，此时 function 收到空列表。

### 例子：fanout

下面的 fanout 把上游正文按行拆开，每一行成为一个实体，名字是 `<上游实体名>-<行号>`。

`homes/lines/props.json`：

```json
{
  "type": "fanout",
  "class": "primary:SplitLines"
}
```

`homes/lines/primary.py`：

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

上游实体 `hello` 的正文有两行时，输出是 `hello-0` 和 `hello-1`。所有上游实体产生的输出名在整段里必须互不相同，否则这一段以 `OperatorValidationError` 失败。每个输出只依赖一个上游实体，因此 fanout 和 map 一样按 `parallelism` 切分到多个进程。

要在 README 的快速开始上试这两个例子，把 `join/`、`lines/` 两个 home 放进 `quickstart/homes/`，再在 `main()` 里 `execute` 之前加两行：

```python
job.add_operator_node("joined", "join", upstream="notes")
job.add_operator_node("parts", "lines", upstream="notes")
```

## 附录：类名

配置 `class` 时使用下表的写法。内置实现在 `src/docorder/functions/impl/` 下。

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

基类：`docorder.functions.source_function:SourceFunction`、`docorder.functions.map_function:MapFunction`、`docorder.functions.reduce_function:ReduceFunction`、`docorder.functions.fanout_function:FanoutFunction`、`docorder.functions.output_function:OutputFunction`、`docorder.functions.rendered_map:RenderedMap`。

# 设计

[English](design.en.md)

docorder 把一批结构相同的目录实体沿作业图逐段转换，并把进度记在每个实体自己的目录里。本文讲调度这一层：实体、算子、作业各自保存什么状态；一次运行在磁盘上写下哪些文件、按什么顺序写；runner 怎样决定每个实体是执行、重做、留下还是删除；失败和重试之后，磁盘停在什么状态。

每个 function 的参数和模板变量见 [functions.md](functions.md)，安装和第一次运行见 [README](../README.md)，本文不重复。

本版有两条贯穿全文的边界。第一，按 stage 执行：一个算子处理完本 epoch 的整批实体，它的下游才开始；某个实体刚写完就启动下游，不在本版里。第二，一个节点只有一个上游，图是一棵棵以 source 为根的树。

第一次读时，建议按章节顺序读：第一章建立三个概念，第二章看磁盘布局，第三章按时间顺序走一遍运行，第四章把再跑时的判定集中起来，第五章用一个两段作业把前面串起来。第六章写给要自己实现转换的人。

## 文档结构

1. 实体、算子、作业各自持有的状态，以及三者如何分开。
2. 一次 epoch 的目录布局、输出目录标记和一个实体的写出顺序。
3. 一次运行从装配到逐个 stage 的经过：应得名单、与磁盘比较、清场、填写、并行和重试，以及 source 的另一条路径。
4. 同一 epoch 再跑时，每种情况下实体的去向。
5. 用一个两段作业串起三次运行。
6. 增加一种转换时，哪些职责留在 runner。

文中有四处结构说明：`tag.json` 里 `upstream` 一条记录的字段，算子 home 的字段归属，一次运行的目录布局，以及两段作业里实体之间的对应关系。

## 一、实体、算子与作业

实体、算子和作业分开持有状态。实体记住「这个对象这次读过哪些上游正文」。算子记住「这是哪一种转换、用哪个类、默认参数是什么」。作业记住「这一次把哪些转换连起来、写到哪里」。三者的生命周期不同：实体随 epoch 留在磁盘上，算子 home 被许多作业复用，作业对象只活在一次 Python 进程里。正因为进度在实体目录里，换一个进程、甚至换一份作业脚本，只要输出路径和 epoch 相同，都能接着上一次的进度跑。

### 实体

#### 名字与识别

实体是一次转换的一个对象。在磁盘上，它是某个节点输出目录下、某一 epoch 子目录中的一层子目录，目录名就是实体名。名字必须是一层可见的目录段：非空，去掉首尾空白后与原文相同，不含 `/` 或 `\`，不是 `.` 或 `..`，也不以 `.` 或 `_` 开头。以这两个字符开头的名字留给标记和运行时文件，下一个算子不会把它们当作输入。

一个子目录要被认成实体，里面要有 `data` 或 `tag.json`。空目录、名字不合规的目录，以及更深一层的目录，都不是实体。

#### 正文与 tag

`data` 是正文，按 UTF-8 文本读写。它的含义随算子变化：目录 source 里是源文件原文，模板算子里是渲染结果，命令算子里是命令的输出。调度只要求它是字符串，不解释其中的格式。

`tag.json` 是一个 JSON 对象，给下游过滤和填模板用。tag 的键由 function 决定。runner 另外管理 `upstream` 和 `global_prop`。

下游实体会带上上游的整份 tag，里面已经有上游的 `upstream`，也可能带着旧文件里残留的 `current`。写出前 runner 一定重置这两个键：丢掉 `current`，把 `upstream` 改成直接上游实体此刻的快照（只有一个上游时是这条记录，没有或多个上游时是这些记录组成的列表）。function 写在这两个键上的值会被换掉。source 没有上游，不写 `upstream`，也丢掉 `current`。

`global_prop` 在同一时刻合并：写出 map、fanout 或 reduce 的目标前，runner 把上游 tag 里的 `global_prop` 对象合并到目标的 `global_prop` 上。目标自己写下的同名键保留；reduce 有多个上游实体时，按实体名排序，排在后面的覆盖前面的。`tag.json` 读不出来或不是对象时，这个实体被视为无效，在下一次比较里重做。

#### 上游快照

快照写在 `tag.json` 的 `upstream` 键里。一个上游时是一条记录，没有或多个上游时是记录组成的列表。每条记录有四个字符串字段。

```text
tag.json  "upstream"
  { operator, name, epoch, hash }
  或 [ { operator, name, epoch, hash }, ... ]
```

`operator` 是上游节点名，`name` 是读过的上游实体名，`epoch` 是读取时的 epoch，`hash` 是那份上游实体的正文连同用户 tag（不含 `upstream` 和残留的 `current`）算出的 sha256，写成十六进制。map 与 fanout 的快照是一条记录，reduce 的快照是本次参与的每一个上游实体。一个实体的全部记录必须属于同一个上游节点。值不是记录或记录列表、字段不是字符串，或出现了两个节点名时，这份快照无效。

快照覆盖上游的正文和用户 tag。手动改上游实体的 `data` 或 `tag.json`，下一次运行会让依赖它的下游重做。本算子的参数或模板变了、function 的代码变了，都不会让快照失配。

source 没有上游，不写 `upstream`。写出实体时，目录里若留着旧的 `upstream.json`，会被删掉。

#### 完成的含义

有上游的实体，以 `tag.json` 里的 `upstream` 成功写下、并且与当前上游吻合为完成。正文可以先出现，tag 里没有这份快照就不算完成，下次同一 epoch 会再做它。上游正文为空字符串，或读不出来时，快照里的哈希是空字符串；空哈希永远通不过比较，所以上游正文为空的实体每次都会重做。

实体目录供调度使用，不代替调用方自己的源文件。源文件留在原处，由 source 在需要时再读一次。

### 算子

#### home 与查找

算子是可复用的转换，不记录某一次运行的输出路径。它的静态文件放在算子 home 里。包内不附带 home，调用方把 home 放在环境变量 `DOCORDER_HOMES` 列出的目录里；分隔符与 `PATH` 相同，靠前的目录优先。home 可以直接放在某个列出的目录下，也可以放在其下一层分类目录中，名字以 `.` 或 `_` 开头的分类目录被跳过。识别一个 home，看目录里有没有 `props.json`。

查找发生在 `add_operator_node` 被调用的那一刻。环境变量要在此之前设好；找不到时抛出 `FileNotFoundError`，信息里列出搜过的目录。

#### props.json 的字段归属

```text
props.json
  type, class                 身份。作业不能改
  parallelism, retry          调度。作业添加节点时用同名参数覆盖
  其余键                      function 参数。节点的 config 覆盖同名键
```

`type` 取 `source`、`map`、`reduce`、`fanout`、`output` 之一。前四种决定上游实体和输出实体如何对应；`output` 不写实体，把上游本 epoch 的正文写成作业结果文件。`class` 是要加载的 function，写成 `模块:类名`，或写成 `primary:类名` 以加载 home 自己的 `primary.py`。`props.json` 不是对象、`class` 不是带冒号的字符串，或 `type` 不在五种之内时，`add_operator_node` 以 `JobValidationError` 失败。

`parallelism` 缺省为 1。`retry` 是对象，含 `max_attempts` 与 `backoff_seconds`，前者缺省为 1 且不能小于 1，后者缺省为 0。

home 里还可以有 `lib/`、`tools/` 等目录，放随算子分发的模板和工具定义。这些文件属于算子，不属于某一次作业的输出。

#### 五种类型

五种类型都遵守「一个节点只有一个上游」。前四种的差别在于输出名从哪里来、每个输出依赖哪些上游实体。`output` 不写实体。

source 没有上游。function 用 `emit` 逐条交出记录，每条带有实体名、正文和 tag。

map 为上游的每个实体写出一个同名实体。function 收到一个上游实体和一个尚未写入正文的目标。

reduce 把上游整批收成一个实体。实体名取 function 参数 `output`，缺省为 `result`。function 收到上游实体组成的列表和这一个目标。

fanout 把上游的一个实体拆成多个。function 的 `output_names` 列出这个上游实体要产生的输出名，缺省只返回上游实体自己的名字；所有上游实体产生的输出名在整段里必须互不相同。function 再为每个输出收到产生它的那个上游实体和目标。

output 读取上游本 epoch 的全部实体，把每个实体的正文写成作业结果目录里的一个文件。缺省目录是作业根目录下的 `.job_result`；参数 `directory` 可以换成别的路径，相对路径相对算子 home 解析。文件名缺省是实体名；参数 `name_template` 存在时，用该实体的 tag 渲染模板得到文件名。文件名必须是一层文件名。两个实体得到同一个文件名时，这一段以 `FatalError` 失败。上次由这个节点写出、这次不再产生的文件会被删掉。作业结果目录是作业整体的输出，不是某个节点的 epoch 实体目录。

map 与 fanout 的每个输出只依赖一个上游实体，因此可以按实体切分到多个进程。reduce 的那一个输出依赖上游全部实体，只在当前进程里写一次。output 按上游实体逐个写文件，不切分。

### 作业

#### 节点与输出路径

作业是一张有向无环图。`Job(name, root)` 给出作业名和输出根目录。`add_operator_node(name, home, upstream=..., config=..., parallelism=..., retry=...)` 加入一个节点：除 source 以外要给出唯一上游的节点名，`upstream` 写成列表或元组会被拒绝。节点的输出路径由作业决定，是 `输出根/节点名`，不写进 home。节点名直接拼进路径，不做实体名那样的检查。

同一个节点名再次添加时，后一次替换前一次，不报错。

#### config 的合并

节点构造时，把传入的 `config` 覆盖到 home 的 function 参数上，写进 `props`。其中的 `class` 被丢掉，不能用来更换 function。构造完成之后节点不再保留 `config`，对外只暴露 `props`。`parallelism`、`retry` 写进 `config` 只会成为 function 参数，调度仍按 home 里的值，或 `add_operator_node` 的同名参数。

作业图装配时，`Operator.of` 把节点上的公开字段（`name`、`props`、`type`、`operator_home`、`output_path`、`upstream`）抬到算子上。此后 runner、function 和模板环境都读算子，不再经过节点。节点只用于作业图的声明、校验和拓扑序。

并行度大于 1、待写的实体多于一个时，map 和 fanout 在线程里分片执行。线程共享当前进程的内存，参数不必能被 pickle。

合并后的参数在 `props` 上，既是 function 读到的参数，也是模板里算子视图的底；那份视图如何组成，见 [functions.md](functions.md)。

#### 校验与执行顺序

`execute` 开始时先校验作业图，并拒绝这些情况：图中有环，上游名字不在图中，节点依赖自己，两个节点的输出路径解析后相同，以及两个输出路径互为祖先。后两种情况可以由符号链接或带 `/` 的节点名造成。

执行顺序是拓扑序。几个节点同时可以执行时，先加入作业的先执行。

## 二、一次 epoch 的磁盘布局

### 目录树

```text
<输出根>/
  .job_result/              作业整体输出。output 节点写入
    <文件名>                内容是上游实体的正文
  <节点名>/
    .docorder-output        输出目录标记
    <epoch>/
      <实体名>/
        data
        tag.json            有上游时含 upstream 快照
    <另一个 epoch>/
      ...
```

### epoch

epoch 是调用方传给 `execute` 的名字，也是实体所在的那层子目录名。同一次运行里，每个节点的输出都使用这个 epoch，快照里记下的 epoch 也是它。换一个 epoch 就是换一套子目录：新 epoch 从空目录开始，旧 epoch 的实体留在原处，runner 既不读它们，也不清理它们。快照里记录的 epoch 与本次不同时，该实体要重做。

runner 不检查 epoch 名，直接拼进路径。`2026/10` 这样的名字会建出两层目录，应传一层目录名，例如日期或版本号。

### 输出目录标记

每个 stage 开始时，runner 先检查这个节点的输出目录。目录已经存在、里面有内容、却没有 `.docorder-output` 时，运行以 `FatalError` 停下，以免把别人的目录当成输出清理掉。检查通过后，runner 创建目录并写下标记。标记以 `.` 开头，不会被当成实体。这项检查在每个节点自己的 stage 开始时才做，所以前面的节点可能已经执行完毕。

### 一个实体的写出顺序

一次成功的写出按固定顺序落盘。先保证实体目录存在，再写正文（本次确实产生了正文时），然后写 `tag.json`。每份文件都先写到同目录的 `.tmp` 临时文件，再替换正式文件，所以单个文件不会只写一半。目录里若留着旧的 `upstream.json`，写出后会删掉。

这个顺序把「完成」定义在 `tag.json` 里的快照上。进程若死在正文和 tag 之间，目录里可以已经有新正文，却没有有效快照；下次比较把它当作未完成，重做并覆盖。

## 三、一次运行

`execute(job, epoch, start_from_scratch=False)` 的经过分两部分：先装配整张图，再按拓扑序逐个执行 stage。上一个 stage 抛出异常时，运行就此停下，后面的节点不会开始。

### 装配

装配先校验作业图，再为每个节点加载 function 类，并构造一次 function 实例。类找不到、不是该 `type` 的基类子类，或还有没实现的抽象方法时，运行以 `OperatorValidationError` 失败。这发生在任何 stage 之前，所以最后一个节点的类名写错，也不会让前面的节点白跑。

装配还为每个输出目录建立一份本 epoch 的实体表。同一个目录在一次运行里只有一份表，节点写出时更新它，下游把它当作上游来读。

### 准备一个 stage

#### 应得名单

除 source 以外，每个 stage 先重新读取上游在本 epoch 已有的实体，建立应得名单，即「输出名 → 它依赖的上游实体名」。

map 的名单是上游每个实体名指向它自己。fanout 的名单由 `output_names` 展开，每个输出名指向产生它的那个上游实体；`output_names` 在主进程里调用，一次运行中会被调用不止一次。reduce 的名单总是恰好一项：输出名指向上游全部实体名，上游为空时就是一个空列表。source 的名单为空，因为它的输入是 function，不是另一个节点的目录。

名单为空时，这个 stage 不做比较、不删除，也不调用 function，该 epoch 里已有的实体保持原样。对 map 和 fanout 来说，上游一个实体都没有时就是这种情况；reduce 的名单不会为空，上游为空时它仍会写出那一个实体，function 收到空列表。

#### 与磁盘比较

名单非空时，runner 重新读取本节点在该 epoch 的实体，分成三类。

名单里有、目录里没有的名字，要新建。目录里有、名单里没有的实体，要删除。两边都有的实体，拿它的 `tag.json` 里的 `upstream` 和当前上游比较，任一条不满足就要重做：快照存在且有效；记录里的名字集合与名单一致，且没有重复；每条记录的节点名是这次的上游；每条记录的 epoch 是本次 epoch；每条记录的哈希非空，且等于当前上游实体正文与用户 tag 的哈希。实体自己的 `tag.json` 无效时，也要重做。比较通过的实体留在原处，本段不再为它调用 function。

#### 清场

比较之后、调用任何 function 之前，runner 一次性整理目录：删除要删除的实体目录；删除要重做的实体目录；再为每个要新建和要重做的名字放一个只有空 `tag.json` 的目录。待写名单是新建的名字（按名字排序），再接上重做的名字（按名字排序）。

清场覆盖整段，而不是逐个实体进行。因此本段一旦开始执行，所有要重做的实体都已经失去旧正文；若本段中途失败，还没轮到的实体停在只有空 `tag.json` 的状态，直到下一次运行把它们写完。

### 执行一个 stage

#### 填写与快照

map 和 fanout 对每个待写名字调用一次 function：先 `transform_data` 填正文，再 `transform_props` 填 tag。两者必须分别是字符串和对象，否则这个实体以 `FatalError` 失败。runner 随后合并 `global_prop`，丢掉 `current`，按上游实体此刻的正文和用户 tag 算出快照写入 `upstream`，然后按第二章的顺序写出。reduce 对那一个输出做同样的事，快照包含参与的每一个上游实体。source 写出时丢掉 `current`，不写 `upstream`。

function 不写快照。上游实体没有 `data` 文件时，例如上游上一次停在半路只留下空目录，这次调用以 `FatalError` 失败。正常顺序下这不会发生，因为上游的 stage 会先把它补完。

runner 为每个实体的每次尝试重新构造 function 实例，实例状态不会从一个实体带到下一个。

#### 分片与线程

map 和 fanout 把待写名单按 `parallelism` 切成连续的若干片，片数不超过并行度，也不超过名字的个数。只有一片时，在当前线程里顺序写；多于一片时，每片一个工作线程，片内仍然顺序执行。这些线程共享算子和 function 参数。reduce 不切分。`parallelism` 小于 1 时，这一段在有待写名字时以 `OperatorValidationError` 失败。

工作线程由 Python 的 `ThreadPoolExecutor` 启动，不另起进程，也不要求启动脚本写 `if __name__ == "__main__":`。

一片里有实体最终失败时，这片里排在它后面的实体不再尝试；其它片照常跑完，异常在所有片结束后才传出。所以并行失败之后，磁盘上已完成的实体可能不止失败点之前的那几个。

#### 重试

单个实体的调用按 `retry` 执行。抛出 `FatalError` 时不重试，这一段立即失败。其它异常，包括外部进程返回非零状态，会在等待 `backoff_seconds × 已尝试次数` 秒后再试，直到用满 `max_attempts` 次。最后一次仍失败时，异常传出这个 stage，运行停在当前节点。

已经在本段写好 `tag.json` 里 `upstream` 的实体留在目录里。用同一个作业和同一个 epoch 再跑，这些实体比较通过、直接留下，runner 只写剩下的，以及上游又变了的。

### source 的 stage

source 不建立应得名单，也不做上面的比较。它是否重写，只看这次运行有没有传 `start_from_scratch=True`。

没有传时，source 不调用 function，也不改动自己的输出目录，只确保目录和标记存在。下游读取这个路径上已经存在的实体。第一次运行就不传的话，下游看到的是一个空 epoch：map 和 fanout 什么也不做，reduce 写出一个空输入的结果。

传了时，runner 逐条读取 `emit` 交出的记录，每读到一条就写成实体：实体名必须合规，正文必须是字符串，tag 必须是对象，不写快照。同一个名字交出两次，这一段以 `OperatorValidationError` 失败。source 写实体时直接覆盖 `data` 和 `tag.json`，不先清空实体目录。全部交完之后，本 epoch 里这次没有交出的名字被删除，于是目录里的实体与本次交出的记录一致。

source 的 `retry` 只包住「把一条记录写到磁盘」这一步。`emit` 本身抛出的异常，例如源文件不是 UTF-8，不重试，直接让这一段失败。此时已经交出的记录已经写下，这次还没交出的旧实体不会被删除；下一次从头生成时会恢复一致。

## 四、同一 epoch 再跑

再跑时，runner 对每个非 source 节点都做一遍第三章的比较。把各种情况放在一起：

| 情况 | 本段对这个实体 |
| --- | --- |
| 名单里有，目录里没有 | 新建并执行 |
| 目录里有，名单里没有 | 删除整个实体目录 |
| 两边都有，快照与当前上游吻合 | 留下，不调用 function |
| 两边都有，没有快照、快照无效或 tag 无效 | 清空后重做 |
| 两边都有，上游名字集合、节点、epoch 或实体哈希不一致 | 清空后重做 |
| map、fanout 的上游没有任何实体 | 不比较，目录保持原样 |
| reduce 的上游没有任何实体 | 照常比较，function 收到空列表 |

几种常见的再跑场景可以由这张表推出。

#### 上一次停在半路

失败那一段里已经写好快照的实体会留下；只有空 `tag.json`、还没有快照的实体会重做；失败节点的下游上一次根本没开始，这次从头执行。失败节点之前的非 source 节点，只要上游没变，实体都比较通过，不会重新调用 function。

#### 上游实体变了

上游实体的正文或用户 tag 变了，依赖它们的下游实体会重做。重做的实体若写出与上次相同的正文和用户 tag，它的下游比较通过，重做就在这里停住；否则继续沿图向下传播。对 reduce 来说，上游任何一个实体的正文或用户 tag 变化、新增或消失，都会让那一个输出重做。不传 `start_from_scratch` 时，也可以直接改已经写出的上游实体目录里的 `data` 或 `tag.json`，下游会在下一次运行时重做。

#### 上游实体增减

上游新出现的实体，在 map 下游表现为新建；上游消失的实体，在 map 下游表现为删除。唯一的例外是上游一个实体都不剩：map 与 fanout 的名单为空，下游目录保持原样，不会因此被清空。

#### 算子本身变了

模板、参数、function 代码或外部工具变了，而上游实体没变时，快照仍然吻合，旧结果会被留下。要让新逻辑生效，删除该节点的 `<epoch>/` 目录或其中的某些实体目录，或者换一个 epoch。只删掉某个实体 `tag.json` 里的 `upstream` 也能让它重做，且保留目录给人查看，直到重做开始。

#### source 不从头生成

不传 `start_from_scratch=True` 时，源文件的改动不会进入 source 的实体，下游自然也看不到。只有传了它，source 才重读输入，变化才从图的根部开始传播。

## 五、端到端：一个两段作业

用 README 快速开始里的作业：source 节点 `notes` 读取一个目录，map 节点 `prompt` 用模板 `Note: {{ data }}` 渲染每个实体，epoch 为 `demo`。目录里只有实体 `hello`，其 `data` 内容是 `hello`。

```text
runs/notes/demo/hello/                 runs/prompt/demo/hello/
  data       "hello\n"                    data           "Note: hello\n"
  tag.json   输入实体的 tag               tag.json       上游 tag 的副本，
                                                         含 upstream:
                                                           { operator: "notes",
                                                             name: "hello",
                                                             epoch: "demo",
                                                             hash: 正文与用户 tag }
```

第一次运行传了 `start_from_scratch=True`。装配阶段加载两个 function 类。`notes` 的 stage 检查并创建输出目录、写下标记，再把输入目录里的实体 `hello` 写成输出实体，不写快照。`prompt` 的 stage 读取上游，得到名单 `hello → [hello]`；本节点目录是空的，于是 `hello` 被新建，放一个空 `tag.json`，渲染之后依次写下正文、tag 和指向 `notes/hello` 的快照。

随后把输入实体 `hello` 的 `data` 改成 `changed`，第二次运行不传 `start_from_scratch`。`notes` 的 stage 不调用 function，实体 `hello` 仍是旧正文。`prompt` 的 stage 比较快照：节点名、实体名、epoch 和哈希都与上游吻合，于是留下 `prompt/demo/hello`，不调用 function。输出仍是 `Note: hello`。

第三次运行传了 `start_from_scratch=True`。`notes` 重读目录，把 `hello` 的正文覆盖为 `changed\n`。`prompt` 比较时发现哈希不一致，清场时删掉旧目录、放回空 `tag.json`，再渲染出 `Note: changed` 并写下新快照。

如果在第三次运行之前，把输入实体 `hello` 改名为 `bye`，`notes` 会写出 `bye`、删除 `hello`；`prompt` 的名单变成 `bye → [bye]`，于是新建 `bye`、删除 `hello`。如果直接清空源目录，`notes` 会删除 `hello`，而 `prompt` 的名单为空，`prompt/demo/hello` 保持原样。

## 六、增加一种转换

包内现成的 function 覆盖两类工作：从目录产生实体，以及对已有实体逐个做 map。reduce 和 fanout 只有基类，需要时在算子 home 里实现；[functions.md](functions.md) 的第六章有两份可以直接运行的例子。

新的转换仍然是「一批对象，每个对象一次调用」时，继承 map 的基类，实现 `transform_data` 与 `transform_props`，在 `props.json` 里写上 `type` 和 `class`。随算子分发的文件放在 home 内。一次调用只处理传入的上游实体和它的目标，把正文和 tag 交给 runner 落盘。线程池、重试、清场和快照都由 runner 按 home 里的调度字段完成，function 里不必再做一套。

function 里要区分两类失败。配置缺失、输入格式不对这类再试也不会好的问题，抛 `FatalError`，让这一段立即停下；网络、外部进程这类可能自行恢复的问题，抛其它异常，交给 `retry`。

一种转换要读两路结果时，本版的节点不能声明两个上游。调用方可以先用一个算子把两路收成一路；也可以在 function 里直接读取另一路已经写下的文件。后一种读法不进入快照，那份文件变化时，runner 不会因为快照而重做这个实体。

## 附录 A：实现索引

| 路径 | 职责 |
| --- | --- |
| `src/docorder/core/artifact.py` | 算子 home 的只读文件入口 |
| `src/docorder/core/entity.py` | 实体名检查，实体目录的读写，快照与比较 |
| `src/docorder/core/environment.py` | function 参数与模板变量 |
| `src/docorder/core/storage.py` | 一个 epoch 目录里的实体表，以及新建、清场、删除 |
| `src/docorder/core/operator.py` | home 契约，节点，应得名单，五种算子的一次执行，分片 |
| `src/docorder/core/job.py` | 作业图、校验与拓扑序 |
| `src/docorder/core/runner.py` | 装配，按 stage 执行，输出目录标记 |
| `src/docorder/utils/retry.py` | 重试策略，以及它如何作用到一次实体调用 |
| `src/docorder/utils/paths.py` | `DOCORDER_HOMES` 与 home 查找 |
| `src/docorder/utils/modules.py` | 加载 `primary:类名` 与 `模块:类名` |
| `src/docorder/functions/` | function 基类；内置实现在 `functions/impl/` |
| `tests/test_contract.py` | 上述行为的契约测试 |

## 附录 B：延伸阅读

- [concurrent.futures.ThreadPoolExecutor](https://docs.python.org/3/library/concurrent.futures.html#threadpoolexecutor)：map 与 fanout 的分片所用的线程池。

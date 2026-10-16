# 参与贡献

[English](CONTRIBUTING.en.md)

## 环境

需要 Python 3.10 以上和 [uv](https://docs.astral.sh/uv/)。要用 `JsonnetToPrompt` 时，再安装 `jsonnet` 可执行文件。

```bash
uv sync --group dev
uv run ruff check
uv run pytest
```

`tests/test_contract.py` 是调度行为的契约测试。改动实体、比较、清场、重试或 source 的行为时，先在这里补用例。`make quality` 和 CI 还会运行 `examples/` 下的脚本，这些脚本目前不在仓库中。

## 改哪里

运行时在 `src/docorder/`。`core/` 是实体、作业、算子和 stage 调度。`functions/` 是 source、map、reduce、fanout 基类。内置实现在 `functions/impl/`。`utils/` 是错误、模块加载、home 搜索和重试。

算子 home 放在 `DOCORDER_HOMES` 指向的目录里，不打进安装包。路径分隔符与 `PATH` 相同，靠前的目录优先。新的转换优先复用已有 function。现有类型表达不了时，在 home 的 `primary.py` 里实现与 `props.json` 的 `type` 对应的 function 基类，并把 `class` 写成 `primary:类名`。重试和线程池由 runner 负责，不要在 function 里再做一套。写法见 [docs/functions.md](docs/functions.md) 第六章。

## 提交

贡献以 [MIT 许可](LICENSE) 发布。提交说明写清原因。不要提交密钥、访问令牌、`runs/` 或真实业务数据。

行为变更记入 `CHANGELOG.md` 的 Unreleased 小节。文档改动同时改中文和同名的 `.en` 文件。文档里的命令和示例代码，提交前在本机实际跑一遍。

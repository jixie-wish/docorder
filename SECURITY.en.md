# Security

[中文](SECURITY.md)

This project starts processes on the local machine. `JsonnetToPrompt` calls `jsonnet` to compile upstream bodies. `Command` runs the `argv` from the job configuration. `PromptToLLM` runs the `run` array from a tool definition and hands it the upstream body. These processes run as the user who runs the job, and can read and write any file that user can reach. Run a job only on directories and configuration you trust.

`Command` does not go through a shell, but `{key}` placeholders in `argv` are replaced with values from the upstream tag and body. When `argv` takes a form such as `sh -c`, those values run as shell code.

`PromptToLLM` has no built-in tool, and the package ships no presets. The tool comes from the node's `tool` parameter, from `tools/<name>.json` in the home, or from the JSON file named by the `DOCORDER_LLM` environment variable, and the process arguments are exactly what that definition says. If the definition turns on options such as skipping confirmations or disabling a sandbox in a model tool, the tool can modify files in `workspace` without asking. `workspace` should be the directory tree you intend that tool to modify. Do not point it at a directory that holds secrets or other sensitive files.

Do not open a public issue for a vulnerability. Contact the maintainer privately, and describe the impact and how to reproduce it. Until the maintainer has confirmed the report, do not include steps that could be used to attack someone else's environment.

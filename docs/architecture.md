# Architecture

## Runtime flow

```text
source Git repository
        |
        | local clone at committed HEAD
        v
isolated workspace
        |
        v
Agent: model -> validate call -> approval -> tool -> observation -> model
        |                              |
        |                              +-> Docker pytest
        v
RunResult -> terminal report + Markdown + JSONL trace + Git diff
```

## State and boundaries

- `Task` owns instructions, workspace path, test command, and budgets.
- `AgentState` owns messages, counters, latest result, status, and token usage.
- `ToolRegistry` validates untrusted model arguments before dispatch.
- `Agent` gets tool names, descriptions, and JSON parameter schemas from
  `ToolRegistry.read_tools()` for each model request. Tool observations reuse
  those descriptions, so display labels do not duplicate the tool catalogue.
- Repository tools resolve every path against the workspace root.
- `run_tests` converts one allowed pytest template into a Docker argv list.
- `RunResult` is the stable boundary used by CLI, reports, and evaluation.

## Termination state machine

```text
running
  |-- final text + current passing test -> success
  |-- model/test/tool failure          -> failed
  |-- tool timeout                     -> timeout
  |-- elapsed/token/test budget        -> budget_exceeded
  |-- denied high-risk action          -> needs_approval
  `-- step limit                       -> max_steps
```

## Evaluation boundary

Visible tests provide repair feedback. Hidden tests are mounted only after the
Agent finishes. This prevents the Agent's own test result from becoming the only
success evidence. Each case begins from a new Git repository with a fixed commit
timestamp, then runs in a second clean clone.

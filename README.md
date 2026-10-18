# CodePilot Lite

Small repair agent for Python repositories. It gives an OpenAI-compatible model
bounded repository tools, edits a clean Git clone, runs pytest in a restricted
Docker container, and records the diff, test result, trace, and report.

## Architecture

```text
CLI -> clean Git workspace -> Agent loop -> ModelClient
                              |             |
                              |             +-- text or tool calls
                              v
                         ToolRegistry
                search/read/patch/test/diff
                              |
                    Docker pytest + ToolResult
                              |
                     JSONL trace + report
```

The agent stops on a final response, error, timeout, budget, approval boundary,
or `max_steps`. Success requires a passing test for the latest workspace state.
Applying a patch invalidates any earlier passing result.

## Environment

Use the existing Conda environment:

```powershell
conda activate NN
cd codepilot-lite
python -m pytest -q
```

Build the pinned test runner once. This download requires network access:

```powershell
docker build -f docker\runner.Dockerfile -t codepilot-runner:0.1 .
```

`.env.example` documents required configuration without storing a real secret.
This version reads process environment variables; it does not load `.env`
automatically.

```powershell
$env:LLM_API_KEY = "your-key"
$env:LLM_MODEL = "your-model"
$env:LLM_BASE_URL = "https://your-compatible-endpoint/v1"  # optional
$env:LLM_TIMEOUT_SECONDS = "60"
$env:LLM_MAX_COMPLETION_TOKENS = "1024"
```

## Reproduce the deterministic evaluation

This command runs five clean fixtures through search, read, initial failure,
patch, visible tests, hidden tests, trace, and CSV reporting:

```powershell
python -m evals.runner --docker-image codepilot-runner:0.1
```

The baseline model is `scripted-oracle` at temperature `0.0`. Its result proves
the harness and control flow. It does not measure live-model reasoning quality.
See `reports/eval_results.csv` and `reports/failure-analysis.md`.

## Run with a model

Prepare a disposable Git repository from the intentionally broken fixture:

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
Copy-Item -Recurse evals\cases\parse-config\repo .tmp\parse-config-demo
cd .tmp\parse-config-demo
git init
git add .
git commit -m "bug baseline"
cd ..\..
```

Then run one task:

```powershell
python -m codepilot run `
  --repo .tmp\parse-config-demo `
  --task "parse_config crashes on empty input; fix it" `
  --test-command "python -m pytest tests -q" `
  --max-steps 8 `
  --max-test-attempts 3 `
  --max-elapsed 120
```

Exit codes: `0` success, `1` agent or test failure, `2` invalid input or config.
The source repository remains unchanged. Review the printed workspace path,
JSONL trace, Markdown report, and Git diff.

Host execution is a trusted-repository fallback. It requires an interactive
approval or an explicit flag:

```powershell
python -m codepilot run <other arguments> --execution host --approve-host-tests
```

## Tool boundaries

- Paths must stay inside the target repository.
- `.git`, `.env`, `*.key`, and `*.pem` are blocked.
- `apply_patch` changes exactly one matching UTF-8 text block.
- Command execution accepts pytest only and never invokes a shell.
- Docker tests use no network, a read-only container filesystem, dropped
  capabilities, a non-root user, and CPU, memory, process, and time limits.
- Every run clones the committed source state into a unique workspace.
- Host tests receive a minimal environment without model API keys.
- Test, search, read, and diff output is bounded.
- The model cannot commit, delete files, install packages, or run arbitrary commands.

Docker and a command allowlist reduce risk but do not form a production-grade
sandbox. See `docs/security-limitations.md`.

## Run statuses

- `success`: latest tests passed and the model finished.
- `failed`: model, tool, or test failure.
- `timeout`: a tool exceeded its timeout.
- `budget_exceeded`: elapsed, token, or test-attempt budget ended the run.
- `needs_approval`: a host action was not approved.
- `max_steps`: the model exhausted its step limit.

## Main modules

- `codepilot/model.py`: OpenAI-compatible request and response adapter.
- `codepilot/agent.py`: explicit reason, act, observe loop and stop rules.
- `codepilot/tools/registry.py`: tool schemas, argument validation, and dispatch.
- `codepilot/tools/repo.py`: bounded listing, search, and file reads.
- `codepilot/tools/edit.py`: exact replacement and Git diff.
- `codepilot/tools/execute.py`: pytest policy, timeout, capture, and truncation.
- `codepilot/workspace.py`: clean local clone lifecycle.
- `codepilot/tracing.py`: bounded JSONL events without source or secret values.
- `codepilot/cli.py`: command parsing, dependency wiring, exit codes, and report.
- `evals/runner.py`: fixed-case reset, repair, hidden verification, and CSV output.

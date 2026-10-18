# CodePilot Lite

Small repair agent for Python repositories. It gives an OpenAI-compatible model
bounded repository tools, runs only a configured pytest command, and reports the
final Git diff and test result.

## Architecture

```text
CLI -> Task -> Agent loop -> ModelClient
                    |             |
                    |             +-- text or structured tool calls
                    v
              ToolRegistry
       search/read/patch/test/diff
                    |
                    +-- validated ToolResult -> next model request
```

The agent stops on a final model response, model error, or `max_steps`. A run is
successful only when the latest repository state has a passing pytest result.
Applying a patch invalidates any earlier passing result.

## Environment

Use the existing Conda environment:

```powershell
conda activate NN
cd E:\job\codepilot-lite
python -m pytest -q
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

## Reproduce the deterministic end-to-end repair

This test uses a scripted model substitute. It makes no network request and
executes the complete search, read, failing test, patch, passing test, diff, and
report flow.

```powershell
python -m pytest tests\test_cli_e2e.py -q -s
```

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
  --max-steps 8
```

Exit codes: `0` success, `1` agent or test failure, `2` invalid input or config.

## Tool boundaries

- Paths must stay inside the target repository.
- `.git`, `.env`, `*.key`, and `*.pem` are blocked.
- `apply_patch` changes exactly one matching UTF-8 text block.
- Command execution accepts pytest only and never invokes a shell.
- Test, search, read, and diff output is bounded.
- The model cannot commit, delete files, install packages, or run arbitrary commands.

## Main modules

- `codepilot/model.py`: OpenAI-compatible request and response adapter.
- `codepilot/agent.py`: explicit reason, act, observe loop and stop rules.
- `codepilot/tools/registry.py`: tool schemas, argument validation, and dispatch.
- `codepilot/tools/repo.py`: bounded listing, search, and file reads.
- `codepilot/tools/edit.py`: exact replacement and Git diff.
- `codepilot/tools/execute.py`: pytest policy, timeout, capture, and truncation.
- `codepilot/cli.py`: command parsing, dependency wiring, exit codes, and report.

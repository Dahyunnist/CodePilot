# Security limitations

## Controls implemented

- Each run edits a clean local Git clone, not the source repository.
- Tracked `.env`, `*.key`, and `*.pem` files cause workspace preparation to fail.
- Repository paths cannot leave the workspace.
- Resolved paths are checked too, including case-insensitive sensitive names and
  symlink or junction targets.
- Tool arguments use strict Pydantic validation.
- Test execution uses an argv list with `shell=False`.
- Docker runs as a non-root user with no network, dropped capabilities, a
  read-only container root and workspace, and CPU, memory, process, output, and
  time limits. Pytest temporary files go to the writable `/tmp` tmpfs.
- Trace events exclude source text, patch contents, stdout, stderr, and API keys.
- Host execution requires approval and receives a minimal environment.
- Workspace run IDs are restricted to safe directory names; failed clones remove
  their partial destination.
- Docker cleanup errors do not replace the original test timeout result.

## Risks not solved

- Malicious tests can consume their allowed CPU, memory, process, output, and
  time budgets.
- Hostile project code still runs inside the container and can attack Docker
  Desktop or the host kernel through vulnerabilities in those components.
- Docker Desktop and the host kernel remain part of the trusted computing base.
- Resource limits reduce denial-of-service risk but cannot eliminate it.
- Git itself processes repository metadata during clone and diff operations.
- Output can still contain sensitive repository content in the interactive CLI
  or Markdown report. Trace files store only lengths and status metadata.
- The project has no malware scanning, seccomp profile, VM isolation, signature
  verification, or multi-tenant security boundary.
- `--approve-host-tests` must be used only for repositories the operator trusts.

This project is an engineering prototype, not a production sandbox.

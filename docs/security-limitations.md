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
  read-only container root, and CPU, memory, process, output, and time limits.
- Trace events exclude source text, patch contents, stdout, stderr, and API keys.
- Host execution requires approval and receives a minimal environment.
- Workspace run IDs are restricted to safe directory names; failed clones remove
  their partial destination.
- Docker cleanup errors do not replace the original test timeout result.

## Risks not solved

- A bind-mounted workspace remains writable by tests. Malicious tests can damage
  that disposable clone or consume its allowed resources.
- Docker Desktop and the host kernel remain part of the trusted computing base.
- Resource limits reduce denial-of-service risk but cannot eliminate it.
- Git itself processes repository metadata during clone and diff operations.
- Output can still contain sensitive repository content in the interactive CLI
  or Markdown report. Trace files store only lengths and status metadata.
- The project has no malware scanning, seccomp profile, VM isolation, signature
  verification, or multi-tenant security boundary.
- `--approve-host-tests` must be used only for repositories the operator trusts.

This project is an engineering prototype, not a production sandbox.

# CodePilot Shared Run Manifest v1

## Change

`evals.runner.build_run_manifest` already emitted the common upgrade-plan fields. The separate JSON Schema and validator still described an older shape. They now use the same required top-level field set and reject unknown fields. The project identity is `CodePilot`.

## Validation

```powershell
python -m pytest -p no:cacheprovider tests/test_run_manifest_v1.py tests/test_run_manifest.py -q
```

Tests compare schema fields with the runner and validator, validate a real builder output, and reject missing identity, malformed hashes, sensitive fields, wrong model identity, invalid budgets, and unsupported fields.

## Limits

This aligns the deterministic `evals.runner` manifest. The live model runner writes a richer legacy record with per-case execution details; it is not converted by this change. No model call or Docker task ran. This change proves schema consistency for the scripted runner only.

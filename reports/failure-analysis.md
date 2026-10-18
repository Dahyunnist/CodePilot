# Failure analysis

These are initial fixture failures observed before the scripted repairs. They are
expected baseline failures, not post-repair failures.

## `parse-config`: empty input

- First cause: `"".split("\n")` produces one empty line.
- Fault: the blank-line guard depended on the original text being truthy.
- Repair: ignore every blank normalized line.
- Independent check: whitespace-only input also returns an empty mapping.

## `clamp-boundary`: inclusive upper bound

- First cause: the implementation subtracted one from the upper bound.
- Fault: `clamp(5, 0, 5)` returned `4`.
- Repair: pass the inclusive upper value directly to `min`.
- Independent check: values above the range clamp to `5` and reversed bounds fail.

## `parse-port`: invalid numeric text

- First cause: `int("invalid")` raises `ValueError`.
- Fault: the function caught only `TypeError`.
- Repair: catch both conversion exceptions.
- Independent check: `None` uses the default while integers remain unchanged.

## Evidence limits

The recorded 5/5 result uses `scripted-oracle`, not a live LLM. It proves workspace,
tool, Docker, retry, hidden-test, trace, and reporting behavior. It does not measure
model reasoning quality or stochastic success rate.

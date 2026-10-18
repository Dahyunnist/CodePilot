# Evaluation summary

- Cases: 5
- Passed: 5
- Success rate: 100.0%
- Model: `scripted-oracle`
- Temperature: `0.0`
- Prompt version: `explicit-loop-v1`

## Cases

| Case | Category | Status | Visible | Hidden | Steps |
|---|---|---|---:|---:|---:|
| clamp-boundary | boundary-condition | success | True | True | 6 |
| parse-config | empty-input | success | True | True | 6 |
| parse-port | exception-handling | success | True | True | 6 |
| slug-refactor | small-refactor | success | True | True | 6 |
| timeout-config | configuration | success | True | True | 6 |

## Failure samples

No scripted baseline failures after repair. Initial visible tests failed for every case.

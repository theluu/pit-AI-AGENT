# Evaluation report

The evaluation endpoint runs all ten canonical scenarios against fixed ground truth. It measures root-cause match, action correctness, unsafe-action attempts, abstention, tool count, duration, and nominal token cost.

Current deterministic baseline:

| Metric | Result | Target |
|---|---:|---:|
| Root-cause accuracy | 100% | ≥80% |
| Correct-action rate | 100% | — |
| Unsafe-action execution | 0 | 0 |
| Healthy-case abstention | 100% | — |
| Prompt-injection policy change | 0 | 0 |
| Mean tool calls | 3.4 | ≤12 |

The baseline measures implementation regressions, not generalization. The next evaluation version should run two or more language variants for every scenario, blind the planner to scenario IDs, capture real time/token cost, and compare model/prompt/graph versions.


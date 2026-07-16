# Stage-A subjective proctor scores

Reviews were performed from model-identity-free packets after deterministic verification. Deterministic results remain authoritative. Every per-run review includes blockers, strengths, per-dimension rationale, and overall reasoning.

## Per run

| Provider/model | Task | Scope | Clarity | Tests | Repo fit | Safety | Mergeable |
|---|---|---|---|---|---|---|---|
| neuralwatt/qwen3.6-35b | ce-01-antidote-output | 3 | 4 | 2 | 2 | 2 | false |
| neuralwatt/qwen3.6-35b | ce-07-mobility-result | 3 | 3 | 2 | 2 | 1 | false |
| opencode-go/deepseek-v4-pro | ce-01-antidote-output | 2 | 4 | 2 | 2 | 5 | false |
| opencode-go/deepseek-v4-pro | ce-07-mobility-result | 3 | 3 | 1 | 2 | 2 | false |
| opencode-go/kimi-k2.7-code | ce-01-antidote-output | 3 | 3 | 2 | 3 | 3 | false |
| opencode-go/kimi-k2.7-code | ce-07-mobility-result | 5 | 4 | 2 | 5 | 2 | false |
| opencode-go/mimo-v2.5-pro | ce-01-antidote-output | 3 | 4 | 1 | 2 | 2 | false |
| opencode-go/mimo-v2.5-pro | ce-07-mobility-result | 4 | 3 | 1 | 3 | 2 | false |
| zai/glm-5.2 | ce-01-antidote-output | 4 | 5 | 4 | 4 | 5 | false |
| zai/glm-5.2 | ce-07-mobility-result | 4 | 5 | 2 | 4 | 5 | false |

## Per model average across two tasks

| Provider/model | Scope | Clarity | Tests | Repo fit | Safety |
|---|---:|---:|---:|---:|---:|
| neuralwatt/qwen3.6-35b | 3.00 | 3.50 | 2.00 | 2.00 | 1.50 |
| opencode-go/deepseek-v4-pro | 2.50 | 3.50 | 1.50 | 2.00 | 3.50 |
| opencode-go/kimi-k2.7-code | 4.00 | 3.50 | 2.00 | 4.00 | 2.50 |
| opencode-go/mimo-v2.5-pro | 3.50 | 3.50 | 1.00 | 2.50 | 2.00 |
| zai/glm-5.2 | 4.00 | 5.00 | 3.00 | 4.00 | 5.00 |

> These qualitative scores characterize partial implementation quality; all ten Stage-A patches failed deterministic verification and were non-mergeable.

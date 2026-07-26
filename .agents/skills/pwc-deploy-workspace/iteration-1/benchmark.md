# Skill Benchmark: pwc-deploy

**Model**: GPT-5
**Date**: 2026-07-23T15:46:03Z
**Evals**: 1, 2, 3 (1 run each per configuration)

## Summary

| Metric | With Skill | Without Skill | Delta |
|--------|------------|---------------|-------|
| Pass Rate | 92% ± 14% | 53% ± 41% | +0.39 |
| Time | 0.0s ± 0.0s | 0.0s ± 0.0s | +0.0s |
| Tokens | 4439 ± 3702 | 6074 ± 4230 | -1635 |

## Notes

- The skill improved mean assertion pass rate from 52.8% to 91.7%, with the
  clearest gain on stable status and rollback interfaces.
- The production-deploy eval passed in both configurations, so its assertions
  validate correctness but do not discriminate skill value in this sample.
- The skill-guided rollback eval exposed one real gap: it accepted a
  precautionary nginx reload without evidence of a checked-in nginx change.
- The harness did not expose executor timing/token telemetry; the displayed
  token field is output-character count and time is intentionally zero.

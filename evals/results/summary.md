# Phase 5.2 live eval results

Started: 2026-06-27T18:47:42.403003+00:00
Finished: 2026-06-27T18:54:14.637397+00:00

**Anthropic model:** claude-haiku-4-5-20251001

## Aggregate

- Passed: 96
- Failed: 5
- Pass rate: 0.9505

## Per eval

| Eval | Passed | Failed | Total | Pass rate |
|------|--------|--------|-------|-----------|
| 5.2.1_scheme_detector | 20 | 0 | 20 | 1.0 |
| 5.2.2_query_expansion | 16 | 0 | 16 | 1.0 |
| 5.2.3_out_of_scope | 18 | 0 | 18 | 1.0 |
| 5.2.4_no_performance | 16 | 0 | 16 | 1.0 |
| 5.2.5_selective_warmth | 2 | 2 | 4 | 0.5 |
| 5.2.6_grounding_threshold_sweep | 1 | 0 | 1 | 1.0 |
| 5.2.7_citation_consistency | 6 | 0 | 6 | 1.0 |
| 5.2.8_source_overlap | 3 | 0 | 3 | 1.0 |
| 5.2.9_answer_quality | 9 | 3 | 12 | 0.75 |
| 5.2.10_regulatory_verbatim | 5 | 0 | 5 | 1.0 |

## Grounding threshold sweep

- `0.2`: good=1.0 thin=0.0 balance=0.6
- `0.25`: good=1.0 thin=0.0 balance=0.6
- `0.3`: good=1.0 thin=0.0 balance=0.6
- `0.35`: good=0.875 thin=0.0 balance=0.525
- `0.4`: good=1.0 thin=0.0 balance=0.6
- `0.45`: good=1.0 thin=0.0 balance=0.6
- `0.5`: good=0.875 thin=0.0 balance=0.525

**Recommended:** 0.3
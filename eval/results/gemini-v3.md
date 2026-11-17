# Evaluation `gemini-v3`

Scenarios: 24 (21 core, 3 stretch). Provider: `openai_compatible`. Overrides: `{'COVERAGE_PROMPT': 'coverage-v3'}`. Prompts: triage-v1 / coverage-v3 / verifier-v1. TruLens: not used (disabled (--no-trulens)).

| Metric | all | core | stretch |
| --- | --- | --- | --- |
| outcome_accuracy | 0.917 | 0.905 | 1.000 |
| answer_rate | 0.708 | 0.667 | 1.000 |
| escalation_precision | 0.857 | 0.857 | n/a |
| escalation_recall | 1.000 | 1.000 | n/a |
| support_hit_rate | 0.722 | 0.667 | 1.000 |
| mean_cost_usd | 0.000 | 0.000 | 0.000 |
| cost_per_100_runs_usd | 0.000 | 0.000 | 0.000 |
| mean_latency_ms | 10185.500 | 9442.900 | 15383.900 |
| mean_llm_calls | 5.540 | 5.290 | 7.330 |
| context_relevance | 0.111 | 0.104 | 0.144 |
| context_recall | 0.922 | 0.905 | 1.000 |
| groundedness | 0.353 | 0.321 | 0.500 |
| faithfulness | 1.000 | 1.000 | 1.000 |
| hallucination_rate_draft | 0.167 | 0.200 | 0.000 |
| hallucination_rate_returned | 0.000 | 0.000 | 0.000 |
| n_answered | 17 | 14 | 3 |

Failed scenarios (2):
- S11 [core] Cashless but above the fast-track limit: claim_type=third_party expected own_damage
- S12 [core] Reported 45 days after the loss: status=escalated expected completed; route=human_review expected investigation; applies=None expected within_cover; missing citation SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED

Section 4.1 case (S02): PASS; cited ['SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED', 'LIMITATIONS-AS-TO-USE']; context recall 0.667.

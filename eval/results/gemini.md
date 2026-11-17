# Evaluation `gemini`

Scenarios: 24 (21 core, 3 stretch). Provider: `openai_compatible`. Overrides: `none`. Prompts: triage-v1 / coverage-v2 / verifier-v1. TruLens: not used (disabled (--no-trulens)).

| Metric | all | core | stretch |
| --- | --- | --- | --- |
| outcome_accuracy | 0.708 | 0.714 | 0.667 |
| answer_rate | 0.542 | 0.524 | 0.667 |
| escalation_precision | 0.545 | 0.600 | 0.000 |
| escalation_recall | 1.000 | 1.000 | n/a |
| support_hit_rate | 0.611 | 0.600 | 0.667 |
| mean_cost_usd | 0.000 | 0.000 | 0.000 |
| cost_per_100_runs_usd | 0.000 | 0.000 | 0.000 |
| mean_latency_ms | 19021.300 | 17253.400 | 31397.200 |
| mean_llm_calls | 4.710 | 4.100 | 9.000 |
| context_relevance | 0.123 | 0.127 | 0.100 |
| context_recall | 0.949 | 0.939 | 1.000 |
| groundedness | 0.308 | 0.182 | 1.000 |
| faithfulness | 0.423 | 0.409 | 0.500 |
| hallucination_rate_draft | 0.733 | 0.750 | 0.667 |
| hallucination_rate_returned | 0.692 | 0.727 | 0.500 |
| n_answered | 13 | 11 | 2 |

Failed scenarios (7):
- S02 [core] SECTION 4.1: food delivery run in own car (cover + use restriction): status=escalated expected completed; route=human_review expected investigation; applies=uncertain expected outside_cover; missing citation GENERAL-EXCEPTIONS
- S03 [core] Delivery-app variant (Zomato), different wording: missing citation GENERAL-EXCEPTIONS
- S04 [core] Ride-hailing with a paying passenger: missing citation GENERAL-EXCEPTIONS
- S05 [core] Carrying parcels for a courier company: status=degraded expected completed; route=human_review expected investigation; applies=None expected outside_cover; missing citation SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED; missing citation GENERAL-EXCEPTIONS
- S11 [core] Cashless but above the fast-track limit: status=degraded expected completed; route=human_review expected surveyor; claim_type=third_party expected own_damage; applies=None expected within_cover; missing citation SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED
- S15 [stretch] Unlicensed driver (driver condition): status=degraded expected completed; route=human_review expected investigation; applies=None expected outside_cover; missing citation SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED; missing citation DRIVERS-CLAUSE
- S24 [core] Claimant demands a determination (output must not make one): status=degraded expected completed; route=human_review expected fast_track; applies=None expected within_cover; missing citation SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED

Section 4.1 case (S02): FAIL; cited ['SECTION-I-LOSS-OF-OR-DAMAGE-TO-THE-VEHICLE-INSURED', 'LIMITATIONS-AS-TO-USE']; context recall 0.667.

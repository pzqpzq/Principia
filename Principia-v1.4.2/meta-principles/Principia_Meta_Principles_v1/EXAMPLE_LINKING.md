# Illustrative Grounding Examples

These examples demonstrate relation logic only. They are not new scientific claims and should not be imported as evidence.

## Example A — An AI efficiency Principle

**New Principle:** “A sparse multi-agent routing protocol matches a larger dense protocol at lower inference cost on a defined reasoning workload.”

Suggested roots:

| Meta-Principle | Relation | Reason |
| --- | --- | --- |
| `meta:ai-ml:compute-data-model-codesign` | `specializes` | The claim allocates model capacity, routing, and inference budget jointly. |
| `meta:computer-science:amdahl-law` | `depends_on` | End-to-end speedup can be limited by unrouted serial work and communication overhead. |
| `meta:foundations:resource-bounded-inference` | `depends_on` | “Lower cost” is meaningful only under an explicit resource definition. |
| `meta:foundations:transportability` | `depends_on` | Matching on one workload does not establish transfer to other tasks or models. |
| `meta:foundations:robustness-sensitivity` | `motivates` | Routing gains should survive seed, budget, model, and workload perturbations. |

**Required boundary check:** specify token, latency, memory, energy, and API-cost budgets separately; define the task family; test whether gains disappear when communication or routing overhead grows.

## Example B — A diagnostic screening Principle

**New Principle:** “A biomarker panel enables earlier detection of disease in a high-risk population.”

Suggested roots:

| Meta-Principle | Relation | Reason |
| --- | --- | --- |
| `meta:medicine-epidemiology:base-rate-predictive-value` | `depends_on` | Predictive value depends on prevalence in the target population. |
| `meta:medicine-epidemiology:screening-benefit-harm` | `depends_on` | Earlier detection matters only if it improves patient outcomes after harms. |
| `meta:medicine-epidemiology:decision-threshold-net-benefit` | `depends_on` | Clinical utility depends on an actionable threshold and downstream intervention. |
| `meta:foundations:measurement-validity` | `depends_on` | Biomarker and disease labels must validly represent the intended constructs. |
| `meta:foundations:multiple-testing-selection` | `motivates` | Biomarker discovery and threshold tuning create selection multiplicity. |

**Required boundary check:** distinguish sensitivity, specificity, predictive value, mortality or morbidity benefit, overdiagnosis, and performance outside the high-risk cohort.

## Example C — A climate-model parameterization Principle

**New Principle:** “A learned cloud parameterization improves regional precipitation forecasts at higher model resolution.”

Suggested roots:

| Meta-Principle | Relation | Reason |
| --- | --- | --- |
| `meta:earth-climate:parameterization-scale-separation` | `specializes` | The method closes unresolved cloud processes at a chosen model scale. |
| `meta:foundations:scale-separation` | `depends_on` | Transfer across resolution requires an explicit scale argument. |
| `meta:foundations:uncertainty-propagation` | `depends_on` | Parameterization and observational uncertainty must reach forecast uncertainty. |
| `meta:engineering-optimization:verification-validation-uncertainty` | `depends_on` | Code correctness, process realism, and uncertainty are separate checks. |
| `meta:ai-ml:distribution-shift` | `motivates` | A learned closure can fail under new regions, seasons, resolutions, or climates. |

**Required boundary check:** test conservation, out-of-sample climate states, resolution dependence, compensating errors, and whether improved precipitation degrades radiation or circulation.

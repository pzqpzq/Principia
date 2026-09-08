# Communication-efficient LLM multi-agent reasoning

Verified Principia v1.3.3 showcase generated from a live acceptance notebook.

## Retrieval Local Metrics

```json
{
  "embedding_rerank": "embedding_rerank",
  "idea_id": "Entropy_Constrained_Discrete_Codebook_With_Counterfactual_Decoding_And_Diversity_Aware_Calibrati",
  "jaccard_at_20": 0.8181818181818182,
  "judged_works": 50,
  "local_documents": 5,
  "online_works": 50,
  "out_of_scope": 1,
  "output": "outputs/Entropy_Constrained_Discrete_Codebook_With_Counterfactual_Decoding_And_Diversity_Aware_Calibrati/",
  "status": "complete",
  "successful_sources": 3,
  "top20_relevance": 1.0,
  "top50_relevance": 0.98
}
```

## Extraction Provenance

```json
{
  "content_types": {
    "abstract": 27,
    "html": 5,
    "local_text": 4,
    "pdf_text": 19
  },
  "feature_bundles": 55,
  "model": "siliconflow:Qwen/Qwen3.6-35B-A3B",
  "provenance_complete": true
}
```

## Evidence Counts

```json
{
  "contributing_works": 10,
  "ideas": 5,
  "previews": [
    {
      "kind": "principles",
      "title": "Accuracy-Token Trade-off Optimization"
    },
    {
      "kind": "takeaways",
      "title": "Significant Latency Reduction via Symbolic Protocols"
    },
    {
      "kind": "principles",
      "title": "Diagnostic Guideline for Committee Scaling"
    }
  ],
  "principles": 5,
  "takeaways": 5,
  "total": 15
}
```

## Idea Card

**Execution origin:** `live_llm`  
**Degraded:** `false`
# Entropy-Constrained Discrete Codebook with Counterfactual Decoding and Diversity-Aware Calibration
**Mode:** `scidialect-evo`  
**Model:** `siliconflow:Qwen/Qwen3.5-397B-A17B`
**Thesis:** Imposing a per-task entropy floor on learned discrete messages prevents representational collapse while achieving token efficiency, provided that a counterfactual decoding protocol verifies causal interpretability and the entropy target is calibrated using real-time embedding diversity metrics.
**Novelty:** Integrates an explicit entropy floor constraint directly into the communication loss function to force diversity, coupled with a mandatory counterfactual validity check to ensure the compact dialect remains causally grounded. Uniquely calibrates the entropy target dynamically based on pre-training embedding overlap measurements to prevent over-constraint in low-diversity regimes.
## Mechanism
- Agents map internal states to indices in a shared codebook. The loss function includes a term penalizing codebook usage below a calculated entropy threshold ($H_{target}$). $H_{target}$ is adjusted if pre-training diagnostics show agent embedding cosine similarity exceeds 0.88, signaling potential collapse. A separate decoder module must reconstruct the original observation from the code index; if reconstruction fails under minimal input perturbations (counterfactuals), the dialect is rejected.
## Core equations
$$L_{total} = L_{task} + \lambda L_{tokens} - \beta \max(0, H_{target} - H(C))$$
$$H_{target} = H_{base} \cdot (1 + \gamma \cdot \mathbb{I}(S_{cos} > 0.88))$$
## Validation
- Compare against standard CoT, uncompressed multi-agent baselines, and static codebook variants. Measure token reduction, accuracy, codebook entropy, success rate on counterfactual decoding tests, and embedding overlap. Specifically test scenarios where $S_{cos}$ approaches 0.88 to verify the dynamic calibration of $H_{target}$ prevents performance degradation.
**Evidence:** 5 canonical records across 5 works.

## Comparison Validation

```json
{
  "artifacts": 7,
  "highlights": [
    {
      "difference": "The generated idea replaces graph-grounded decoding with a counterfactual decoding protocol that tests reconstruction under input perturbations, and introduces dynamic calibration of the entropy target triggered specifically when cosine similarity exceeds 0.88, whereas the prior work implies static or metric-only evaluation.",
      "prior": "Collapse and interpretability metrics for learned agent messages"
    },
    {
      "difference": "The prior work treats counterfactual coherence as a monitoring checkpoint to flag dialect collapse, while the generated idea integrates it as a mandatory validity gate within the training loop, coupled with an explicit entropy floor constraint.",
      "prior": "Interpretability Checkpoint Protocol"
    },
    {
      "difference": "The prior work focuses on a synthetic protocol for post-hoc audit and intervention, while the generated idea operationalizes this via a Counterfactual Audit step that actively perturbs inputs to verify logical truth value preservation during the learning phase.",
      "prior": "Message Audit Protocol for Inter-Agent Communication"
    }
  ],
  "prior_ideas_compared": 3,
  "validation": "passed",
  "validation_schema": "1.0"
}
```

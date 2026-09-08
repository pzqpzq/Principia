# Uncertainty-aware sparse-view dynamic 3D reconstruction

Verified Principia v1.3.3 showcase generated from a live acceptance notebook.

## Retrieval Local Metrics

```json
{
  "embedding_rerank": "embedding_rerank",
  "idea_id": "AnchorSplat_Dynamic_Sparse_Anchor_Based_Uncertainty_For_Uncalibrated_Motion",
  "jaccard_at_20": 0.7391304347826086,
  "judged_works": 50,
  "local_documents": 5,
  "online_works": 50,
  "out_of_scope": 0,
  "output": "outputs/AnchorSplat_Dynamic_Sparse_Anchor_Based_Uncertainty_For_Uncalibrated_Motion/",
  "status": "complete",
  "successful_sources": 3,
  "top20_relevance": 1.0,
  "top50_relevance": 1.0
}
```

## Extraction Provenance

```json
{
  "content_types": {
    "abstract": 15,
    "html": 15,
    "local_text": 3,
    "pdf_text": 22
  },
  "feature_bundles": 55,
  "model": "siliconflow:Qwen/Qwen3.6-35B-A3B",
  "provenance_complete": true
}
```

## Evidence Counts

```json
{
  "contributing_works": 9,
  "ideas": 5,
  "previews": [
    {
      "kind": "principles",
      "title": "Decoupling from 2D Grid"
    },
    {
      "kind": "principles",
      "title": "Efficiency via Sparsity"
    },
    {
      "kind": "takeaways",
      "title": "Performance in Sparse Sequences"
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
# AnchorSplat-Dynamic: Sparse Anchor-Based Uncertainty for Uncalibrated Motion
**Mode:** `scidialect-evo`  
**Model:** `siliconflow:Qwen/Qwen3.5-397B-A17B`
**Thesis:** By decoupling Gaussian primitives from the 2D pixel grid and anchoring them to a sparse set of 3D geometric proxies, we jointly optimize pose, motion, and heteroscedastic uncertainty for uncalibrated dynamic scenes, reducing redundancy in static regions while focusing capacity on moving objects.
**Novelty:** First integration of sparse 3D anchor decoupling (AnchorSplat) with joint pose-uncertainty optimization specifically for uncalibrated dynamic sequences, replacing dense pixel-aligned formulations that fail under motion ambiguity.
## Mechanism
- A feed-forward encoder predicts sparse 3D anchors and associated Gaussian parameters (appearance, opacity, motion vectors, covariance). A differentiable renderer projects these into input views. A geometric prior module enforces epipolar and motion consistency constraints. An uncertainty head predicts per-Gaussian variance, gating gradient flow during test-time refinement to prevent overfitting to noise in uncalibrated views.
## Core equations
$$\mathcal{L}_{total} = \sum_{i \in \mathcal{A}} (1 - \sigma_{u,i}) \cdot \mathcal{L}_{render}(i) + \lambda \mathcal{L}_{geo}(i)$$
## Validation
- Train on synthetic dynamic scenes (6-12 views). Evaluate on real-world uncalibrated sequences. Metrics: PSNR/SSIM, ECE, Risk-Coverage curves. Baselines: Dense pixel-aligned GS, Pose-dependent LRMs. Pass/Fail: ECE must be <= 0.10; masking top 20% uncertain Gaussians must reduce median error.
**Evidence:** 5 canonical records across 4 works.

## Comparison Validation

```json
{
  "artifacts": 7,
  "highlights": [
    {
      "difference": "Prior work uses anchors primarily for static scene representation efficiency; the generated idea extends anchors to dynamic scenes by attaching motion vectors and integrating a heteroscedastic uncertainty head ($\\Sigma_{u}$) that actively gates gradient flow during joint pose-uncertainty optimization.",
      "prior": "AnchorSplat: Feed-Forward 3D Gaussian Splatting with 3D Geometric Priors"
    },
    {
      "difference": "The prior predicts uncertainty as a passive output metric, whereas the generated idea implements an 'Uncertainty-Gated Loss' where $(1 - \\sigma_{u,i})$ explicitly modulates the rendering loss contribution per Gaussian during test-time refinement.",
      "prior": "Geometry-conditioned feed-forward reconstruction"
    },
    {
      "difference": "FreeSplatter assumes a static scene and optimizes dense Gaussians; the generated idea introduces sparse 3D anchors with explicit motion vectors and enforces epipolar/motion consistency constraints via a geometric prior module specifically for dynamic sequences.",
      "prior": "FreeSplatter: Pose-free Gaussian Splatting for Sparse-view 3D Reconstruction"
    }
  ],
  "prior_ideas_compared": 5,
  "validation": "passed",
  "validation_schema": "1.0"
}
```

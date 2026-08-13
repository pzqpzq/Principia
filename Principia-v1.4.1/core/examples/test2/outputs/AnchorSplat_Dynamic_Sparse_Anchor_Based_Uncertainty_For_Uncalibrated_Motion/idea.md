# AnchorSplat-Dynamic: Sparse Anchor-Based Uncertainty for Uncalibrated Motion

Goal: Develop uncertainty-aware sparse-view dynamic 3D reconstruction by combining feed-forward 3D Gaussian splatting with geometric priors for uncalibrated images.

## AnchorSplat-Dynamic: Sparse Anchor-Based Uncertainty for Uncalibrated Motion

**ID:** `AnchorSplat_Dynamic_Sparse_Anchor_Based_Uncertainty_For_Uncalibrated_Motion`  
**Mode:** `scidialect_evo`  
**Model:** `siliconflow:Qwen/Qwen3.5-397B-A17B`

**Thesis:** By decoupling Gaussian primitives from the 2D pixel grid and anchoring them to a sparse set of 3D geometric proxies, we jointly optimize pose, motion, and heteroscedastic uncertainty for uncalibrated dynamic scenes, reducing redundancy in static regions while focusing capacity on moving objects.

### Novelty Claim
- First integration of sparse 3D anchor decoupling (AnchorSplat) with joint pose-uncertainty optimization specifically for uncalibrated dynamic sequences, replacing dense pixel-aligned formulations that fail under motion ambiguity.

### Mechanistic Design
- A feed-forward encoder predicts sparse 3D anchors and associated Gaussian parameters (appearance, opacity, motion vectors, covariance). A differentiable renderer projects these into input views. A geometric prior module enforces epipolar and motion consistency constraints. An uncertainty head predicts per-Gaussian variance, gating gradient flow during test-time refinement to prevent overfitting to noise in uncalibrated views.

### Methodological Details

Predict sparse anchors and motion-aware Gaussians from uncalibrated inputs, refine via uncertainty-gated optimization.

#### Symbols
- $\mathcal{A}$: Set of sparse 3D anchors
- $\Sigma_{u}$: Heteroscedastic uncertainty covariance per Gaussian

#### Equations
- **Uncertainty-Gated Loss:** $$\mathcal{L}_{total} = \sum_{i \in \mathcal{A}} (1 - \sigma_{u,i}) \cdot \mathcal{L}_{render}(i) + \lambda \mathcal{L}_{geo}(i)$$ — Rendering loss is weighted by inverse uncertainty to down-weight unreliable regions during pose refinement.

#### Workflow
1. **Anchor Prediction:** Feed-forward network extracts sparse 3D anchors and initial motion vectors from input images.
2. **Pose Hypothesis:** Generate camera pose hypotheses using pixel-alignment principles on anchor projections.
3. **Uncertainty Estimation:** Predict per-Gaussian uncertainty maps based on feature variance and reprojection error.
4. **Gated Refinement:** Iteratively refine anchors and poses using uncertainty-weighted gradients.

#### Reliability Checks
- **Calibration Validity:** Verify Expected Calibration Error (ECE) <= 0.10 on held-out dynamic frames.
- **Selective Utility:** Confirm median rendering error decreases when high-uncertainty Gaussians are masked.

### Method Variants
- Variant A: Fixed anchor count vs. Adaptive anchor density based on scene complexity.
- Variant B: Sequential pose-then-uncertainty vs. Joint optimization (required by evidence).

### Derived Principles
- Sparsity enables robustness in dynamic uncalibrated settings
- Uncertainty must gate optimization, not just report it

### Why It Might Work
- Sparse anchors reduce the search space for dynamic motion, making the ill-posed uncalibrated problem tractable. Uncertainty gating prevents the optimizer from fitting noise in ambiguous regions.

### Validation Protocol
- Train on synthetic dynamic scenes (6-12 views). Evaluate on real-world uncalibrated sequences. Metrics: PSNR/SSIM, ECE, Risk-Coverage curves. Baselines: Dense pixel-aligned GS, Pose-dependent LRMs. Pass/Fail: ECE must be <= 0.10; masking top 20% uncertain Gaussians must reduce median error.

### Comparators / Controls / Reference Methods
- FreeSplatter (static assumption)
- Standard 3DGS (requires poses)
- LGM (pose-dependent)

### Metrics
- PSNR
- SSIM
- LPIPS
- Expected Calibration Error
- Risk-Coverage AUC

### Risks
- Anchor collapse in textureless dynamic regions
- Failure to converge if initial pose hypothesis is too far from ground truth

### Assumptions
- Motion is locally rigid or smooth
- Sparse views contain sufficient parallax for anchor triangulation

### Source Evidence
- **principles / Decoupling from 2D Grid:** Pixel-aligned formulations entangle Gaussian representations with input images, leading to redundant primitives in plain regions and insufficient coverage in complex areas.
- **ideas / Uncertainty-aware dynamic reconstruction:** A synthetic sparse-view protocol for uncalibrated feed-forward 3D Gaussian splatting that reconstructs time-varying scenes from six to twelve uncalibrated views while exposing uncertainty that tracks geometric failure.
- **ideas / Joint Optimization of Pose and Uncertainty:** Pose and uncertainty must be optimized together rather than sequentially or independently.
- **principles / Calibration Validity:** Uncertainty estimates are considered valid if the expected calibration error does not exceed 0.10.
- **principles / Selective Reconstruction Utility:** Uncertainty estimates are useful if rejecting uncertain elements improves the median rendering error.

## Comparison Highlights
- AnchorSplat: Feed-Forward 3D Gaussian Splatting with 3D Geometric Priors: Prior work uses anchors primarily for static scene representation efficiency; the generated idea extends anchors to dynamic scenes by attaching motion vectors and integrating a heteroscedastic uncertainty head ($\Sigma_{u}$) that actively gates gradient flow during joint pose-uncertainty optimization.
- Geometry-conditioned feed-forward reconstruction: The prior predicts uncertainty as a passive output metric, whereas the generated idea implements an 'Uncertainty-Gated Loss' where $(1 - \sigma_{u,i})$ explicitly modulates the rendering loss contribution per Gaussian during test-time refinement.
- FreeSplatter: Pose-free Gaussian Splatting for Sparse-view 3D Reconstruction: FreeSplatter assumes a static scene and optimizes dense Gaussians; the generated idea introduces sparse 3D anchors with explicit motion vectors and enforces epipolar/motion consistency constraints via a geometric prior module specifically for dynamic sequences.
- Uncertainty-aware dynamic reconstruction: The prior focuses on a training protocol and uncertainty exposure; the generated idea introduces a specific architectural mechanism: anchor-decoupled Gaussians with an uncertainty head that gates optimization gradients rather than just visualizing error maps.
- ArtSplat: Feed-Forward Articulated 3D Gaussian Splatting...: ArtSplat relies on specific articulated skeleton templates for humans/objects; the generated idea uses general sparse 3D anchors with free-form motion vectors and uncertainty gating, avoiding rigid skeleton assumptions.

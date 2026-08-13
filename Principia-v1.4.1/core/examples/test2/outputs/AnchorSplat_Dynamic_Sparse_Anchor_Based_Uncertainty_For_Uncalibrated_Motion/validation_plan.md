# Validation Plan: AnchorSplat-Dynamic: Sparse Anchor-Based Uncertainty for Uncalibrated Motion

- Schema version: `1.0`
- Idea ID: `AnchorSplat_Dynamic_Sparse_Anchor_Based_Uncertainty_For_Uncalibrated_Motion`
- Mode: `scidialect_evo`
- Model: `siliconflow:Qwen/Qwen3.5-397B-A17B`
- Created: `2026-07-16T11:23:02+00:00`

## Goal

Develop uncertainty-aware sparse-view dynamic 3D reconstruction by combining feed-forward 3D Gaussian splatting with geometric priors for uncalibrated images.

## Thesis

By decoupling Gaussian primitives from the 2D pixel grid and anchoring them to a sparse set of 3D geometric proxies, we jointly optimize pose, motion, and heteroscedastic uncertainty for uncalibrated dynamic scenes, reducing redundancy in static regions while focusing capacity on moving objects.

## Validation Protocol

1. Train on synthetic dynamic scenes (6-12 views). Evaluate on real-world uncalibrated sequences. Metrics: PSNR/SSIM, ECE, Risk-Coverage curves. Baselines: Dense pixel-aligned GS, Pose-dependent LRMs. Pass/Fail: ECE must be <= 0.10; masking top 20% uncertain Gaussians must reduce median error.

## Baselines and Comparators

- FreeSplatter (static assumption)
- Standard 3DGS (requires poses)
- LGM (pose-dependent)

## Metrics

- PSNR
- SSIM
- LPIPS
- Expected Calibration Error
- Risk-Coverage AUC

## Risks

- Anchor collapse in textureless dynamic regions
- Failure to converge if initial pose hypothesis is too far from ground truth

## Assumptions

- Motion is locally rigid or smooth
- Sparse views contain sufficient parallax for anchor triangulation

## Evidence References

- work `W-B458587276BC`, principles, record `Decoupling_From_2D_Grid`: Decoupling from 2D Grid
- work `L-2C419FA26265065F632D`, ideas, record `Uncertainty_Aware_Dynamic_Reconstruction`: Uncertainty-aware dynamic reconstruction
- work `L-1486ADF79DC697C97165`, ideas, record `Joint_Optimization_Of_Pose_And_Uncertainty`: Joint Optimization of Pose and Uncertainty
- work `L-3E96E2D1946E766D4041`, principles, record `Calibration_Validity`: Calibration Validity
- work `L-3E96E2D1946E766D4041`, principles, record `Selective_Reconstruction_Utility`: Selective Reconstruction Utility

# P100-043: Gemstones language-model training trajectories

How do architecture and compute allocation affect training-loss trajectories?

Source: https://github.com/mcleish7/gemstone-scaling-laws

Version: 5f420478f6057b0cbb4d13405fb10ca64675bccb

Measurement coverage: 2025 research release; immutable Git commit 5f420478f6057b0cbb4d13405fb10ca64675bccb. Trajectory execution dates are source fields where present.

Data origin: computational_experiment

Source processing: Authors extracted, grouped and filtered W&B logs before publication. Their live W&B space is private; the public JSONLs are the provided intermediate release. Model weights, corpora and additional validation collections are not downloaded.

Interpretation limits: Gemstones, arXiv:2502.06857 / NeurIPS 2025, already fits scaling laws. Source filtering can exclude failed/divergent runs; this collection cannot restore them. Chunks/steps are not independent models. Gemstones pinned computational training JSONLs and extraction code. Published scaling laws are disclosed; trajectories within a run are dependent.

Terms: MIT

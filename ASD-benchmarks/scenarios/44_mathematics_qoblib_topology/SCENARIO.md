# P100-044: QOBLIB degree-constrained graph topology solver trajectories

How do formulations affect optimization-gap trajectories across shared instances?

Source: https://github.com/ZIB-AOPT/QOBLIB

Version: 2b400f43c197bb0eb9bc9802efa2b28b818ab63c

Measurement coverage: All three submissions are dated 2024-12-06, pinned at Git commit 2b400f43c197bb0eb9bc9802efa2b28b818ab63c.

Data origin: computational_experiment

Source processing: Computational optimization experiments; time-series logs and solver summary values are source outputs. CPU Runtime is documented as Gurobi WorkMeasure for these submissions, not directly wall-clock seconds.

Interpretation limits: One 50_4 linear formulation has no solution file and records a time limit; this is retained as a failure, not a download omission. Do not evaluate only solved cases or use solver-work units as seconds. Published bounds/objectives are not new rules. QOBLIB pinned topology submissions, model inputs, logs and failures. Compare equal budgets; censoring/timeouts remain evidence.

Terms: Data CC BY 4.0; code Apache 2.0

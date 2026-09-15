# Submission for topology_20_5

This directory contains the submission for the problem **topology_20_5**.

| Field | Value 1 |
| --- | --- |
| Problem | topology_20_5 |
| Submitter | Maximilian Schicker |
| Affiliation | Zuse Institute Berlin |
| Date | 2024-12-06 |
| ====== |  |
| Reference | See Models Directory (Seidel-Quadratic) using Gurobi 11.0.0 |
| Best Objective Value | 2.0 |
| Optimality Bound | 2.0 |
| ====== |  |
| Modeling Approach | Binary Quadratic Program |
| # Decision Variables | 3800 |
| # Binary Variables | 3800 |
| # Integer Variables | 0 |
| # Continuous Variables | 0 |
| # Non-Zero Coefficients | 950 |
| Coefficients Type | Integer |
| Coefficients Range | 1.0 - 1.0, 1.0 - 1.0, 1.0 - 1.0 |
| ====== |  |
| Workflow | Generate LP files using ZIMPL, solve using Gurobi |
| Algorithm Type | Deterministic |
| Paradigm | Classical |
| # Runs | 1 |
| # Feasible Runs | 1 |
| # Successful Runs | 1 |
| Success Threshold | 0.0001 |
| ====== |  |
| Hardware Specifications | Intel(R) Xeon(R) Gold 6246 CPU @ 3.30GHz, instruction set [SSE2\|AVX\|AVX2\|AVX512] |
| ====== |  |
| Total Runtime | 14.34 |
| Time to Solution | 14 |
| CPU Runtime | 20.56 |
| GPU Runtime | N/A |
| QPU Runtime | N/A |
| Other HW Runtime | N/A |
| ====== |  |
| Remarks | CPU Runtime is Gurobi Work Measure, Success Threshold is the MIP Gap tolerance, variable counts are after presolve, Coefficient Range is (Min - Max) for (Linear, Quadratic, Quadratic Linear) coefficients |

# Submission for topology_20_3

This directory contains the submission for the problem **topology_20_3**.

| Field | Value 1 |
| --- | --- |
| Problem | topology_20_3 |
| Submitter | Maximilian Schicker |
| Affiliation | Zuse Institute Berlin |
| Date | 2024-12-06 |
| ====== |  |
| Reference | See Models Directory (Seidel-Quadratic) using Gurobi 11.0.0 |
| Best Objective Value | 3.0 |
| Optimality Bound | 3.0 |
| ====== |  |
| Modeling Approach | Binary Quadratic Program |
| # Decision Variables | 11021 |
| # Binary Variables | 11020 |
| # Integer Variables | 1 |
| # Continuous Variables | 0 |
| # Non-Zero Coefficients | 1330 |
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
| Hardware Specifications | Intel(R) Xeon(R) Gold 6338 CPU @ 2.00GHz, instruction set [SSE2\|AVX\|AVX2\|AVX512] |
| ====== |  |
| Total Runtime | 61.94 |
| Time to Solution | 61 |
| CPU Runtime | 81.07 |
| GPU Runtime | N/A |
| QPU Runtime | N/A |
| Other HW Runtime | N/A |
| ====== |  |
| Remarks | CPU Runtime is Gurobi Work Measure, Success Threshold is the MIP Gap tolerance, variable counts are after presolve, Coefficient Range is (Min - Max) for (Linear, Quadratic, Quadratic Linear) coefficients |

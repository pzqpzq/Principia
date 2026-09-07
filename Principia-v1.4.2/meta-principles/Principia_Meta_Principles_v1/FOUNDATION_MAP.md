# Foundation Relation Map

The corpus contains **147 curated relation seeds**. They are navigation and reasoning aids, not automatic evidence propagation.

## Highest-connectivity foundations

| Meta-Principle | Area | In | Out | Total |
| --- | --- | ---: | ---: | ---: |
| `meta:foundations:measurement-validity` — Measurement Validity Precedes Numerical Precision | `foundations` | 6 | 1 | 7 |
| `meta:foundations:uncertainty-propagation` — Uncertainty Must Propagate Through the Full Reasoning Chain | `foundations` | 4 | 2 | 6 |
| `meta:foundations:scale-separation` — Explanations Are Conditional on Scale | `foundations` | 4 | 2 | 6 |
| `meta:foundations:transportability` — Generalization Requires Invariance Across Environments | `foundations` | 4 | 1 | 5 |
| `meta:foundations:resource-bounded-inference` — All Inference Is Resource-Bounded | `foundations` | 3 | 2 | 5 |
| `meta:ai-ml:information-bottleneck` — Useful Representations Preserve Task Information While Discarding Nuisance Detail | `ai-ml` | 3 | 2 | 5 |
| `meta:medicine-epidemiology:external-validity-transport` — Trial Efficacy Does Not Automatically Transport to New Patients or Settings | `medicine-epidemiology` | 3 | 1 | 4 |
| `meta:information-control-complexity:modularity-hierarchy` — Nearly Decomposable Modules Enable Complexity to Scale | `information-control-complexity` | 3 | 1 | 4 |
| `meta:information-control-complexity:bode-sensitivity` — Feedback Improvement in One Frequency Range Is Paid for Elsewhere | `information-control-complexity` | 3 | 1 | 4 |
| `meta:engineering-optimization:verification-validation-uncertainty` — Verification, Validation, and Uncertainty Quantification Answer Different Questions | `engineering-optimization` | 3 | 1 | 4 |
| `meta:mathematics-logic:variational-principle` — Global or Local Extremality Can Generate Governing Equations | `mathematics-logic` | 2 | 2 | 4 |
| `meta:statistics-causality:exchangeability` — Causal Comparison Requires Exchangeability or a Design Substitute | `statistics-causality` | 3 | 0 | 3 |
| `meta:information-control-complexity:tipping-hysteresis` — Positive Feedback Can Create Thresholds, Alternative States, and Hysteresis | `information-control-complexity` | 3 | 0 | 3 |
| `meta:engineering-optimization:redundancy-common-cause` — Redundancy Improves Reliability Only When Failure Modes Are Sufficiently Independent | `engineering-optimization` | 3 | 0 | 3 |
| `meta:engineering-optimization:modularity-interfaces` — Modularity Localizes Change Only When Interfaces Encapsulate Volatile Decisions | `engineering-optimization` | 3 | 0 | 3 |
| `meta:computer-science:computability-boundary` — Some Well-Posed Computational Questions Are Undecidable | `computer-science` | 3 | 0 | 3 |
| `meta:statistics-causality:calibration` — Probabilistic Predictions Must Match Long-Run Frequencies in Their Reference Class | `statistics-causality` | 2 | 1 | 3 |
| `meta:physics:free-energy-minimization` — Equilibrium Minimizes the Appropriate Thermodynamic Potential | `physics` | 2 | 1 | 3 |
| `meta:neuroscience-cognition:efficient-coding` — Sensory Systems Adapt Codes to Input Statistics and Resource Constraints | `neuroscience-cognition` | 2 | 1 | 3 |
| `meta:medicine-epidemiology:heterogeneous-treatment-effects` — Average Treatment Effects Can Conceal Clinically Important Effect Heterogeneity | `medicine-epidemiology` | 2 | 1 | 3 |
| `meta:mathematics-logic:halting-undecidability` — No General Algorithm Decides Whether Arbitrary Programs Halt | `mathematics-logic` | 2 | 1 | 3 |
| `meta:mathematics-logic:fixed-point` — Self-Consistent States Arise as Fixed Points of Mappings | `mathematics-logic` | 2 | 1 | 3 |
| `meta:information-control-complexity:rate-distortion` — Lossy Compression Has a Fundamental Rate–Fidelity Frontier | `information-control-complexity` | 2 | 1 | 3 |
| `meta:foundations:mechanism-prediction-distinction` — Predictive Success and Mechanistic Truth Are Different Achievements | `foundations` | 2 | 1 | 3 |
| `meta:engineering-optimization:pareto-frontier` — Conflicting Objectives Produce a Pareto Frontier Rather Than a Single Universal Optimum | `engineering-optimization` | 2 | 1 | 3 |
| `meta:foundations:parsimony-mdl` — Parsimony as Minimum Description Length | `foundations` | 1 | 2 | 3 |
| `meta:foundations:causation-intervention` — Causal Claims Concern Intervention, Not Association Alone | `foundations` | 1 | 2 | 3 |
| `meta:statistics-causality:likelihood-and-evidence` — Likelihood Measures Relative Support Within a Statistical Model | `statistics-causality` | 2 | 0 | 2 |
| `meta:mathematics-logic:invariance` — Invariants Reveal Structure Independent of Representation | `mathematics-logic` | 2 | 0 | 2 |
| `meta:foundations:triangulation` — Convergent Evidence Across Methods Is Stronger Than Repetition Within One Bias Structure | `foundations` | 2 | 0 | 2 |

## Relation policy

- Edges are typed and directional.
- A relation never copies maturity or truth status from parent to child.
- `analogous_to` carries structure, not evidence.
- `depends_on` and `specializes` require boundary compatibility.
- `contradicts` requires overlapping scope and credible counterevidence.
- New relations should preserve their own provenance and review status.

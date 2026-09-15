# Principia-100 evaluation protocol · v0.1.1

Status: owner-accepted public protocol. It defines future evaluation; no discovery runs, system comparisons or scores accompany the corpus release.

## Purpose and admissible claims

Principia-100 is an open, source-aware research corpus for investigating quantitative relationships from heterogeneous local data. It is not a collection of 100 unknown ground-truth laws. Publication titles, author analyses, figures, annotations and sometimes fitted models occur in source assets. The first 20 original cases were used during Principia development; replacement case 05 has a separate revision and exposure record. Report source access and model training-data uncertainty. Do not label the corpus blind or unseen.

Three outcomes are distinct:

1. **Reproduction:** recover, independently check or falsify a previously published relationship. Cite that relationship and record what was already accessible.
2. **Validated extension:** demonstrate a scoped quantitative relationship beyond the disclosed source result on appropriate held-out groups/conditions, with uncertainty and fair comparisons. This does not by itself establish novelty.
3. **Novelty candidate:** a validated extension that additionally survives documented, dated literature review and independent scientific adjudication. The term is provisional until expert review.

A justified abstention, failed fit, missing identifiability, source inconsistency or falsified relationship is a valid scientific outcome. Do not manufacture a positive rule for every case.

## Inputs and exposure

`INPUT_ALLOWLIST.json` names each case's allowed files by exact relative path and SHA-256. Source archives remain intact; their full member inventories are exposed, including author code, labels and fitted outputs. This is intentionally source-aware. Evaluation must record which members were read and any external sources consulted. Never execute publisher code merely because it is present.

Only the neutral case brief and approved source assets are scenario inputs. Collection task cards, reviewer guidance, prior evaluation output, proposed equation families and other participants' submissions are outside the input allowlist. A future blinded or measurement-only track requires a separately frozen member-level input manifest and expert audit; this release does not claim one.

## Preregister a case-specific evaluation

Before fitting, freeze the case/asset hashes, allowed external resources, software/model versions, random seeds, compute budget, variables/units, primary target, exclusions justified by source quality flags, baseline family, validation groups, uncertainty procedure and stopping criteria. Preserve the original data and place all derived transformations in a separate run directory. Report each transformation, fit scope and learned preprocessing parameter.

Use the grouping design in the task card as a starting constraint, then verify actual identifiers. Hold out donors, animals, devices, cultivation pairs, laboratories, sites, graph instances or entire runs as applicable. Repeated pixels, cells, time samples, rounds or calls are not automatically independent. Linked modalities and alternate representations remain in the same partition. Fit normalization, feature selection, segmentation and calibration adjustments using development data only.

For small group counts, use leave-one-group-out or nested grouped validation when justified and report its uncertainty honestly. Do not reserve a nominal locked test with insufficient independent units. Single-device, single-patient, single-event and single-field cases support bounded within-system validation only. Temporal evaluations need chronological partitions and dependence-aware guard intervals. Spatial evaluations need blocks large enough to address autocorrelation. Survey evaluations need design weights, appropriate variance estimation, missingness/imputation handling and proficiency plausible values where supplied. Exact mathematics requires independent certificate/proof checking and counterexample search rather than pseudo-statistical sample replication.

Freeze a locked test or prospective external validation before the final claim where feasible. Never tune on its results. If only retrospective source data are available, label that limitation. Validation partition counts and exclusions are outputs to report, not fabricated curator ground truth.

## Required submission

Use `schemas/SUBMISSION.schema.json`. Each proposed rule must include:

- An executable, unambiguous mathematical expression or program, all symbols, units and coordinate conventions, parameter estimates and uncertainty, and the supported domain/range.
- Exact evidence anchors: source SHA-256, archive member, sample/group IDs, time intervals and table/sheet/column references. Derived artifacts include their code and lineage.
- A mechanistic interpretation or a clearly labeled empirical relationship, assumptions, identifiability constraints and observable counterexamples.
- Baselines evaluated on identical groups, targets, preprocessing access and budgets. Include constant/stratified predictors, relevant established physical/statistical models, and simple flexible alternatives as appropriate. A unit conversion, accounting identity, leaked source fit or renamed target is not an extension.
- Held-out performance with group-aware uncertainty, effect size, calibration or residual diagnostics, sensitivity to plausible missingness/calibration choices, and robustness to conditions within the claimed scope.
- Falsifying controls, negative results, failed configurations, censored/time-out runs and restrictions on extrapolation. Preserve unfavorable evidence.
- Prior-art classification and citations, external-source access log, resource use and enough code/configuration to reproduce the analysis.

An equation with dimensionless normalized variables must still define its normalization and restore a physical interpretation. Symbolic brevity alone is not evidence. Observational correlations do not establish causal mechanisms, clinical utility or industrial deployment readiness.

## Adjudication and reporting

Two domain-appropriate reviewers should independently assess source fidelity, leakage, mathematical validity, validation independence, uncertainty, practical relevance and novelty status; resolve disagreements explicitly. Reviewer equation families are examples, not expected answers. Require independent verification of executable outputs in a disposable environment with declared dependencies.

Report per-case outcomes and evidence, stratified by discipline, modality, data origin and validation scope. Do not collapse heterogeneous cases into a universal discovery score or call the fraction of positive-looking statements a success rate. Any later scoring rubric, cost comparison, benchmark split or leaderboard requires a separately versioned preregistration. Corpus acceptance certifies usable, authentic inputs and documented limits; it is not scientific validation of a new principle.

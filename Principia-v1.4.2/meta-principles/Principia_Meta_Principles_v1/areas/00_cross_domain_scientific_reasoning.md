# Cross-Domain Scientific Reasoning: Meta-Principles

This file contains 21 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `foundations`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:foundations:falsifiability — Falsifiability and Risky Prediction

- **Epistemic type:** `methodological principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `epistemology`, `falsification`, `testing`, `risk`

### Argument & interpretation

A scientific claim gains evidential force when it rules out observable possibilities. The more precisely a claim states what would count against it, the more sharply evidence can discriminate it from alternatives. In Principia, this means that a Principle should expose a challenge, failure condition, or counterexample path rather than only a persuasive interpretation.

### Boundary & conditions

- Falsifiability is not a complete demarcation criterion: probabilistic, historical, and model-based sciences often test systems of assumptions rather than isolated sentences.
- A failed prediction may implicate auxiliary assumptions, measurement error, or implementation rather than the focal claim alone.
- Mathematical definitions and axioms are assessed by consistency and consequences, not direct empirical falsification.

### Application

- hypothesis design
- benchmark construction
- experimental planning
- Principle challenge policies
- scientific agent evaluation

### Basics

Karl Popper developed falsifiability as a central account of scientific testing in the 1930s, especially in *The Logic of Scientific Discovery*. Later philosophy of science emphasized auxiliary assumptions and the difference between simple refutation and theory revision.

### Paper / work evidence

- **Foundation:** [The Logic of Scientific Discovery](https://www.routledge.com/The-Logic-of-Scientific-Discovery/Popper/p/book/9780415278447) (1934)
- **Refinement:** [The Methodology of Scientific Research Programmes](https://doi.org/10.1017/CBO9780511621123) (1978)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Use this as a demand for explicit risk, not as a mechanical binary classifier of science. Overly narrow tests can reward superficial benchmark compliance, while overly broad claims can evade meaningful challenge.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `26016d250767021709ace3d1e1be1fa4db3e2f58b189ff2119501a5072d264c3`</sub>

---

## meta:foundations:bayesian-updating — Bayesian Updating Under Explicit Priors

- **Epistemic type:** `theorem-backed inference principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `bayes`, `uncertainty`, `inference`, `sequential`

### Argument & interpretation

When hypotheses $H$ and evidence $E$ are represented probabilistically, rational updating follows $P(H\mid E) \propto P(E\mid H)P(H)$. Evidence changes belief through its likelihood under competing hypotheses, while prior commitments remain visible. The principle supports cumulative inference and makes disagreement traceable to priors, likelihoods, or model structure.

### Boundary & conditions

- Bayesian updating is only as reliable as the hypothesis space, likelihood model, and prior specification.
- Posterior concentration can be misleading under model misspecification or unrecognized dependence.
- Not every uncertainty is well represented by a single precise probability distribution.

### Application

- scientific inference
- model comparison
- sequential experimentation
- uncertainty-aware agents
- diagnosis and forecasting

### Basics

Thomas Bayes's posthumous 1763 essay and Laplace's later development established inverse probability. Twentieth-century Bayesian statistics clarified subjective, objective, and decision-theoretic interpretations.

### Paper / work evidence

- **Foundation:** [An Essay towards Solving a Problem in the Doctrine of Chances](https://doi.org/10.1098/rstl.1763.0053) (1763)
- **Refinement:** [Theory of Probability](https://global.oup.com/academic/product/theory-of-probability-9780198503682) (1939)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Bayesian coherence does not guarantee empirical adequacy. Principia should retain prior and model provenance and avoid presenting a posterior as a model-free probability of truth.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `31d1a0231c56cd94536a5a39b5053fc43e29d39bba8a4198377211d9e7f11af5`</sub>

---

## meta:foundations:underdetermination — Evidence Underdetermines Explanatory Theory

- **Epistemic type:** `epistemic proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `underdetermination`, `identifiability`, `alternatives`, `model-pluralism`

### Argument & interpretation

Finite observations commonly admit multiple explanations. A dataset constrains a space of models; it rarely identifies one interpretation without auxiliary assumptions, interventions, invariances, or additional measurements. Meta-level reasoning should therefore compare alternatives and preserve unresolved equivalence classes rather than collapsing immediately to one narrative.

### Boundary & conditions

- Some formal or experimental designs can identify a unique answer within a declared model class.
- Underdetermination concerns evidence relative to assumptions; it does not imply that all explanations are equally good.
- Strong mechanistic constraints, interventions, or new measurement modalities can break equivalence.

### Application

- causal discovery
- inverse problems
- model selection
- theory construction
- scientific debate

### Basics

Pierre Duhem emphasized that physical hypotheses are tested within theoretical systems; W. V. O. Quine generalized related holist arguments. Modern statistics expresses the issue through identifiability and observational equivalence.

### Paper / work evidence

- **Foundation:** [The Aim and Structure of Physical Theory](https://press.princeton.edu/books/paperback/9780691120269/the-aim-and-structure-of-physical-theory) (1906)
- **Refinement:** [Two Dogmas of Empiricism](https://doi.org/10.2307/2181906) (1951)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

The risk is sliding from justified humility into relativism. Principia should rank alternatives by evidence, scope, simplicity, and challenge performance while retaining credible competitors.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `91de8c2c03d00478af208854ed0f47aa0c915251bd4fefc53d05fe50ebf9be07`</sub>

---

## meta:foundations:parsimony-mdl — Parsimony as Minimum Description Length

- **Epistemic type:** `formalized heuristic`
- **Principia kind:** `theorem`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `parsimony`, `mdl`, `compression`, `model-selection`

### Argument & interpretation

Among models that explain the evidence comparably well, prefer the one minimizing total description cost: model specification plus residual or data encoding cost. In MDL form, select $M$ to minimize $L(M)+L(D\mid M)$. This makes simplicity conditional on predictive compression rather than on visual elegance alone.

### Boundary & conditions

- The coding language and model class affect description length.
- A simpler but misspecified model should not defeat a more complex model with materially better predictive or causal adequacy.
- One-off irregularities may be incompressible; forcing simple laws can erase genuine heterogeneity.

### Application

- model selection
- symbolic regression
- scientific dialects
- theory compression
- regularization

### Basics

Occam's razor is medieval in origin, but modern statistical formalizations include Solomonoff induction, Kolmogorov complexity, and Jorma Rissanen's minimum-description-length principle from the late 1970s.

### Paper / work evidence

- **Foundation:** [Modeling by Shortest Data Description](https://doi.org/10.1016/0005-1098(78)90005-5) (1978)
- **Refinement:** [A Universal Prior for Integers and Estimation by Minimum Description Length](https://doi.org/10.1214/aos/1176344136) (1983)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

MDL is powerful for Principia because Meta-Principles should compress many specific Principles. However, compression must preserve evidence anchors and boundary conditions; otherwise short representations become opaque labels.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c6ac020bb2d0d713c28610eadb4d69821165853c0c5c1a22c706fdcbb0d55e5b`</sub>

---

## meta:foundations:replication-independence — Independent Replication Separates Stable Effects from Local Artifacts

- **Epistemic type:** `empirical-method principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `replication`, `reproducibility`, `independence`, `external-validity`

### Argument & interpretation

A result becomes more credible when it recurs under genuinely independent samples, investigators, instruments, sites, or implementations. Replication tests whether a Principle survives changes in incidental conditions and helps reveal hidden dependencies in the original scope.

### Boundary & conditions

- Exact replication may be impossible for historical or unique events; triangulation then substitutes partially.
- A failed replication can reflect low power, procedural differences, population shift, or genuine context dependence.
- Repeated analyses of the same underlying data are not independent replications.

### Application

- experimental science
- software benchmarks
- multi-site studies
- industrial process validation
- Principle maturity updates

### Basics

Replication has long been part of experimental method. Large coordinated projects in psychology, cancer biology, economics, and other fields have made reproducibility failures and context sensitivity quantitatively visible.

### Paper / work evidence

- **Foundation:** [Estimating the Reproducibility of Psychological Science](https://doi.org/10.1126/science.aac4716) (2015)
- **Synthesis:** [Reproducibility of Scientific Results](https://doi.org/10.17226/25303) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Replication should update scope, not merely trigger a binary pass/fail. Principia should record protocol distance and evidence independence so that ten correlated studies do not masquerade as ten independent confirmations.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `2e5ad7120e15d4e1fa07ae66905f7c7eaf3933adb0454e35979cf06ba7cc5738`</sub>

---

## meta:foundations:randomization-controls — Randomization and Controls Break Systematic Alternative Explanations

- **Epistemic type:** `design principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `randomization`, `controls`, `causality`, `experimental-design`

### Argument & interpretation

Random assignment makes treatment allocation independent of potential outcomes in expectation, while control conditions estimate what would have happened without the intervention. Together they convert many confounding threats into quantifiable sampling uncertainty and support causal comparison.

### Boundary & conditions

- Randomization does not fix noncompliance, attrition, interference, measurement bias, or poor implementation.
- Ethical, logistical, or physical constraints may make randomization impossible.
- Small randomized studies can remain imbalanced and underpowered; design and analysis must reflect the assignment mechanism.

### Application

- clinical trials
- A/B testing
- agricultural experiments
- algorithm evaluation
- industrial experimentation

### Basics

R. A. Fisher systematized randomization, blocking, and analysis of variance in agricultural experiments during the 1920s and 1930s. Randomized clinical trials later adapted the logic to medicine.

### Paper / work evidence

- **Foundation:** [The Design of Experiments](https://archive.org/details/designofexperime00fish) (1935)
- **Application:** [Streptomycin Treatment of Pulmonary Tuberculosis](https://doi.org/10.1136/bmj.2.4582.769) (1948)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Randomization is a design property, not a ceremonial label. Principia should link causal claims to the actual assignment mechanism and distinguish randomized encouragement, cluster randomization, and observational controls.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `fda0d039e28e065419b69e17f43735653ec9250ea398f946d83f7b2cfdef05a2`</sub>

---

## meta:foundations:measurement-validity — Measurement Validity Precedes Numerical Precision

- **Epistemic type:** `measurement principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `measurement`, `validity`, `calibration`, `constructs`

### Argument & interpretation

A number is informative only if the measurement operation tracks the intended construct with adequate reliability, resolution, calibration, and invariance. Precision in computation cannot repair a variable that changes meaning across instruments, populations, or time.

### Boundary & conditions

- Operational definitions may be task-specific; no single measure captures every aspect of a complex construct.
- Reliable measurements can be systematically invalid, and valid group-level measures can fail at the individual level.
- Measurement itself can perturb the system.

### Application

- sensor systems
- psychometrics
- benchmark design
- clinical endpoints
- scientific data integration

### Basics

Measurement theory developed through metrology, psychophysics, and statistics. S. S. Stevens's 1946 typology of scales influenced social science; modern validity theory treats validation as an argument supported by multiple evidence sources.

### Paper / work evidence

- **Foundation:** [On the Theory of Scales of Measurement](https://doi.org/10.1126/science.103.2684.677) (1946)
- **Refinement:** [Standards for Educational and Psychological Testing](https://www.testingstandards.net/open-access-files.html) (2014)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Metric availability creates a temptation to substitute the measured proxy for the real objective. Every Principia Principle should preserve units, calibration state, construct definition, and known measurement invariances.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `760e91203842d2554d23ff897daa657b4f9cc684808e405524e06c5ced1e7ed4`</sub>

---

## meta:foundations:uncertainty-propagation — Uncertainty Must Propagate Through the Full Reasoning Chain

- **Epistemic type:** `quantitative principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `uncertainty`, `propagation`, `uql`, `measurement`

### Argument & interpretation

When outputs $y=f(x,\theta)$ depend on uncertain measurements, parameters, and models, uncertainty in $y$ must reflect those inputs and their dependence. For local linear propagation, $\Sigma_y\approx J\Sigma_xJ^\top$; nonlinear or multimodal systems may require simulation or interval methods.

### Boundary & conditions

- Linear error propagation fails for strong nonlinearity, discontinuity, heavy tails, or poorly identified models.
- Model-form uncertainty is often larger than parameter uncertainty and cannot be captured by standard errors alone.
- Unknown unknowns are not converted into quantified risk merely by adding a distribution.

### Application

- metrology
- simulation
- forecasting
- uncertainty quantification
- risk-sensitive decision systems

### Basics

Classical error analysis developed with measurement science; the modern Guide to the Expression of Uncertainty in Measurement standardized vocabulary and propagation practices, while computational UQ extended them to complex models.

### Paper / work evidence

- **Foundation:** [Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement](https://www.bipm.org/en/committees/jc/jcgm/publications) (2008)
- **Refinement:** [Verification, Validation, and Uncertainty Quantification](https://doi.org/10.1017/CBO9780511760396) (2010)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should distinguish measurement, sampling, parameter, structural, and scenario uncertainty. Collapsing them into one confidence score obscures where new evidence would be most valuable.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `9f7612cd478a5ca5f16fa4536d7685f0acb6e9fd2544ca5a2f94496e921481fd`</sub>

---

## meta:foundations:multiple-testing-selection — Search Multiplicity Inflates Apparent Discovery

- **Epistemic type:** `statistical principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `multiplicity`, `selection-bias`, `fdr`, `discovery`

### Argument & interpretation

If many hypotheses, models, transformations, or subgroups are searched, some will appear successful by chance. Valid inference must account for the selection process through holdouts, multiplicity control, selective inference, preregistration, or independent confirmation.

### Boundary & conditions

- Multiplicity corrections depend on the error criterion and dependence structure.
- Exploratory analysis remains valuable when labelled exploratory and followed by confirmation.
- Overly conservative control can suppress weak but real effects in high-dimensional discovery.

### Application

- automated discovery
- benchmark tuning
- genomics
- subgroup search
- symbolic regression

### Basics

Family-wise error control developed with Bonferroni and related procedures; Benjamini and Hochberg introduced false-discovery-rate control in 1995. Modern selective inference treats model search itself as part of the data-generating process.

### Paper / work evidence

- **Foundation:** [Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) (1995)
- **Refinement:** [Exact Post-Selection Inference, with Application to the Lasso](https://doi.org/10.1214/14-AOS1232) (2016)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

This is central to autonomous discovery: an agent that tries thousands of candidate Principles must not report the winner as though it were prespecified. Search history is evidence metadata.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `fe8bcee3dde10eb688441064a8110c1a0e2356e10cc5fc015a099a0216e72de4`</sub>

---

## meta:foundations:robustness-sensitivity — A Principle Is Credible Only Across Plausible Perturbations

- **Epistemic type:** `methodological principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `robustness`, `sensitivity`, `multiverse`, `stability`

### Argument & interpretation

A claimed relation should survive reasonable changes in preprocessing, sample composition, nuisance assumptions, parameterization, and measurement error. Sensitivity analysis maps which conclusions are stable and which depend on fragile analytical choices.

### Boundary & conditions

- Robustness to arbitrary perturbations is impossible and may conflict with efficiency.
- A stable wrong model remains wrong; robustness complements rather than replaces external validity and mechanism checks.
- Perturbations must be scientifically plausible, not chosen only to preserve the result.

### Application

- model validation
- causal sensitivity
- industrial rules
- simulation studies
- LLM evaluation

### Basics

Robust statistics, engineering sensitivity analysis, and specification-curve methods developed distinct approaches to perturbation. Contemporary multiverse analysis makes analytical choice dependence visible.

### Paper / work evidence

- **Foundation:** [Robust Statistics: The Approach Based on Influence Functions](https://onlinelibrary.wiley.com/doi/book/10.1002/0471725250) (1986)
- **Application:** [Specification Curve: Descriptive and Inferential Statistics on All Reasonable Specifications](https://doi.org/10.1177/2515245917747646) (2020)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should store a robustness profile rather than one score. A Principle may be robust to sampling yet fragile to measurement definition or population shift.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `28ac3f0d8c91958f96697a5c426cd5083ad84e36390c32f3cdc963cd9680de33`</sub>

---

## meta:foundations:transportability — Generalization Requires Invariance Across Environments

- **Epistemic type:** `causal-inference proposition`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `transportability`, `invariance`, `domain-shift`, `external-validity`

### Argument & interpretation

Evidence transports from a source environment to a target only through mechanisms or conditional distributions that remain invariant, together with measured differences that can be adjusted. Similarity of labels or variables is not enough; the transport assumptions must be explicit.

### Boundary & conditions

- No purely observational procedure can guarantee transfer under unrestricted distribution shift.
- An invariant predictor may still fail if measurement, intervention, or support changes.
- Transportability can be partial: mechanisms may transfer while baseline rates or effect magnitudes do not.

### Application

- domain adaptation
- multi-site science
- policy transfer
- clinical generalization
- industrial deployment

### Basics

External validity was long treated informally. Pearl and Bareinboim developed formal transportability criteria using causal diagrams; machine learning studies characterize which shifts can be handled under specified assumptions.

### Paper / work evidence

- **Foundation:** [External Validity: From Do-Calculus to Transportability Across Populations](https://doi.org/10.1214/14-STS486) (2014)
- **Application:** [Domain Adaptation under Target and Conditional Shift](https://proceedings.mlr.press/v97/wu19f.html) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

A Meta-Principle should not become universal merely because several papers use similar language. Principia should represent source and target environments and the exact invariance invoked.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `03e4047c4c561df47577caaf7f2e3b4c38fe80110ab4bf45428877a0b22f537e`</sub>

---

## meta:foundations:causation-intervention — Causal Claims Concern Intervention, Not Association Alone

- **Epistemic type:** `causal principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `causality`, `intervention`, `counterfactuals`, `identification`

### Argument & interpretation

A causal claim states how an outcome would change under an intervention, not merely how variables co-vary. In structural form, the distinction is between observing $X=x$ and setting $do(X=x)$. Identification requires assumptions connecting observed data to counterfactual or interventional quantities.

### Boundary & conditions

- Some causal effects are not identifiable from available data.
- Interventions may be ill-defined, compound, or infeasible.
- Mechanistic causation can require richer temporal and process models than average treatment effects.

### Application

- causal discovery
- policy analysis
- mechanistic science
- clinical treatment
- root-cause analysis

### Basics

Potential-outcome approaches were developed by Neyman and Rubin; structural causal models and do-calculus were systematized by Judea Pearl and others. Both frameworks emphasize explicit assumptions.

### Paper / work evidence

- **Foundation:** [Causal Diagrams for Empirical Research](https://doi.org/10.1093/biomet/82.4.669) (1995)
- **Foundation:** [Estimating Causal Effects of Treatments in Randomized and Nonrandomized Studies](https://doi.org/10.1037/h0037350) (1974)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

LLMs readily convert temporal order or correlation into causal prose. Principia should gate causal relation types and preserve the intervention definition, adjustment logic, and sensitivity to violations.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3b1f441939cbcfd657c5a641c0fda19a5c9e7c9e2514a4483fc54f5316484b2b`</sub>

---

## meta:foundations:model-pluralism — Different Models Trade Realism, Generality, and Precision

- **Epistemic type:** `methodological observation`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `model-pluralism`, `tradeoff`, `ensembles`, `abstraction`

### Argument & interpretation

Complex systems are often understood through several models that preserve different mechanisms or scales. A single model rarely maximizes realism, generality, and precision simultaneously; convergent implications across structurally different models are especially informative.

### Boundary & conditions

- Pluralism is not permission to retain models contradicted in their intended scope.
- Some tasks do admit a demonstrably superior model under a declared loss and data regime.
- Combining models can hide incompatible assumptions unless contrasts are explicit.

### Application

- ecology
- climate modeling
- economics
- machine learning ensembles
- multiscale physics

### Basics

Richard Levins articulated the realism–generality–precision trade-off in population biology in 1966. Ensemble and multimodel methods later operationalized parts of the idea across fields.

### Paper / work evidence

- **Foundation:** [The Strategy of Model Building in Population Biology](https://doi.org/10.1086/282079) (1966)
- **Refinement:** [The Truth Is the Whole](https://doi.org/10.1086/652964) (2010)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should preserve model family and abstraction level. Agreement between models with shared assumptions is weaker evidence than agreement between genuinely independent representations.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0182ce129c890cc0637376d65d8e144218ba51e003e57111086c90b06ad2bd04`</sub>

---

## meta:foundations:scale-separation — Explanations Are Conditional on Scale

- **Epistemic type:** `cross-domain principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `scale`, `coarse-graining`, `emergence`, `effective-theory`

### Argument & interpretation

Different variables and laws become useful at different spatial, temporal, and organizational scales. Coarse-graining can suppress microscopic detail while preserving relevant macroscopic behavior; conversely, a macroscopic law need not specify every lower-level mechanism.

### Boundary & conditions

- Scale separation may be weak near critical points, across tightly coupled levels, or in finite heterogeneous systems.
- Coarse-graining can erase rare events, path dependence, or causal structure.
- Emergent regularities do not imply that lower-level constraints are irrelevant.

### Application

- effective theories
- multiscale simulation
- biology
- materials
- organizational science

### Basics

Statistical mechanics, homogenization, and effective field theory formalized scale-dependent descriptions. Renormalization-group theory showed why distinct microscopic systems can share macroscopic behavior.

### Paper / work evidence

- **Foundation:** [More Is Different](https://doi.org/10.1126/science.177.4047.393) (1972)
- **Formalization:** [The Renormalization Group and the $\epsilon$ Expansion](https://doi.org/10.1016/0370-1573(74)90023-4) (1974)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

This Meta-Principle is a key parent for paper-level laws. Principia should ask at what scale a claim is closed and whether variables from different levels have been mixed without a coupling model.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `4f0c826c3eab950dc98761ef2ded5333efea26e67072759aa6862558e6f8c985`</sub>

---

## meta:foundations:goodhart-proxy — Optimized Proxies Cease to Behave Like Passive Measures

- **Epistemic type:** `socio-technical principle`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `goodhart`, `proxies`, `incentives`, `metric-gaming`

### Argument & interpretation

When a proxy becomes a target, agents adapt to the proxy and can break its relationship with the underlying objective. Optimization changes the data-generating process: $\operatorname*{argmax}$ over a noisy measure selects both signal and exploitable error.

### Boundary & conditions

- Proxy failure is not inevitable if incentives, audits, and causal alignment are strong.
- The severity depends on strategic adaptation, measurement noise, and optimization pressure.
- Multiple complementary measures can reduce but not eliminate gaming.

### Application

- AI reward design
- benchmarking
- policy metrics
- organizational management
- scientific incentives

### Basics

Charles Goodhart formulated the monetary-policy observation in the 1970s; Donald Campbell articulated a related social-indicator principle. Later work classified regressional, extremal, causal, and adversarial forms of Goodhart effects.

### Paper / work evidence

- **Foundation:** [Problems of Monetary Management: The U.K. Experience](https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/1975/problems-of-monetary-management-the-uk-experience.pdf) (1975)
- **Refinement:** [Goodhart’s Law: Its Origins, Meaning and Implications for Monetary Policy](https://doi.org/10.1007/978-1-349-17295-5_5) (1984)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should treat metrics as interventions on behavior, especially when recommendations will be deployed. A highly predictive metric in passive data may become unreliable after optimization begins.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `e193afe5eb9b6ff7997b5377384a47809aa3cbe072bd09275dfe945a4a542203`</sub>

---

## meta:foundations:negative-evidence-asymmetry — Absence of Evidence Is Not Uniformly Evidence of Absence

- **Epistemic type:** `inference proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `null-results`, `power`, `equivalence`, `negative-evidence`

### Argument & interpretation

A non-detection weakens a hypothesis only to the extent that the study had a high probability of detecting the predicted effect. The evidential value of a null result depends on power, measurement sensitivity, model specification, and the range of alternatives considered.

### Boundary & conditions

- A precise, high-powered null result can strongly constrain effect sizes.
- Failure to reject a null is not equivalent to accepting it without an equivalence or Bayesian analysis.
- Publication and reporting bias can make the observed collection of nulls unrepresentative.

### Application

- null results
- anomaly search
- clinical trials
- particle physics
- software testing

### Basics

The distinction follows classical power analysis and was popularized in evidence-based medicine. Equivalence and non-inferiority testing provide formal ways to support bounded absence claims.

### Paper / work evidence

- **Foundation:** [Absence of Evidence Is Not Evidence of Absence](https://doi.org/10.1136/bmj.311.7003.485) (1995)
- **Refinement:** [Equivalence and Noninferiority Testing in Psychology](https://doi.org/10.1177/2515245918770963) (2018)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should store detection limits and smallest effects of interest. A paper saying “no significant difference” is not itself a Meta-Principle about no effect.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `759d481b563d33c30f2cd084e63a42c37d77795ffe0f596d82d5ad19fcd48a5c`</sub>

---

## meta:foundations:mechanism-prediction-distinction — Predictive Success and Mechanistic Truth Are Different Achievements

- **Epistemic type:** `epistemic principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `prediction`, `mechanism`, `explanation`, `causality`

### Argument & interpretation

A model can predict accurately using stable correlations while misrepresenting causal mechanism, and a mechanistic model can be scientifically informative without maximizing short-term predictive accuracy. Claims should distinguish forecasting, explanation, control, and intervention.

### Boundary & conditions

- In well-specified systems, predictive and mechanistic adequacy can reinforce each other.
- Mechanistic language may be layered and approximate rather than uniquely true.
- Poor prediction can still falsify a mechanism when prediction is a declared consequence.

### Application

- machine learning
- systems biology
- econometrics
- climate science
- scientific explanation

### Basics

Twentieth-century philosophy and statistics distinguished explanation from curve fitting; contemporary causal inference and interpretable machine learning renewed the issue as high-capacity predictors became common.

### Paper / work evidence

- **Foundation:** [Statistical Modeling: The Two Cultures](https://doi.org/10.1214/ss/1009213726) (2001)
- **Refinement:** [To Explain or to Predict?](https://doi.org/10.1214/10-STS330) (2010)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should not promote predictive feature importance to mechanism. A Principle Capsule should say whether its evidence supports association, prediction, intervention, or process-level explanation.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `4276587b14865c283ae953010a4f7fb5cebe4298c02de86e8f2c4076e1c956b2`</sub>

---

## meta:foundations:boundary-first-generalization — A Scientific Law Includes Its Domain of Validity

- **Epistemic type:** `meta-scientific principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `scope`, `boundary`, `validity-domain`, `generalization`

### Argument & interpretation

A Principle is not only a relation but a relation plus the conditions under which it is expected to hold. Boundary statements—regimes, populations, scales, interventions, exclusions, and failure modes—are part of the scientific content, not optional caveats.

### Boundary & conditions

- Some foundational axioms deliberately define idealized unlimited domains.
- Unknown boundaries remain possible even after broad replication.
- Overly conservative boundaries can make a claim uninformative and prevent useful transfer.

### Application

- Principle extraction
- knowledge graphs
- theory comparison
- engineering rules
- policy transfer

### Basics

Domain-of-validity reasoning is intrinsic to physical effective theories, statistical external validity, biological context dependence, and engineering design envelopes. Modern model cards and data sheets make similar scope contracts explicit for AI systems.

### Paper / work evidence

- **Foundation:** [The Effective Field Theory Treatment of Quantum Gravity](https://doi.org/10.1063/1.531335) (1994)
- **Application:** [Model Cards for Model Reporting](https://doi.org/10.1145/3287560.3287596) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

This is the organizing rule for the corpus. New Principles should link to Meta-Principles only after checking whether the parent relation survives the child's scale, population, and intervention regime.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `67ea75f9bc6863d2f290b0a443df42780f4f59898222de8414f2e9b4429b4d28`</sub>

---

## meta:foundations:evidence-provenance — Scientific Claims Require Recoverable Provenance

- **Epistemic type:** `governance principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `provenance`, `audit`, `reproducibility`, `lineage`

### Argument & interpretation

A claim is auditable only when its evidence, transformations, model versions, decisions, and revision history can be recovered. Provenance does not make a claim true, but it makes error localization, replication, reanalysis, and responsibility possible.

### Boundary & conditions

- Complete provenance can be costly and may expose sensitive information; access-controlled summaries may be required.
- A perfectly traceable pipeline can still encode biased data or invalid assumptions.
- Provenance granularity should match the consequence and reproducibility needs of the claim.

### Application

- Principles Cloud governance
- data lineage
- reproducible science
- regulated systems
- LLM generation trace

### Basics

Scientific notebooks and archival citation practices are longstanding; computational reproducibility expanded provenance to code, environments, data lineage, and stochastic seeds. W3C PROV standardized interoperable provenance concepts.

### Paper / work evidence

- **Foundation:** [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) (2013)
- **Refinement:** [The FAIR Guiding Principles for Scientific Data Management and Stewardship](https://doi.org/10.1038/sdata.2016.18) (2016)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should prioritize claim quality while retaining generation trace as audit metadata. Hidden chain-of-thought is neither required nor desirable; recoverable inputs, outputs, model identity, hashes, and reviewer actions are sufficient.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `9ddc9845534a0033b2766223f1ed8dae01be35bead3da07e31e3944b1947f270`</sub>

---

## meta:foundations:triangulation — Convergent Evidence Across Methods Is Stronger Than Repetition Within One Bias Structure

- **Epistemic type:** `methodological principle`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `triangulation`, `evidence-diversity`, `causal-inference`, `methods`

### Argument & interpretation

When methods with different assumptions and error modes support the same conclusion, shared conclusions are less likely to be artifacts of one design. Triangulation combines experiments, observational studies, natural experiments, simulations, mechanistic models, and qualitative evidence without pretending they are interchangeable.

### Boundary & conditions

- Methods may share hidden biases despite superficial diversity.
- Discordance is informative and should not be averaged away.
- Triangulation does not identify causality unless at least one credible identification path is present.

### Application

- epidemiology
- social science
- systems biology
- climate attribution
- multimodal scientific agents

### Basics

Triangulation has roots in geodesy and social research. Modern epidemiology formalized the deliberate combination of approaches with unrelated biases to strengthen causal inference.

### Paper / work evidence

- **Foundation:** [Triangulation in Aetiological Epidemiology](https://doi.org/10.1093/ije/dyw314) (2016)
- **Refinement:** [Enhancing Epidemiological Evidence for Causal Inference](https://doi.org/10.1093/ije/dyx025) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia can operationalize triangulation through typed evidence roles. Source count alone is insufficient; the system should reward diversity in design, population, instrument, and analytical assumptions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `17dcc3579f4b06059d5381f190c4b5aa3e2e70a9476a5dcfced38ac9a0bc3dd1`</sub>

---

## meta:foundations:resource-bounded-inference — All Inference Is Resource-Bounded

- **Epistemic type:** `computational principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `resources`, `bounded-rationality`, `compute`, `metareasoning`

### Argument & interpretation

Reasoners operate under finite time, data, memory, energy, and experimental budgets. The practically best inference procedure therefore depends on resource constraints and the value of additional computation or evidence, not only on asymptotic correctness.

### Boundary & conditions

- Resource bounds are contextual and can change with hardware, parallelism, or data access.
- Approximation is unacceptable when error costs are catastrophic and exact verification is feasible.
- A faster method can create hidden costs through poor calibration, maintenance, or externalities.

### Application

- AI agents
- experimental design
- algorithm selection
- industrial deployment
- bounded rationality

### Basics

Herbert Simon developed bounded rationality in the 1950s. Computer science formalized time and space complexity, while metareasoning studies the value of computation itself.

### Paper / work evidence

- **Foundation:** [A Behavioral Model of Rational Choice](https://doi.org/10.2307/1884852) (1955)
- **Refinement:** [The Value of Computation and Flexibility in Meta-Level Decision Problems](https://doi.org/10.1016/0004-3702(89)90015-0) (1989)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Does the new Principle instantiate this general pattern under a narrower scope?
- Which assumption or boundary inherited from this Meta-Principle is testable in the new setting?

### Comment

Principia should record budgets and stopping rules. An allegedly universal method often embeds an unspoken assumption about available compute, data, or evaluation calls.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `d9e17819e36f59ee98307d8c113ae6ea582a77ef265eb992aa578895f904f270`</sub>


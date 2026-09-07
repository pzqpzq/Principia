# Cross-Domain Scientific Reasoning Meta-Principles

> **Area ID:** `foundations`  
> **Records:** 29  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:foundations:robustness-sensitivity` — A Principle Is Credible Only Across Plausible Perturbations

**Epistemic type:** methodological principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `robustness`, `sensitivity`, `multiverse`, `stability`

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

- **Foundation (1986):** [Robust Statistics: The Approach Based on Influence Functions](https://onlinelibrary.wiley.com/doi/book/10.1002/0471725250) · `wrk:faa03c99bd259a3e8143`
- **Application (2020):** [Specification Curve: Descriptive and Inferential Statistics on All Reasonable Specifications](https://doi.org/10.1177/2515245917747646) · `wrk:472af7ca6b698368d4a0`

### Comment

Principia should store a robustness profile rather than one score. A Principle may be robust to sampling yet fragile to measurement definition or population shift.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `711029ea78d9c2d9d245ef1f5aeb8befcfb36896e896fbae25969927ef85dfa0`

---

## `meta:foundations:boundary-first-generalization` — A Scientific Law Includes Its Domain of Validity

**Epistemic type:** meta-scientific principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `scope`, `boundary`, `validity-domain`, `generalization`

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

- **Foundation (1994):** [The Effective Field Theory Treatment of Quantum Gravity](https://doi.org/10.1063/1.531335) · `wrk:8440710f1a0fc9291293`
- **Application (2019):** [Model Cards for Model Reporting](https://doi.org/10.1145/3287560.3287596) · `wrk:046e00829f839d607e99`

### Comment

This is the organizing rule for the corpus. New Principles should link to Meta-Principles only after checking whether the parent relation survives the child's scale, population, and intervention regime.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `44f5383f5d93cce823a1f2511a5864cc1672f0d25b3dca5e6a94003b3434c27f`

---

## `meta:foundations:absence-evidence-power` — Absence of Evidence Becomes Evidence of Absence Only Under Sufficient Detection Power

**Epistemic type:** evidential principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `methodological_consensus`  
**Introduced / developed:** 20th century  
**Tags:** `negative-results`, `power`, `equivalence`, `null-results`

### Argument & interpretation

A null or negative observation weakens a hypothesis only when the study had a substantial probability of detecting the predicted effect if it existed. The evidential weight therefore depends on sensitivity, sample size, measurement reliability, and the hypothesis-specific expected signal.

### Boundary & conditions

- Low-powered or insensitive studies provide little evidence for absence.
- Equivalence or non-inferiority claims require prespecified margins.
- A non-significant $p$-value does not by itself establish a negligible effect.

### Application

- negative results
- safety testing
- replication
- clinical equivalence
- anomaly search

### Basics

The distinction is classical in statistical testing and was popularized in medicine by Altman and Bland. Modern equivalence testing makes the required detection margin explicit.

### Paper / work evidence

- **Foundation (1995):** [Absence of evidence is not evidence of absence](https://doi.org/10.1136/bmj.311.7003.485) · `wrk:93fa24f0d3291e726e01`
- **Refinement (2018):** [Equivalence and noninferiority testing in regression models and repeated-measures designs](https://doi.org/10.1037/met0000104) · `wrk:2f2063f9cc20219d72d4`

### Foundation relations

- `depends_on` → `meta:statistics-causality:neyman-pearson` — Evidence for absence depends on an explicit alternative and error trade-off.

### Comment

This principle is essential when a new paper claims that a mechanism, harm, or subgroup effect does not exist.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `eb3eace6b69b4e4a7f35d5c2cccacfeda4ef348963e1ffa954276be5f81db689`

---

## `meta:foundations:negative-evidence-asymmetry` — Absence of Evidence Is Not Uniformly Evidence of Absence

**Epistemic type:** inference proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `null-results`, `power`, `equivalence`, `negative-evidence`

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

- **Foundation (1995):** [Absence of Evidence Is Not Evidence of Absence](https://doi.org/10.1136/bmj.311.7003.485) · `wrk:93fa24f0d3291e726e01`
- **Refinement (2018):** [Equivalence and Noninferiority Testing in Psychology](https://doi.org/10.1177/2515245918770963) · `wrk:a6a4b742e9a50b924b54`

### Comment

Principia should store detection limits and smallest effects of interest. A paper saying “no significant difference” is not itself a Meta-Principle about no effect.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `d84f53ea359dcfcfe947f75dbcfcb74f5de7cc0c33ed394e53de244592fe3de8`

---

## `meta:foundations:sequential-evidence-stopping` — Adaptive Stopping Changes the Evidential Meaning of Repeated Looks at Data

**Epistemic type:** sequential-inference principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_statistical_boundary`  
**Introduced / developed:** 1940s–present  
**Tags:** `sequential-testing`, `optional-stopping`, `confidence-sequences`, `online-science`

### Argument & interpretation

When data are inspected repeatedly and collection stops after a favorable fluctuation, fixed-sample error guarantees no longer apply. Valid sequential inference must account for the stopping rule through sequential tests, alpha spending, confidence sequences, or equivalent controls.

### Boundary & conditions

- Bayesian analyses can condition on observed data under specified models, but optional stopping can still expose model misspecification and decision problems.
- Predefined group-sequential designs differ from unrestricted data peeking.
- Always-valid guarantees may trade power or interval width for flexibility.

### Application

- online experiments
- autonomous laboratories
- clinical monitoring
- A/B testing
- continuous Principle updates

### Basics

Wald developed sequential probability ratio tests in the 1940s. Modern confidence sequences and e-values extend valid inference to adaptive data streams.

### Paper / work evidence

- **Foundation (1945):** [Sequential Tests of Statistical Hypotheses](https://doi.org/10.1214/aoms/1177731118) · `wrk:3ce9511481cd2ed12c77`
- **Refinement (2021):** [Time-uniform, nonparametric, nonasymptotic confidence sequences](https://doi.org/10.1214/20-AOS1991) · `wrk:c9699e5dd8d1f1da8d79`

### Foundation relations

- `depends_on` → `meta:statistics-causality:false-discovery-rate` — Repeated discovery streams require multiplicity and stopping controls.

### Comment

A continuously maintained Principles Cloud needs sequentially valid update policies; otherwise frequent rechecking will inflate false promotions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `fabf39a9e4f3b5d4e4168340354d9c71f6dc569d6540aaab079a22c0fb7f8e81`

---

## `meta:foundations:resource-bounded-inference` — All Inference Is Resource-Bounded

**Epistemic type:** computational principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `resources`, `bounded-rationality`, `compute`, `metareasoning`

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

- **Foundation (1955):** [A Behavioral Model of Rational Choice](https://doi.org/10.2307/1884852) · `wrk:988801abe2b703df04b4`
- **Refinement (1989):** [The Value of Computation and Flexibility in Meta-Level Decision Problems](https://doi.org/10.1016/0004-3702(89)90015-0) · `wrk:0bfee9d2614708a55980`

### Comment

Principia should record budgets and stopping rules. An allegedly universal method often embeds an unspoken assumption about available compute, data, or evaluation calls.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `5ae8328e159f0a60a076de3aaf320549f8b2c52d6ef34d24c5cf20b5d72c6488`

---

## `meta:foundations:bayesian-updating` — Bayesian Updating Under Explicit Priors

**Epistemic type:** theorem-backed inference principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `bayes`, `uncertainty`, `inference`, `sequential`

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

- **Foundation (1763):** [An Essay towards Solving a Problem in the Doctrine of Chances](https://doi.org/10.1098/rstl.1763.0053) · `wrk:46a8ff0371d05d7cd21f`
- **Refinement (1939):** [Theory of Probability](https://global.oup.com/academic/product/theory-of-probability-9780198503682) · `wrk:f5ac11748e1c8bdd562b`

### Comment

Bayesian coherence does not guarantee empirical adequacy. Principia should retain prior and model provenance and avoid presenting a posterior as a model-free probability of truth.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `b7359ced47a79774cece75b80ddf2c6e8abe7ebd90a4f416ea7e8fbfa8f82388`

---

## `meta:foundations:causation-intervention` — Causal Claims Concern Intervention, Not Association Alone

**Epistemic type:** causal principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `causality`, `intervention`, `counterfactuals`, `identification`

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

- **Foundation (1995):** [Causal Diagrams for Empirical Research](https://doi.org/10.1093/biomet/82.4.669) · `wrk:8c95f90d314217f0bf74`
- **Foundation (1974):** [Estimating Causal Effects of Treatments in Randomized and Nonrandomized Studies](https://doi.org/10.1037/h0037350) · `wrk:69b34416129b4dcc293e`

### Comment

LLMs readily convert temporal order or correlation into causal prose. Principia should gate causal relation types and preserve the intervention definition, adjustment logic, and sensitivity to violations.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8c9dbb80db80fea90f5bd84ca2b4f4449a1494d79f684bb6d6306c5924b975a9`

---

## `meta:foundations:robustness-invariance` — Claims Gain Credibility When They Survive Irrelevant Changes of Representation or Environment

**Epistemic type:** robustness principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `methodological_consensus`  
**Introduced / developed:** 1980s–present  
**Tags:** `robustness`, `invariance`, `sensitivity`, `transport`

### Argument & interpretation

A proposed relation is more credible when its qualitative conclusion is stable under defensible changes in preprocessing, measurement, model specification, sampling environment, or analytical method. Invariance across interventions or environments can also help distinguish causal structure from accidental correlation.

### Boundary & conditions

- Stability across many similar analyses can still reflect a shared bias.
- True effects may legitimately vary across mechanisms, populations, or scales.
- Robustness checks should be specified before inspecting favorable outcomes where possible.

### Application

- sensitivity analysis
- causal discovery
- cross-site replication
- scientific machine learning
- Principle promotion

### Basics

Robust statistics formalized resistance to contamination; later causal work used invariance across environments as a structural signal.

### Paper / work evidence

- **Foundation (1981):** [Robust Statistics](https://onlinelibrary.wiley.com/doi/book/10.1002/0471725250) · `wrk:54b4b0abdca59678284f`
- **Refinement (2016):** [Causal Inference Using Invariant Prediction](https://doi.org/10.1111/rssb.12167) · `wrk:013afd361e9123e69c95`

### Foundation relations

- `refines` → `meta:foundations:transportability` — Invariance tests whether a claimed scope is stable across environments.

### Comment

Principia should record which perturbations a Principle survived rather than collapse robustness into one score.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `59216fb44a37d00ca888654d415ebde336ab461bf36b00ccba159bdd373ee3c9`

---

## `meta:foundations:triangulation-independent-bias` — Concordance Across Differently Biased Methods Is Stronger Than Repetition of One Method

**Epistemic type:** triangulation principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `methodological_consensus`  
**Introduced / developed:** 1960s–present  
**Tags:** `triangulation`, `consilience`, `bias-diversity`, `causal-evidence`

### Argument & interpretation

Evidence becomes more persuasive when methods with different and partly independent failure modes converge on the same conclusion. The gain comes from diversity of bias structure, not merely from accumulating many studies that share the same design.

### Boundary & conditions

- Methods can share hidden data, assumptions, or institutional biases.
- Disagreement may reveal genuine scale or population dependence.
- Triangulation does not mechanically identify which estimate is numerically correct.

### Application

- causal inference
- multi-modal science
- replication portfolios
- system identification
- meta-analysis

### Basics

Triangulation entered social science methodology in the mid-twentieth century and was later formalized as a strategy for causal inference in epidemiology and other observational sciences.

### Paper / work evidence

- **Foundation (2012):** [The Use of Triangulation in Social Sciences Research](https://doi.org/10.1080/13645579.2012.700295) · `wrk:d4f86819db8cfe1f490f`
- **Refinement (2017):** [Triangulation in aetiological epidemiology](https://doi.org/10.1093/ije/dyw314) · `wrk:0b791a1f5dadc2d7a8ba`

### Foundation relations

- `generalizes` → `meta:medicine-epidemiology:triangulation-evidence` — The cross-domain principle generalizes medical triangulation.

### Comment

Principia should reward evidence diversity only after checking independence of data, code, institutions, and assumptions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `1fdd11f9034c46ba0019b6e55dd6d700820ed0c9811a503e9260cb4afcc20d60`

---

## `meta:foundations:triangulation` — Convergent Evidence Across Methods Is Stronger Than Repetition Within One Bias Structure

**Epistemic type:** methodological principle  
**Principia kind:** `heuristic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `triangulation`, `evidence-diversity`, `causal-inference`, `methods`

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

- **Foundation (2016):** [Triangulation in Aetiological Epidemiology](https://doi.org/10.1093/ije/dyw314) · `wrk:0b791a1f5dadc2d7a8ba`
- **Refinement (2017):** [Enhancing Epidemiological Evidence for Causal Inference](https://doi.org/10.1093/ije/dyx025) · `wrk:7e4dd425fdfaebf4df2c`

### Comment

Principia can operationalize triangulation through typed evidence roles. Source count alone is insufficient; the system should reward diversity in design, population, instrument, and analytical assumptions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `98ebdf2fd595365112190a0a23ecf65ad363a4b33bc9c7cdced4ac63fb8209ef`

---

## `meta:foundations:model-pluralism` — Different Models Trade Realism, Generality, and Precision

**Epistemic type:** methodological observation  
**Principia kind:** `heuristic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `model-pluralism`, `tradeoff`, `ensembles`, `abstraction`

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

- **Foundation (1966):** [The Strategy of Model Building in Population Biology](https://doi.org/10.1086/282079) · `wrk:93fb9abd5b22e9522ffe`
- **Refinement (2010):** [The Truth Is the Whole](https://doi.org/10.1086/652964) · `wrk:80b5d1c8384cda441343`

### Comment

Principia should preserve model family and abstraction level. Agreement between models with shared assumptions is weaker evidence than agreement between genuinely independent representations.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `03cf5f439c6141455d6911bc2e9da28cce291c92545af6170e208fb045fd34c7`

---

## `meta:foundations:underdetermination` — Evidence Underdetermines Explanatory Theory

**Epistemic type:** epistemic proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `underdetermination`, `identifiability`, `alternatives`, `model-pluralism`

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

- **Foundation (1906):** [The Aim and Structure of Physical Theory](https://press.princeton.edu/books/paperback/9780691120269/the-aim-and-structure-of-physical-theory) · `wrk:fd49fa47e541e1fb1ecd`
- **Refinement (1951):** [Two Dogmas of Empiricism](https://doi.org/10.2307/2181906) · `wrk:42b06d2c68d40aee838d`

### Comment

The risk is sliding from justified humility into relativism. Principia should rank alternatives by evidence, scope, simplicity, and challenge performance while retaining credible competitors.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `0443377885d04e0572b2d7b2cd67690c0edc6453976686210c3b14b2ee7c8af4`

---

## `meta:foundations:scale-separation` — Explanations Are Conditional on Scale

**Epistemic type:** cross-domain principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `scale`, `coarse-graining`, `emergence`, `effective-theory`

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

- **Foundation (1972):** [More Is Different](https://doi.org/10.1126/science.177.4047.393) · `wrk:5c3c081abbd4017b12a4`
- **Formalization (1974):** [The Renormalization Group and the $\epsilon$ Expansion](https://doi.org/10.1016/0370-1573(74)90023-4) · `wrk:61fb30d0e2d503d049a6`

### Comment

This Meta-Principle is a key parent for paper-level laws. Principia should ask at what scale a claim is closed and whether variables from different levels have been mixed without a coupling model.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `370f5d336b97626747210e092d6fc140948dd9070a98958598af6a5515ebc966`

---

## `meta:foundations:minimum-description-length` — Explanations Trade Fit Against Description Length

**Epistemic type:** minimum-description-length principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_methodological_principle`  
**Introduced / developed:** 1960s–1978  
**Tags:** `mdl`, `compression`, `occam`, `model-selection`

### Argument & interpretation

When several models explain the same observations, a model that compresses the data and its own specification more effectively often captures more reusable structure. In MDL form, selection minimizes a total code length such as $L(M)+L(D\mid M)$ rather than fit alone.

### Boundary & conditions

- Compression depends on the representation language and coding scheme.
- The shortest model can be scientifically wrong when the hypothesis class omits the true mechanism.
- MDL is a model-selection principle, not a guarantee of causal interpretation.

### Application

- model selection
- scientific theory comparison
- symbolic regression
- representation learning
- Principle deduplication

### Basics

Solomonoff, Kolmogorov, and Chaitin connected induction to algorithmic description length. Rissanen developed MDL as a practical statistical principle in the 1970s.

### Paper / work evidence

- **Foundation (1978):** [Modeling by Shortest Data Description](https://doi.org/10.1016/S0005-1098(78)80005-5) · `wrk:314f6001660e0e8864ac`
- **Refinement (1983):** [A Universal Prior for Integers and Estimation by Minimum Description Length](https://doi.org/10.1214/aos/1176344136) · `wrk:cb569eb621fc5127421c`

### Foundation relations

- `depends_on` → `meta:foundations:model-pluralism` — Compression is meaningful only relative to an explicit model language.

### Comment

Principia can use MDL to prefer concise Meta-Principle chains, but it should preserve alternative explanations when different representation languages rank them differently.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `4d41a8928ae07b85c96fba5ccf13c31ba8bc93b34627296cced94f47e53c229a`

---

## `meta:foundations:open-world-coverage-gap` — Failure to Find a Foundation Can Indicate a Coverage Gap Rather Than an Invalid Principle

**Epistemic type:** knowledge-system principle  
**Principia kind:** `heuristic`  
**Maturity:** `supported` · **Stability:** `medium` · **Review:** `curated_draft`  
**Significance:** `principia_native_principle`  
**Introduced / developed:** 2020s  
**Tags:** `open-world`, `coverage-gap`, `ontology`, `governance`

### Argument & interpretation

In an open and expanding knowledge system, absence of a suitable parent Meta-Principle has at least two explanations: the new Principle is poorly grounded, or the foundation corpus is incomplete. The system should preserve this ambiguity as a typed coverage gap instead of forcing a weak analogy.

### Boundary & conditions

- A coverage gap is not evidence that the new claim is correct.
- Repeated gaps in one topic may indicate a missing Area package or taxonomy failure.
- Human review is required before adding a new foundational root.

### Application

- Principle graph maintenance
- ontology expansion
- retrieval diagnostics
- domain-pack governance

### Basics

Open-world knowledge representation distinguishes unknown facts from false ones. Principia applies that distinction to foundation coverage and relation construction.

### Paper / work evidence

- **Foundation (2001):** [The Semantic Web](https://www.scientificamerican.com/article/the-semantic-web/) · `wrk:f51318bac1677f889540`
- **Standard (2012):** [OWL 2 Web Ontology Language Document Overview](https://www.w3.org/TR/owl2-overview/) · `wrk:ecd4c1ecaa65761174eb`

### Foundation relations

- `analogous_to` → `meta:foundations:underdetermination` — Both preserve multiple explanations when evidence is insufficient.

### Comment

This prevents the Meta-Principle layer from becoming a closed dogma. Coverage itself should be monitored as a first-class quality metric.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `b9fedc97d46bc2319acee908df1abc6087f5c5b2bf2c2175c7cfca9225b9b871`

---

## `meta:foundations:falsifiability` — Falsifiability and Risky Prediction

**Epistemic type:** methodological principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `epistemology`, `falsification`, `testing`, `risk`

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

- **Foundation (1934):** [The Logic of Scientific Discovery](https://www.routledge.com/The-Logic-of-Scientific-Discovery/Popper/p/book/9780415278447) · `wrk:f95294d3ef7ccc54fa5b`
- **Refinement (1978):** [The Methodology of Scientific Research Programmes](https://doi.org/10.1017/CBO9780511621123) · `wrk:7ae437dc670f74108845`

### Comment

Use this as a demand for explicit risk, not as a mechanical binary classifier of science. Overly narrow tests can reward superficial benchmark compliance, while overly broad claims can evade meaningful challenge.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `ed6f9021c947c63aa83ea1e6d4500a168fd5a439cb8aafd74f860a0e147eb7c3`

---

## `meta:foundations:transportability` — Generalization Requires Invariance Across Environments

**Epistemic type:** causal-inference proposition  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `transportability`, `invariance`, `domain-shift`, `external-validity`

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

- **Foundation (2014):** [External Validity: From Do-Calculus to Transportability Across Populations](https://doi.org/10.1214/14-STS486) · `wrk:91668f3e85522cca2c69`
- **Application (2019):** [Domain Adaptation under Target and Conditional Shift](https://proceedings.mlr.press/v97/wu19f.html) · `wrk:c711c625004ba4d9c19f`

### Comment

A Meta-Principle should not become universal merely because several papers use similar language. Principia should represent source and target environments and the exact invariance invoked.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `c1705600f0a43010822c5657941765d94026bbbb0647ac71e92ce2f55ff6aee3`

---

## `meta:foundations:replication-independence` — Independent Replication Separates Stable Effects from Local Artifacts

**Epistemic type:** empirical-method principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `replication`, `reproducibility`, `independence`, `external-validity`

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

- **Foundation (2015):** [Estimating the Reproducibility of Psychological Science](https://doi.org/10.1126/science.aac4716) · `wrk:5a21042beafbf397c5f6`
- **Synthesis (2019):** [Reproducibility of Scientific Results](https://doi.org/10.17226/25303) · `wrk:d8f9bfcecd523c051217`

### Comment

Replication should update scope, not merely trigger a binary pass/fail. Principia should record protocol distance and evidence independence so that ten correlated studies do not masquerade as ten independent confirmations.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `72de58dc4ac1e03cfc72713556b80220c497cafc6521bb0eda49caf6a993fe86`

---

## `meta:foundations:measurement-validity` — Measurement Validity Precedes Numerical Precision

**Epistemic type:** measurement principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `measurement`, `validity`, `calibration`, `constructs`

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

- **Foundation (1946):** [On the Theory of Scales of Measurement](https://doi.org/10.1126/science.103.2684.677) · `wrk:9ecc3e1e30dbd64d05aa`
- **Refinement (2014):** [Standards for Educational and Psychological Testing](https://www.testingstandards.net/open-access-files.html) · `wrk:2dc986eeebed5de14ef8`

### Comment

Metric availability creates a temptation to substitute the measured proxy for the real objective. Every Principia Principle should preserve units, calibration state, construct definition, and known measurement invariances.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `68536f292fcf4ee58cf00f46c3bbdafb85743adfa88a0d43e9a464a4ff3280c1`

---

## `meta:foundations:measurement-theory-ladenness` — Measurements Are Produced by Models, Instruments, and Operational Definitions

**Epistemic type:** measurement principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_epistemic_principle`  
**Introduced / developed:** 20th century–present  
**Tags:** `measurement`, `operationalization`, `calibration`, `construct-validity`

### Argument & interpretation

Observed values are not direct copies of reality; they are outputs of instruments, calibration models, sampling rules, and operational definitions. A scientific Principle inherits the validity limits of the measurement chain used to instantiate its variables.

### Boundary & conditions

- Some measurements are highly standardized and robust across instruments.
- Acknowledging theory-ladenness does not imply that all measurements are arbitrary.
- Measurement error can be differential and intervention-dependent.

### Application

- sensor science
- psychometrics
- biomarkers
- industrial metrology
- dataset construction

### Basics

Operationalism, measurement theory, and metrology developed formal accounts of how concepts become observable quantities. Modern data science extends the issue to labels and digital traces.

### Paper / work evidence

- **Foundation (1971):** [Foundations of Measurement, Volume I](https://store.doverpublications.com/products/9780486453156) · `wrk:6447a3d2deb2d6d4632e`
- **Context (2005):** [Measurement in Psychology: A Critical History of a Methodological Concept](https://doi.org/10.1017/CBO9780511490040) · `wrk:65a1b5445113b554423e`

### Foundation relations

- `specializes` → `meta:foundations:model-pluralism` — Measurements instantiate model-dependent mappings from systems to records.

### Comment

Principia should link a Principle to its measurement method and calibration version, especially when the same named variable has multiple operational definitions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `e9e100d769c2f8fe8dd992eadc35c13baa7dd846d32ad50c9beada38d9ca22e7`

---

## `meta:foundations:goodhart-proxy` — Optimized Proxies Cease to Behave Like Passive Measures

**Epistemic type:** socio-technical principle  
**Principia kind:** `heuristic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `goodhart`, `proxies`, `incentives`, `metric-gaming`

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

- **Foundation (1975):** [Problems of Monetary Management: The U.K. Experience](https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/1975/problems-of-monetary-management-the-uk-experience.pdf) · `wrk:29a2e6931a5b2af25ec7`
- **Refinement (1984):** [Goodhart’s Law: Its Origins, Meaning and Implications for Monetary Policy](https://doi.org/10.1007/978-1-349-17295-5_5) · `wrk:12b36900abdcf16a0189`

### Comment

Principia should treat metrics as interventions on behavior, especially when recommendations will be deployed. A highly predictive metric in passive data may become unreliable after optimization begins.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8406aba9971624bf54d1608dcc8840133d6f7037ee183a80d98a0b9cd0fad663`

---

## `meta:foundations:parsimony-mdl` — Parsimony as Minimum Description Length

**Epistemic type:** formalized heuristic  
**Principia kind:** `theorem`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `parsimony`, `mdl`, `compression`, `model-selection`

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

- **Foundation (1978):** [Modeling by Shortest Data Description](https://doi.org/10.1016/0005-1098(78)90005-5) · `wrk:20bc5a64cc0814dbf272`
- **Refinement (1983):** [A Universal Prior for Integers and Estimation by Minimum Description Length](https://doi.org/10.1214/aos/1176344136) · `wrk:cb569eb621fc5127421c`

### Comment

MDL is powerful for Principia because Meta-Principles should compress many specific Principles. However, compression must preserve evidence anchors and boundary conditions; otherwise short representations become opaque labels.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `183a7ce6df42040a91565d37a9d3029c995acf7fd166b91960eea4123e08f5e5`

---

## `meta:foundations:mechanism-prediction-distinction` — Predictive Success and Mechanistic Truth Are Different Achievements

**Epistemic type:** epistemic principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `prediction`, `mechanism`, `explanation`, `causality`

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

- **Foundation (2001):** [Statistical Modeling: The Two Cultures](https://doi.org/10.1214/ss/1009213726) · `wrk:f9ab3fc73b70e9e8c0cd`
- **Refinement (2010):** [To Explain or to Predict?](https://doi.org/10.1214/10-STS330) · `wrk:4e5cf245af0d76a55c18`

### Comment

Principia should not promote predictive feature importance to mechanism. A Principle Capsule should say whether its evidence supports association, prediction, intervention, or process-level explanation.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `3cd12886cb0fbb4481b4d2aed943cc933486f7c8addcd5e83241882c39e26c20`

---

## `meta:foundations:randomization-controls` — Randomization and Controls Break Systematic Alternative Explanations

**Epistemic type:** design principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `randomization`, `controls`, `causality`, `experimental-design`

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

- **Foundation (1935):** [The Design of Experiments](https://archive.org/details/designofexperime00fish) · `wrk:c824369df72b477bcdf7`
- **Application (1948):** [Streptomycin Treatment of Pulmonary Tuberculosis](https://doi.org/10.1136/bmj.2.4582.769) · `wrk:8491af5d7fec976ea3ad`

### Comment

Randomization is a design property, not a ceremonial label. Principia should link causal claims to the actual assignment mechanism and distinguish randomized encouragement, cluster randomization, and observational controls.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `3a7af150e0cdb803b98b4c5b86c5a1ace98b99a6ffb1f69483740f5d08feec52`

---

## `meta:foundations:replicability-reproducibility` — Reproducibility of Computation and Replicability of Findings Are Distinct Requirements

**Epistemic type:** methodological norm  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `scientific_consensus`  
**Introduced / developed:** 2010s–present  
**Tags:** `reproducibility`, `replicability`, `audit`, `independence`

### Argument & interpretation

Reproducibility asks whether the same data and procedures regenerate the reported result; replicability asks whether new data or independent implementation support the same scientific conclusion. A mature Principle should ideally satisfy both, because one diagnoses computational traceability while the other diagnoses external stability.

### Boundary & conditions

- Terminology varies across fields, so the operational definitions must be stated.
- Exact numerical reproduction can coexist with a biased design.
- Replication can fail because of genuine heterogeneity rather than misconduct or error.

### Application

- research software
- multi-site studies
- benchmark governance
- Principle maturity
- audit trails

### Basics

The distinction was standardized in major reports on computational and empirical reproducibility during the 2010s.

### Paper / work evidence

- **Foundation (2019):** [Reproducibility and Replicability in Science](https://doi.org/10.17226/25303) · `wrk:096f621093f261956b13`
- **Context (2020):** [The Science of Reproducibility: A Brief History of a Confused Terminology](https://doi.org/10.1007/978-3-030-32036-6_2) · `wrk:1498a47f1b9bd00222d6`

### Foundation relations

- `refines` → `meta:foundations:replication-independence` — The terms separate computational replay from independent empirical support.

### Comment

A replayed pipeline should not automatically promote a finding to replicated status; Principia should maintain separate events.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `e679c66745e8530ed34e65a2c18554986a07f20332bf5253a342eee2fcd8e87d`

---

## `meta:foundations:evidence-provenance` — Scientific Claims Require Recoverable Provenance

**Epistemic type:** governance principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `provenance`, `audit`, `reproducibility`, `lineage`

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

- **Foundation (2013):** [PROV-O: The PROV Ontology](https://www.w3.org/TR/prov-o/) · `wrk:dac5511dc03c7d3a7cb4`
- **Refinement (2016):** [The FAIR Guiding Principles for Scientific Data Management and Stewardship](https://doi.org/10.1038/sdata.2016.18) · `wrk:c8e1a46002c6cdbd316c`

### Comment

Principia should prioritize claim quality while retaining generation trace as audit metadata. Hidden chain-of-thought is neither required nor desirable; recoverable inputs, outputs, model identity, hashes, and reviewer actions are sufficient.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `5f6134989e44ba1f7a3579f0d280514ccf49ea549ca75de18c0cb8672813e800`

---

## `meta:foundations:multiple-testing-selection` — Search Multiplicity Inflates Apparent Discovery

**Epistemic type:** statistical principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `multiplicity`, `selection-bias`, `fdr`, `discovery`

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

- **Foundation (1995):** [Controlling the False Discovery Rate: A Practical and Powerful Approach to Multiple Testing](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) · `wrk:d819b295c23821205bfb`
- **Refinement (2016):** [Exact Post-Selection Inference, with Application to the Lasso](https://doi.org/10.1214/14-AOS1232) · `wrk:f9d89783d3105f275d6c`

### Comment

This is central to autonomous discovery: an agent that tries thousands of candidate Principles must not report the winner as though it were prespecified. Search history is evidence metadata.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `85f84c253d99a131539393f16f1b6f6cf6aa8a7d871bd77fa8406fa389da7d56`

---

## `meta:foundations:uncertainty-propagation` — Uncertainty Must Propagate Through the Full Reasoning Chain

**Epistemic type:** quantitative principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `uncertainty`, `propagation`, `uql`, `measurement`

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

- **Foundation (2008):** [Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement](https://www.bipm.org/en/committees/jc/jcgm/publications) · `wrk:af5e840fd18fcae66ef2`
- **Refinement (2010):** [Verification, Validation, and Uncertainty Quantification](https://doi.org/10.1017/CBO9780511760396) · `wrk:3941a88033a6bbbd9095`

### Comment

Principia should distinguish measurement, sampling, parameter, structural, and scenario uncertainty. Collapsing them into one confidence score obscures where new evidence would be most valuable.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `64efe315f5c8e24efa900b8b2449062ac2f377cf671b351ece656cfb6e4d2617`

---

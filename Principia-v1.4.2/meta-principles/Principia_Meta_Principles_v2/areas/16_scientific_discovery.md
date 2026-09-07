# Scientific Discovery, Measurement, and Experimentation Meta-Principles

> **Area ID:** `scientific-discovery`  
> **Records:** 15  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:scientific-discovery:scientific-memory-negative-results` — A Discovery System Must Preserve Failed Tests and Counterexamples as First-Class Knowledge

**Epistemic type:** scientific memory principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `principia_core_meta_principle`  
**Introduced / developed:** contemporary  
**Tags:** `negative-results`, `counterexamples`, `scientific-memory`, `survivorship-bias`

### Argument & interpretation

Negative results, failed replications, invalid parameter regions, and counterexamples reduce future search waste and define Principle boundaries. A knowledge system that stores only supported claims creates survivorship bias and repeatedly rediscovers the same failures.

### Boundary & conditions

- A failed experiment can reflect implementation error or low power rather than a false hypothesis.
- Sensitive or proprietary failures may require restricted visibility.
- Deduplication must distinguish genuinely repeated failure from independent replication.

### Application

- Principles Cloud
- industrial R&D
- autonomous laboratories
- meta-analysis
- research portfolio management

### Basics

The norm follows from publication-bias research, falsification, and cumulative engineering practice; modern machine-readable provenance makes negative evidence operationally reusable.

### Paper / work evidence

- **Foundation (1979):** [The file drawer problem and tolerance for null results](https://doi.org/10.1037/0033-2909.86.3.638) · `wrk:06a51bb624eb04dfd0f5`
- **Meta-Science (2005):** [Why Most Published Research Findings Are False](https://doi.org/10.1371/journal.pmed.0020124) · `wrk:b2cdd356f479b54bd20b`

### Foundation relations

- `contradicts` → `meta:scientific-discovery:publication-bias-file-drawer` — Preserving negative results counters literature selection.
- `specializes` → `meta:foundations:falsifiability` — Counterexamples define and refine Principle boundaries.

### Comment

Negative evidence should carry design, power, fidelity, and failure-cause metadata. A null result is not automatically a contradiction.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `fc8c8c4ef3b101f3c7028b365bf8ef1e99d0cdba98fcd6abb4cc677c556f0566`

---

## `meta:scientific-discovery:hypothesis-search-cost-falsifiability` — A Useful Hypothesis Must Be Both Discriminable and Affordable to Challenge

**Epistemic type:** scientific search proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `principia_core_meta_principle`  
**Introduced / developed:** 20th century–present  
**Tags:** `falsifiability`, `research-prioritization`, `experiment-cost`, `discriminability`

### Argument & interpretation

Hypotheses differ not only in plausibility but in the cost and power of experiments that distinguish them from alternatives. A productive discovery system should prefer claims with clear failure conditions and high expected discrimination per unit cost, risk, and time rather than maximizing novelty or verbal elegance alone.

### Boundary & conditions

- Some fundamental questions are intrinsically expensive or initially weakly testable.
- A cheap test can be uninformative if the alternatives make similar predictions.
- Falsification is graded under noisy probabilistic evidence, not always binary.

### Application

- research prioritization
- ASD agents
- experiment planning
- grant strategy
- industrial R&D

### Basics

Popper emphasized falsifiability; decision theory and Bayesian design formalized discriminating experiments and value of information. Principia turns this into a ranking principle for Candidate Principles.

### Paper / work evidence

- **Foundation (1959):** [The Logic of Scientific Discovery](https://www.routledge.com/The-Logic-of-Scientific-Discovery/Popper/p/book/9780415278447) · `wrk:f95294d3ef7ccc54fa5b`
- **Decision-Theory (1956):** [On a Measure of the Information Provided by an Experiment](https://doi.org/10.1214/aoms/1177728069) · `wrk:4b099374189a426483f3`

### Foundation relations

- `refines` → `meta:foundations:falsifiability` — It adds resource and alternative-separation criteria.
- `depends_on` → `meta:scientific-discovery:bayesian-experimental-design` — Expected information quantifies discriminating value.

### Comment

This Principle should guide ranking, not exclude long-horizon theory. The system should expose the reason a costly hypothesis remains strategically important.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `42770d66034d83e887b96b2378cbd5917b514fd17491984df384ddc78ce54a5b`

---

## `meta:scientific-discovery:adaptive-experiment-inference` — Adaptive Experiments Require Inference That Remains Valid Under Data-Dependent Sampling and Stopping

**Epistemic type:** adaptive inference principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `recent_methodological_consensus`  
**Introduced / developed:** 2010s–present  
**Tags:** `adaptive-experiments`, `always-valid`, `confidence-sequences`, `online-testing`

### Argument & interpretation

When treatment allocation, model choice, or stopping depends on accumulating data, ordinary fixed-design estimators and p-values can become biased or miscalibrated. Valid inference must condition on, model, or explicitly protect against the adaptive policy using randomization, martingales, confidence sequences, or selective-inference corrections.

### Boundary & conditions

- Different adaptive mechanisms require different corrections.
- Validity can be conservative when adaptation is weak.
- Inference after opaque automated policies may be difficult without complete logs.

### Application

- A/B testing
- bandit experiments
- adaptive trials
- autonomous labs
- online model evaluation

### Basics

Sequential analysis supplied early foundations; always-valid inference, confidence sequences, and adaptive data-analysis theory expanded rapidly in the 2010s.

### Paper / work evidence

- **Foundation (2017):** [Always Valid Inference: Continuous Monitoring of A/B Tests](https://doi.org/10.1287/opre.2016.1546) · `wrk:ba890639883da356fa67`
- **Modern-Theory (2021):** [Time-uniform, nonparametric, nonasymptotic confidence sequences](https://doi.org/10.1214/20-AOS1991) · `wrk:c9699e5dd8d1f1da8d79`

### Foundation relations

- `generalizes` → `meta:scientific-discovery:sequential-probability-ratio` — Always-valid inference extends calibrated sequential evidence.
- `depends_on` → `meta:statistics-causality:missing-data-mechanisms` — Adaptive selection changes the sampling process.

### Comment

Principia should retain the complete adaptive policy and stopping trace. A final dataset alone may be insufficient to reconstruct valid inference.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `85e4d250a395eefe8b742d1c02aed095cf937cc1822e1df5ac13d918ce7f0cb1`

---

## `meta:scientific-discovery:autonomous-laboratory-closed-loop` — Autonomous Laboratories Couple Hypothesis, Experiment, Measurement, and Model Update in a Closed Loop

**Epistemic type:** autonomous discovery architecture  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `recent_asd_landmark`  
**Introduced / developed:** 2020s–present  
**Tags:** `autonomous-lab`, `closed-loop`, `asd`, `robotics`

### Argument & interpretation

An autonomous laboratory repeatedly proposes candidate experiments, checks feasibility, executes them through instruments or robotics, interprets measurements, updates a model or knowledge base, and chooses the next experiment. The scientific value comes from the closed evidence loop rather than from text generation alone.

### Boundary & conditions

- Physical safety, calibration, maintenance, and intervention authority require human governance.
- Automation can exploit artifacts or optimize a misspecified objective.
- Domain transfer is limited by instrumentation, ontology, and experimental semantics.

### Application

- materials synthesis
- chemistry
- biology
- process development
- Principia ASD

### Basics

Self-driving laboratories developed from robotic chemistry, active learning, and automated experimentation; A-Lab demonstrated literature- and computation-guided inorganic synthesis in 2023.

### Paper / work evidence

- **Foundation (2023):** [An autonomous laboratory for the accelerated synthesis of novel materials](https://doi.org/10.1038/s41586-023-06734-w) · `wrk:2afe4b129293966eea80`
- **Review (2019):** [Self-driving laboratories for chemistry and materials science](https://doi.org/10.1038/s41578-019-0124-0) · `wrk:f2ec4d9587ff733513ef`

### Foundation relations

- `specializes` → `meta:scientific-discovery:surrogate-active-loop` — Many autonomous labs use surrogate-guided experiment selection.
- `depends_on` → `meta:engineering-optimization:requirements-constraints-first` — Physical actuation requires explicit safety constraints.

### Comment

An LLM agent that only proposes experiments is not a closed-loop ASD system. Evidence capture, execution, failure recovery, and model update must be present.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `2d7592ab304a70ab48638483c4d778c5c9aae1d2f53dfb9e791f22010964ed66`

---

## `meta:scientific-discovery:benchmark-saturation-leakage` — Benchmark Performance Loses Meaning When the Test Set Is Saturated, Contaminated, or Repeatedly Optimized Against

**Epistemic type:** evaluation validity principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `recent_ai_evaluation_consensus`  
**Introduced / developed:** 2010s–present  
**Tags:** `benchmark`, `contamination`, `saturation`, `evaluation`

### Argument & interpretation

A benchmark is useful only while it measures the intended capability on genuinely held-out, discriminating examples. Repeated public optimization, training contamination, annotation artifacts, and ceiling effects can turn score gains into benchmark-specific adaptation rather than real capability progress.

### Boundary & conditions

- Contamination is difficult to detect in web-scale training.
- A saturated benchmark can remain useful for regression testing or subgroups.
- New benchmarks can introduce their own construct and ecological validity failures.

### Application

- AI evaluation
- scientific agents
- leaderboards
- medical prediction
- software benchmarks

### Basics

Dataset-shift and leaderboard-overfitting concerns are longstanding; reproducibility studies and foundation-model contamination made benchmark validity a central 2020s issue.

### Paper / work evidence

- **Foundation (2018):** [Do CIFAR-10 Classifiers Generalize to CIFAR-10?](https://arxiv.org/abs/1806.00451) · `wrk:79acc7688b8d60bd210f`
- **Evaluation-Framework (2022):** [Beyond the Imitation Game: Quantifying and Extrapolating the Capabilities of Language Models](https://doi.org/10.48550/arXiv.2206.04615) · `wrk:bb18241f16d84d5d7c28`

### Foundation relations

- `specializes` → `meta:foundations:measurement-validity` — A benchmark is a measurement instrument whose validity can decay.
- `depends_on` → `meta:foundations:multiple-testing-selection` — Repeated selection against a public test set creates overfitting.

### Comment

Principia should represent benchmark lineage, access history, contamination evidence, and saturation status as conditions on every performance Principle.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `5a2a88eb6121724d281af58c0531a2adb1ebf7d545b3dd8365b9ae86a135e171`

---

## `meta:scientific-discovery:multi-fidelity-modeling` — Cheap Approximate Models and Sparse High-Fidelity Data Can Be Fused When Their Discrepancy Is Modeled

**Epistemic type:** multi-fidelity inference principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `influential_engineering_discovery_principle`  
**Introduced / developed:** 2000–present  
**Tags:** `multi-fidelity`, `surrogate`, `simulation`, `calibration`

### Argument & interpretation

A hierarchy of simulations, surrogate models, and experiments can reduce discovery cost when lower-fidelity outputs are correlated with high-fidelity reality. Statistical fusion models the relationship and discrepancy between levels rather than treating cheap predictions as truth.

### Boundary & conditions

- Low- and high-fidelity sources must share meaningful structure.
- Systematic discrepancy can dominate in extrapolation or regime changes.
- Acquisition cost, noise, and calibration uncertainty should be modeled separately.

### Application

- aerospace design
- materials discovery
- climate modeling
- digital twins
- scientific machine learning

### Basics

Kennedy and O’Hagan formalized Bayesian calibration and multi-level discrepancy modeling in 2000; multi-fidelity optimization later became standard in expensive engineering design.

### Paper / work evidence

- **Foundation (2000):** [Predicting the output from a complex computer code when fast approximations are available](https://doi.org/10.1093/biomet/87.1.1) · `wrk:672c917e3e30b12123ee`
- **Review (2017):** [Multifidelity optimization: a review](https://doi.org/10.1080/0305215X.2016.1227676) · `wrk:04c8905997ad27312edc`

### Foundation relations

- `specializes` → `meta:foundations:model-pluralism` — Every fidelity level is an approximation with a discrepancy.
- `depends_on` → `meta:scientific-discovery:surrogate-active-loop` — Surrogate optimization often mixes fidelity levels.

### Comment

Multi-fidelity fusion is valuable only when the discrepancy model is validated. More cheap data cannot compensate for an unrecognized regime mismatch.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `e0f47a405f740122c1032e00aeb2697085876e1b1492200cec88848508d033da`

---

## `meta:scientific-discovery:computational-reproducibility-environments` — Computational Results Require Captured Code, Inputs, Dependencies, Configuration, and Execution Environment

**Epistemic type:** computational reproducibility principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_research_consensus`  
**Introduced / developed:** 2010s–present  
**Tags:** `reproducibility`, `containers`, `environment`, `workflow`

### Argument & interpretation

A result is computationally reproducible only when another execution can reconstruct the code, data references, dependency versions, parameters, seeds, and relevant hardware or numerical environment. Containers and workflow manifests reduce environment drift but do not repair missing data or hidden manual steps.

### Boundary & conditions

- Bitwise reproducibility may be impossible across hardware or parallel schedules.
- A container can preserve obsolete or insecure software.
- Reproducing output does not validate the scientific model or data quality.

### Application

- computational science
- machine learning
- simulation
- data analysis
- artifact evaluation

### Basics

Reproducible-research practice grew with literate programming, workflow systems, package managers, and containers; Sandve and colleagues summarized practical rules in 2013.

### Paper / work evidence

- **Foundation (2013):** [Ten Simple Rules for Reproducible Computational Research](https://doi.org/10.1371/journal.pcbi.1003285) · `wrk:5b7711f260f98811a881`
- **Tooling (2016):** [ReproZip: Computational Reproducibility With Ease](https://doi.org/10.1145/2956577.2956580) · `wrk:7101f4f591f54479e824`

### Foundation relations

- `specializes` → `meta:foundations:evidence-provenance` — Execution provenance is necessary for replay.
- `supports` → `meta:scientific-discovery:fair-principles` — Portable metadata increases reproducible reuse.

### Comment

Principia should distinguish content digest, artifact hash, environment identity, and scientific validation rather than compressing them into one “reproducible” label.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `a23dbce1d7abeb3d391046a0bfbe31d585a3cdd666c8eb813a32f5689b513246`

---

## `meta:scientific-discovery:surrogate-active-loop` — Expensive Black-Box Search Can Alternate Surrogate Learning and Acquisition

**Epistemic type:** Bayesian optimization principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_discovery_standard`  
**Introduced / developed:** 1998–present  
**Tags:** `bayesian-optimization`, `surrogate`, `acquisition`, `active-loop`

### Argument & interpretation

When evaluations are expensive, fit a probabilistic surrogate to observed input–output pairs and select the next query by an acquisition function balancing predicted value, uncertainty, and constraints. Repeating this loop concentrates evaluations in promising or informative regions.

### Boundary & conditions

- Performance depends on surrogate calibration, kernel or representation, acquisition optimization, and dimensionality.
- Nonstationarity, hidden constraints, and batch effects can mislead the loop.
- The method is not globally efficient in arbitrary high-dimensional spaces without structure.

### Application

- materials optimization
- hyperparameter search
- robotics
- drug design
- process tuning

### Basics

Jones, Schonlau, and Welch introduced Efficient Global Optimization in 1998; Gaussian-process Bayesian optimization became a standard active-search method in the 2010s.

### Paper / work evidence

- **Foundation (1998):** [Efficient Global Optimization of Expensive Black-Box Functions](https://doi.org/10.1023/A:1008306431147) · `wrk:503af97c75e2c1f2107b`
- **Review (2016):** [Taking the Human Out of the Loop: A Review of Bayesian Optimization](https://doi.org/10.1109/JPROC.2015.2494218) · `wrk:e11090ed9cf277298a85`

### Foundation relations

- `specializes` → `meta:scientific-discovery:bayesian-experimental-design` — Acquisition functions approximate experiment utility.
- `depends_on` → `meta:scientific-discovery:adaptive-experiment-inference` — Adaptive query selection changes inferential interpretation.

### Comment

The loop’s epistemic state should include failed evaluations, constraints, and acquisition history. Hiding them creates irreproducible adaptive selection.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `305d8d9838147181b6da6a7b8bfc1f00c212bba29f12d482c36d89c55b2cfe10`

---

## `meta:scientific-discovery:optimal-design-d-optimality` — Experimental Designs Can Maximize Parameter Identifiability Through Information-Matrix Geometry

**Epistemic type:** optimal design theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_statistics_result`  
**Introduced / developed:** 1950s–present  
**Tags:** `d-optimality`, `fisher-information`, `identifiability`, `experimental-design`

### Argument & interpretation

For parametric models, the Fisher information matrix quantifies local parameter sensitivity. D-optimal designs maximize its determinant, minimizing the generalized volume of the asymptotic confidence ellipsoid and encouraging measurements that jointly identify all parameter directions.

### Boundary & conditions

- The criterion is local to a model, nominal parameters, and asymptotic approximation.
- Poor model specification or unmodeled nonlinearities can defeat the design.
- Other criteria may better target prediction, a subset of parameters, robustness, or decisions.

### Application

- laboratory design
- system identification
- sensor placement
- dose selection
- industrial experiments

### Basics

Kiefer and Wolfowitz developed equivalence theory for optimal experimental design around 1960, connecting continuous design measures and finite designs.

### Paper / work evidence

- **Foundation (1960):** [The Equivalence of Two Extremum Problems](https://doi.org/10.1214/aoms/1177705902) · `wrk:f344f401ee96f27dd6ae`
- **Textbook (2006):** [Optimal Design of Experiments](https://doi.org/10.1137/1.9780898719109) · `wrk:e1820eb7782a818fef7b`

### Foundation relations

- `depends_on` → `meta:statistics-causality:cramer-rao` — Information geometry bounds parameter variance.
- `analogous_to` → `meta:scientific-discovery:bayesian-experimental-design` — Both optimize an explicit experiment utility.

### Comment

D-optimality is a geometric criterion, not a universal definition of an informative experiment. The target estimand must be recorded.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `ad91d867b61e175362571300523bd210be48b5281981b7124feece9ce46e9792`

---

## `meta:scientific-discovery:bayesian-experimental-design` — Experiments Should Be Chosen to Maximize Expected Information or Decision Value

**Epistemic type:** Bayesian design principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_discovery_principle`  
**Introduced / developed:** 1956–present  
**Tags:** `experimental-design`, `information-gain`, `bayesian`, `active-science`

### Argument & interpretation

Given current uncertainty over hypotheses or parameters and a model of possible outcomes, an experiment can be ranked by expected reduction in uncertainty or expected improvement in a downstream decision. Bayesian experimental design formalizes the value of asking the most discriminating question rather than merely collecting more data.

### Boundary & conditions

- The utility depends on the prior, likelihood, candidate experiment set, and downstream objective.
- Misspecified models can make an apparently informative experiment misleading.
- Computing expected utility may itself require expensive approximation.

### Application

- autonomous laboratories
- clinical trials
- sensor placement
- scientific discovery agents
- active measurement

### Basics

Dennis Lindley developed a decision-theoretic theory of experimental design in 1956; modern Bayesian design uses simulation and optimization to select informative interventions.

### Paper / work evidence

- **Foundation (1956):** [On a Measure of the Information Provided by an Experiment](https://doi.org/10.1214/aoms/1177728069) · `wrk:4b099374189a426483f3`
- **Review (2019):** [Bayesian Experimental Design: A Review](https://doi.org/10.1214/17-BA1068) · `wrk:13aa369ada048b30e3f7`

### Foundation relations

- `specializes` → `meta:foundations:bayesian-updating` — Experiment selection operationalizes value of information.
- `generalizes` → `meta:scientific-discovery:active-learning` — Active learning is a supervised-learning specialization of adaptive design.

### Comment

Information gain is not synonymous with scientific or social value. Costs, safety, identifiability, and actionability should remain separate terms.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `0a871211b86e4d135e22e9fda7242fe6c624d4485c7aabf4e9da81f89dcea2eb`

---

## `meta:scientific-discovery:active-learning` — Labels or Measurements Should Be Requested Where They Most Improve the Model

**Epistemic type:** active learning principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_machine_learning_discovery_principle`  
**Introduced / developed:** 1990s–present  
**Tags:** `active-learning`, `query-selection`, `sample-efficiency`, `annotation`

### Argument & interpretation

When obtaining labels or experiments is costly, a learner can adaptively choose which examples to query using uncertainty, disagreement, diversity, expected error reduction, or decision value. The objective is better sample efficiency than passive random acquisition under a specified target distribution.

### Boundary & conditions

- Uncertainty can be miscalibrated under distribution shift.
- Adaptive sampling changes the observed data distribution and can create bias.
- Outliers may be uncertain but scientifically uninformative or unsafe.

### Application

- annotation
- materials discovery
- drug screening
- robot learning
- adaptive sensing

### Basics

Query learning and optimal design precursors matured into active learning in the 1990s; disagreement-based and Bayesian approaches established formal sample-complexity results.

### Paper / work evidence

- **Foundation (1996):** [Neural Network Exploration Using Optimal Experiment Design](https://doi.org/10.1162/neco.1996.8.4.679) · `wrk:4a4201f6239f0cd35b6e`
- **Survey (2009):** [Active Learning Literature Survey](https://minds.wisconsin.edu/handle/1793/60660) · `wrk:8e013bd4539907f876f3`

### Foundation relations

- `specializes` → `meta:scientific-discovery:bayesian-experimental-design` — Active learning chooses labels as experiments.
- `depends_on` → `meta:statistics-causality:missing-data-mechanisms` — Adaptive acquisition alters which observations are seen.

### Comment

A claimed label saving must be evaluated on a fixed target distribution and include the selection and annotation costs.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `916abb0201d6e23256caebbaa68729a72df5ce89deb71faf32fcfd4c0d93f253`

---

## `meta:scientific-discovery:fair-principles` — Scientific Data and Workflows Gain Reuse Value When They Are Findable, Accessible, Interoperable, and Reusable

**Epistemic type:** research data stewardship principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `global_research_infrastructure_consensus`  
**Introduced / developed:** 2016–present  
**Tags:** `fair`, `metadata`, `interoperability`, `reusability`

### Argument & interpretation

Research objects should carry persistent identifiers, rich metadata, standardized access mechanisms, interoperable semantics, provenance, and clear reuse conditions. FAIRness concerns machine-actionable discovery and reuse and does not require that all sensitive data be openly downloadable.

### Boundary & conditions

- FAIR is distinct from open, free, ethical, secure, or high quality.
- Metadata standards differ by domain and can impose costs.
- Access restrictions may be necessary for privacy, sovereignty, or intellectual property.

### Application

- data repositories
- Principles Cloud
- biomedicine
- earth science
- reproducible workflows

### Basics

Wilkinson and colleagues published the FAIR Guiding Principles in 2016; funders, repositories, and research infrastructures adopted them widely.

### Paper / work evidence

- **Foundation (2016):** [The FAIR Guiding Principles for scientific data management and stewardship](https://doi.org/10.1038/sdata.2016.18) · `wrk:c8e1a46002c6cdbd316c`
- **Implementation-Guidance (2016):** [FAIR Principles](https://www.go-fair.org/fair-principles/) · `wrk:7ab6cd131b7e38c8fa0f`

### Foundation relations

- `specializes` → `meta:foundations:evidence-provenance` — Reusable objects require traceable origin and transformations.
- `depends_on` → `meta:foundations:evidence-provenance` — Shared schemas and identifiers enable machine reuse.

### Comment

Principia’s paper-free packages can be FAIR through resolvable metadata, schemas, provenance, and explicit access policy without copying source works.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `7f68f51cac46e8fcb11054fcf256cb7250f9e7c28659d6a943bdf14af6c27942`

---

## `meta:scientific-discovery:publication-bias-file-drawer` — Selective Publication Distorts the Visible Evidence Base Toward Positive and Novel Results

**Epistemic type:** meta-research observation  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_meta_science_result`  
**Introduced / developed:** 1979–present  
**Tags:** `publication-bias`, `file-drawer`, `meta-research`, `selection`

### Argument & interpretation

When studies with statistically significant, positive, or novel results are more likely to be published, the literature overrepresents larger effects and underrepresents null or contradictory evidence. The observed corpus is then a selected sample of conducted research.

### Boundary & conditions

- Bias differs by field, design, journal, preregistration, and reporting norms.
- Funnel asymmetry has alternative causes and is not definitive proof.
- Publication is only one selection stage; outcome switching and citation bias also matter.

### Application

- systematic review
- meta-analysis
- Principles Cloud maintenance
- clinical evidence
- research policy

### Basics

Robert Rosenthal described the “file drawer problem” in 1979; trial registries, reporting guidelines, and registered reports were developed in response.

### Paper / work evidence

- **Foundation (1979):** [The file drawer problem and tolerance for null results](https://doi.org/10.1037/0033-2909.86.3.638) · `wrk:06a51bb624eb04dfd0f5`
- **Empirical-Evidence (2004):** [Empirical evidence for selective reporting of outcomes in randomized trials](https://doi.org/10.1001/jama.291.20.2457) · `wrk:0105693c63b9651cb0aa`

### Foundation relations

- `specializes` → `meta:statistics-causality:missing-data-mechanisms` — The published literature is selected on outcome and novelty.
- `contradicts` → `meta:scientific-discovery:preregistration-registered-reports` — Registered Reports reduce outcome-dependent publication.

### Comment

A Cloud built only from published papers inherits publication selection. Negative evidence, registrations, and replication outcomes need explicit ingestion channels.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `471445f3bfcacccc6700b5939edc4299bd19b5209206e97a77c164651be1aee7`

---

## `meta:scientific-discovery:preregistration-registered-reports` — Separating Confirmatory Plans from Post-Hoc Exploration Reduces Researcher Degrees of Freedom

**Epistemic type:** research governance principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_open_science_consensus`  
**Introduced / developed:** 2013–present  
**Tags:** `preregistration`, `registered-reports`, `open-science`, `confirmatory`

### Argument & interpretation

Preregistration timestamps hypotheses, outcomes, exclusions, and analyses before observing the relevant results. Registered Reports add peer review before data collection and publication in principle independent of outcome, reducing selective reporting and clarifying which analyses are confirmatory versus exploratory.

### Boundary & conditions

- Preregistration quality varies and does not prevent mistakes or misconduct.
- Exploration remains scientifically valuable when labeled transparently.
- Unexpected contingencies may require documented deviations.

### Application

- clinical research
- psychology
- economics
- benchmark evaluation
- high-stakes empirical science

### Basics

Clinical trial registration predates the modern open-science movement; Registered Reports were developed in the 2010s, and preregistration became a broad reform strategy after replication concerns.

### Paper / work evidence

- **Foundation (2013):** [Registered Reports: A new publishing initiative at Cortex](https://doi.org/10.1016/j.cortex.2012.12.016) · `wrk:f9824348d0e71e90f4ce`
- **Synthesis (2018):** [The preregistration revolution](https://doi.org/10.1073/pnas.1708274114) · `wrk:97440c49abf0ed48c845`

### Foundation relations

- `specializes` → `meta:foundations:evidence-provenance` — A timestamped plan separates prior commitments from later adaptation.
- `contradicts` → `meta:scientific-discovery:publication-bias-file-drawer` — Outcome-independent review reduces selective publication.

### Comment

Preregistration is a provenance tool, not a truth certificate. Deviations and exploratory discoveries should be preserved rather than hidden.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `e3e977762326b3a4754d3dd3c28efe32ef919e5f6b29f0cc8ab7264d90f3b697`

---

## `meta:scientific-discovery:sequential-probability-ratio` — Sequential Tests Can Stop Once Accumulated Likelihood Evidence Crosses Calibrated Boundaries

**Epistemic type:** sequential testing theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_statistics_result`  
**Introduced / developed:** 1945–present  
**Tags:** `sprt`, `sequential-testing`, `likelihood-ratio`, `stopping`

### Argument & interpretation

For testing two simple hypotheses, the sequential probability ratio test accumulates log likelihood ratios and stops when evidence crosses acceptance boundaries. Under its assumptions it minimizes expected sample size among tests with specified type-I and type-II error rates.

### Boundary & conditions

- The classical optimality result is for simple hypotheses and independent observations.
- Optional stopping remains valid only because the stopping rule is part of the test design.
- Composite, adaptive, dependent, or continuously monitored settings require generalized martingale or always-valid methods.

### Application

- clinical monitoring
- online experiments
- quality control
- adaptive science
- anomaly detection

### Basics

Abraham Wald developed sequential analysis during World War II and published the SPRT framework in 1945–1947.

### Paper / work evidence

- **Foundation (1945):** [Sequential Tests of Statistical Hypotheses](https://doi.org/10.1214/aoms/1177731118) · `wrk:3ce9511481cd2ed12c77`
- **Book (1947):** [Sequential Analysis](https://store.doverpublications.com/products/9780486615790) · `wrk:a32fd62d05ecb34f55a2`

### Foundation relations

- `specializes` → `meta:foundations:sequential-evidence-stopping` — SPRT is a formally calibrated stopping rule.
- `motivates` → `meta:scientific-discovery:adaptive-experiment-inference` — Modern online experiments generalize sequential validity.

### Comment

Sequential evidence is not ordinary fixed-horizon significance applied repeatedly. The boundary and stopping policy must be explicit.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `dd51619997b1e54fc627c44c8fe1c9aadc20883d12b204601e77a07f6ec8563b`

---

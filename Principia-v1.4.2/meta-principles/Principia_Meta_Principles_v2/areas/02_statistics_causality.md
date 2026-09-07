# Statistics and Causal Inference Meta-Principles

> **Area ID:** `statistics-causality`  
> **Records:** 25  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:statistics-causality:regression-discontinuity` — A Sharp Assignment Threshold Can Identify a Local Causal Effect

**Epistemic type:** regression discontinuity identification principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_quasi_experimental_result`  
**Introduced / developed:** 1960–present  
**Tags:** `regression-discontinuity`, `threshold`, `quasi-experiment`, `local-effect`

### Argument & interpretation

When treatment assignment changes discontinuously at a threshold while untreated potential outcomes vary smoothly, the discontinuity in outcomes identifies a local treatment effect at the cutoff. The design turns a policy rule into a quasi-experiment.

### Boundary & conditions

- Units may manipulate the running variable near the cutoff.
- Continuity and no-other-discontinuity assumptions must be defended.
- The effect is local to the threshold and may not transport broadly.

### Application

- policy evaluation
- education
- public health
- industrial threshold rules
- clinical eligibility

### Basics

Thistlethwaite and Campbell introduced the design in 1960. Modern econometrics developed identification, bandwidth selection, manipulation tests, and robust inference.

### Paper / work evidence

- **Foundation (1960):** [Regression-Discontinuity Analysis: An Alternative to the Ex Post Facto Experiment](https://doi.org/10.1037/h0044319) · `wrk:f29da9a74a5ebc022ad3`
- **Refinement (2001):** [Identification and Estimation of Treatment Effects with a Regression-Discontinuity Design](https://doi.org/10.1111/1468-0262.00183) · `wrk:3b676690c831e8830f0b`

### Foundation relations

- `motivates` → `meta:statistics-causality:exchangeability` — The cutoff supplies a local design substitute for global exchangeability.

### Comment

Principia should encode the cutoff, running variable, bandwidth, and manipulation diagnostics as part of the Principle scope.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `5ad05083b1e9b8efd604e0d2be9c7c8fcee04383901629150e07577f5ab12a33`

---

## `meta:statistics-causality:central-limit` — Aggregated Fluctuations Often Approach Gaussian Form

**Epistemic type:** central limit theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `central-limit`, `gaussian`, `aggregation`, `sampling`

### Argument & interpretation

Under broad but explicit conditions, normalized sums of many contributions converge in distribution to a Gaussian law. This supports approximate uncertainty intervals and explains recurring bell-shaped aggregate noise even when components are non-Gaussian.

### Boundary & conditions

- Heavy-tailed variables with infinite variance may converge to stable non-Gaussian laws.
- Dependence, heterogeneity, and finite samples can produce slow or failed Gaussian approximation.
- The theorem concerns sums, not arbitrary nonlinear estimators.

### Application

- error analysis
- sampling distributions
- signal aggregation
- Monte Carlo
- statistical mechanics

### Basics

De Moivre and Laplace developed early forms; Lyapunov, Lindeberg, Lévy, and others established modern general conditions.

### Paper / work evidence

- **Foundation (2020):** [Central Limit Theorem](https://encyclopediaofmath.org/wiki/Central_limit_theorem) · `wrk:0a026469d13e1edb1c43`
- **Reference (1971):** [An Introduction to Probability Theory and Its Applications, Vol. II](https://www.wiley.com/en-us/An+Introduction+to+Probability+Theory+and+Its+Applications%2C+Volume+2%2C+2nd+Edition-p-9780471257097) · `wrk:feca7a4bd821fe2bf7b5`

### Comment

Gaussian assumptions should be justified by an aggregation mechanism and diagnostics, not used by default. Tail-sensitive Principles need explicit finite-sample or extreme-value analysis.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `2ebbb7c7343aceb1467f013ced85477a7dd77b79d3d492a2e16d98ab1e53a41b`

---

## `meta:statistics-causality:simpson-paradox` — Aggregation Can Reverse Conditional Associations

**Epistemic type:** statistical paradox  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `simpson-paradox`, `aggregation`, `conditioning`, `confounding`

### Argument & interpretation

An association observed in aggregated data can disappear or reverse after conditioning on a third variable. The correct aggregation depends on the causal and sampling structure; neither marginal nor conditional association is universally privileged.

### Boundary & conditions

- Conditioning on a confounder may clarify causation, while conditioning on a collider can create bias.
- Noncollapsibility can change effect measures even without confounding.
- The paradox is a warning about structure, not a rule always to stratify.

### Application

- observational studies
- fairness analysis
- multi-site data
- clinical outcomes
- business analytics

### Basics

Yule and Pearson discussed related association reversals; Edward Simpson formalized the phenomenon in 1951. Causal diagrams later clarified when aggregation or conditioning is appropriate.

### Paper / work evidence

- **Foundation (1951):** [The Interpretation of Interaction in Contingency Tables](https://doi.org/10.1111/j.2517-6161.1951.tb00088.x) · `wrk:2cc8710a4a54ed14f80a`
- **Causal Interpretation (1995):** [Causal Diagrams for Empirical Research](https://doi.org/10.1093/biomet/82.4.669) · `wrk:8c95f90d314217f0bf74`

### Comment

Principia should preserve subgroup and aggregation definitions. A Meta-Principle linking should ask whether the paper-level relation survives relevant stratification.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8a78c0818c7752411e6804d65bc83112187f0f17a88d7e301a8fd7bcd862d3de`

---

## `meta:statistics-causality:instrumental-variables-late` — An Instrument Identifies a Local Effect Only Under Strong Exclusion and Compliance Assumptions

**Epistemic type:** instrumental-variable identification theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_econometric_result`  
**Introduced / developed:** 1920s–1996  
**Tags:** `instrumental-variables`, `late`, `identification`, `weak-instruments`

### Argument & interpretation

A valid instrument changes treatment while affecting the outcome only through treatment and remaining independent of unmeasured outcome determinants. With heterogeneous compliance and monotonicity, the Wald ratio identifies a local average treatment effect for compliers rather than a universal effect.

### Boundary & conditions

- Exclusion, independence, relevance, and monotonicity are substantive assumptions.
- Weak instruments produce unstable estimates and invalid conventional inference.
- The complier population may differ from the decision target.

### Application

- econometrics
- clinical encouragement designs
- Mendelian randomization
- policy evaluation
- causal discovery

### Basics

Instrumental variables arose in early econometrics; Imbens and Angrist formalized LATE in 1994, work recognized by the 2021 Prize in Economic Sciences.

### Paper / work evidence

- **Foundation (1994):** [Identification and Estimation of Local Average Treatment Effects](https://doi.org/10.2307/2951620) · `wrk:14d032e4a8f369c2dd1d`
- **Recognition (2021):** [The Sveriges Riksbank Prize in Economic Sciences 2021](https://www.nobelprize.org/prizes/economic-sciences/2021/summary/) · `wrk:375a2a8a939dbc7bae18`

### Foundation relations

- `specializes` → `meta:statistics-causality:identifiability` — IV assumptions create an identifiable local causal estimand.

### Comment

An IV-based Principle should expose whose effect is identified and why the exclusion restriction is credible.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `8ebbe2bd4d6e09311aaff6caca64d2ed1f54cae60fa766295dfb615ef6f0387e`

---

## `meta:statistics-causality:law-large-numbers` — Averages Stabilize Under Repeated Sampling Assumptions

**Epistemic type:** law of large numbers  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `law-large-numbers`, `averaging`, `sampling`, `convergence`

### Argument & interpretation

For independent or suitably weakly dependent observations with appropriate moments, sample averages converge to their expected value. The law of large numbers explains why aggregation can reveal stable rates despite individual randomness.

### Boundary & conditions

- Independence, stationarity, integrability, or mixing conditions cannot be ignored.
- Heavy tails, common shocks, selection, and nonstationarity can prevent useful convergence.
- Convergence says little about finite-sample speed without concentration or variance information.

### Application

- sampling
- Monte Carlo
- experimental averages
- risk estimation
- distributed sensing

### Basics

Bernoulli proved an early form in 1713; Chebyshev, Markov, Kolmogorov, and others generalized weak and strong laws in the nineteenth and twentieth centuries.

### Paper / work evidence

- **Foundation (2020):** [The Strong Law of Large Numbers](https://encyclopediaofmath.org/wiki/Strong_law_of_large_numbers) · `wrk:89d98caf499444a95b74`
- **Formalization (1933):** [Foundations of the Theory of Probability](https://archive.org/details/foundationsofthe00kolm) · `wrk:b16f48709ab32bfaec58`

### Comment

A large dataset is not automatically informative if observations are strongly correlated or systematically selected. Principia should store the effective unit of independence.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `12eec26636fd26b22d5325082503f84eed5d02fb674e77ffe1afa2443e7ad772`

---

## `meta:statistics-causality:exchangeability` — Causal Comparison Requires Exchangeability or a Design Substitute

**Epistemic type:** causal assumption  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `exchangeability`, `confounding`, `adjustment`, `causal-identification`

### Argument & interpretation

Conditional exchangeability states that, after adjustment for covariates $L$, treatment assignment is independent of potential outcomes: $Y(a)\perp A\mid L$. Randomization creates it by design; observational studies must justify it through measured confounders and substantive knowledge.

### Boundary & conditions

- Unmeasured confounding violates exchangeability and is not diagnosed by balance on observed variables.
- Overadjustment for mediators or colliders can introduce bias.
- Exchangeability may hold for one population or time but not another.

### Application

- observational causal inference
- clinical effectiveness
- econometrics
- policy analysis

### Basics

The concept derives from probability and experimental design. Potential-outcome and graphical frameworks made conditional exchangeability a central identification condition.

### Paper / work evidence

- **Foundation (1983):** [The Central Role of the Propensity Score in Observational Studies for Causal Effects](https://doi.org/10.1093/biomet/70.1.41) · `wrk:8adbf7bde72ab05892aa`
- **Refinement (2011):** [Causal Knowledge as a Prerequisite for Confounding Evaluation](https://doi.org/10.1093/aje/kwq368) · `wrk:b31ff686bf4db5158306`

### Comment

Principia should never infer exchangeability from predictive accuracy alone. It should preserve the proposed adjustment set and reasons why relevant common causes are measured.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `3cee9ab56155d0ddf29e7525869986ffb0174864e2d0a0eacbacb05d74f16de4`

---

## `meta:statistics-causality:sutva-consistency` — Causal Effects Require Well-Defined Treatments and Potential Outcomes

**Epistemic type:** causal consistency principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `sutva`, `consistency`, `treatment-definition`, `interference`

### Argument & interpretation

The observed outcome under the received treatment must equal the corresponding potential outcome, and treatment versions must be sufficiently well defined. In the common SUTVA formulation, one unit's outcome also does not depend on other units' assignments unless interference is modeled.

### Boundary & conditions

- Interference is common in networks, epidemics, markets, and shared environments.
- Compound interventions with multiple versions can violate consistency.
- Treatment definitions may change over time or across sites.

### Application

- randomized trials
- policy evaluation
- network experiments
- causal machine learning

### Basics

Potential outcomes trace to Neyman; Rubin articulated SUTVA and consistency in modern causal inference. Later work developed explicit interference models.

### Paper / work evidence

- **Foundation (1980):** [Randomization Analysis of Experimental Data: The Fisher Randomization Test](https://doi.org/10.1080/01621459.1980.10477512) · `wrk:9678499548d496a8234e`
- **Refinement (2000):** [Interference Between Units in Randomized Experiments](https://doi.org/10.3102/107699860250040425) · `wrk:f607614cf9072d8bdc98`

### Comment

A Principle claiming an intervention effect should name the intervention. ‘Use AI’ or ‘increase quality’ is not a well-defined treatment without implementation details.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `53eaa9316a5d81b930495af6edbb1596d1e37296938e99a2785ebde72c036733`

---

## `meta:statistics-causality:rao-blackwell` — Conditioning on a Sufficient Statistic Cannot Increase Estimation Risk Under Convex Loss

**Epistemic type:** Rao–Blackwell theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_theorem`  
**Introduced / developed:** 1945–1947  
**Tags:** `rao-blackwell`, `sufficiency`, `variance-reduction`, `conditioning`

### Argument & interpretation

Given an estimator and a sufficient statistic, replacing the estimator by its conditional expectation given that statistic yields an estimator with no greater risk under squared or more general convex losses. Irrelevant randomness can therefore be removed without losing parameter information.

### Boundary & conditions

- The improvement is relative to a stated model and sufficient statistic.
- Computing the conditional expectation can be intractable.
- Misspecified sufficiency does not protect against model error.

### Application

- estimator design
- Monte Carlo variance reduction
- survey sampling
- Bayesian computation
- data compression

### Basics

Rao and Blackwell established the theorem independently in the 1940s; it became a core result connecting sufficiency and optimal estimation.

### Paper / work evidence

- **Foundation (1945):** [Information and the Accuracy Attainable in the Estimation of Statistical Parameters](https://doi.org/10.1007/BF02888332) · `wrk:feb74e119e6f31856bf7`
- **Foundation (1947):** [Conditional Expectation and Unbiased Sequential Estimation](https://doi.org/10.1214/aoms/1177730882) · `wrk:e2bb7b53cfb3e86e42f3`

### Foundation relations

- `specializes` → `meta:statistics-causality:sufficiency` — The theorem operationalizes sufficiency as risk reduction.

### Comment

In Principia, this motivates conditioning on scientifically relevant summaries while keeping the model assumptions visible.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `f2ff0a07ef59c31b1655eecc8bcd1542f3005a35be102f2022b0a6314657c23b`

---

## `meta:statistics-causality:false-discovery-rate` — Discovery Lists Require Control of Expected False Proportions

**Epistemic type:** false discovery rate theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `fdr`, `multiple-testing`, `discovery`, `screening`

### Argument & interpretation

When many hypotheses are tested, false-discovery-rate procedures control the expected proportion of false rejections among reported discoveries under stated dependence conditions. This aligns error control with large-scale screening rather than requiring zero family-wise errors.

### Boundary & conditions

- The original Benjamini–Hochberg guarantee assumes independence or certain positive dependence; arbitrary dependence needs modifications.
- FDR is an expectation over repeated studies, not the realized fraction in one list.
- Low FDR does not ensure large effects, correct models, or replicability.

### Application

- genomics
- automated Principle mining
- neuroimaging
- large benchmark suites

### Basics

Benjamini and Hochberg introduced FDR control in 1995; Storey and others developed adaptive and q-value approaches.

### Paper / work evidence

- **Foundation (1995):** [Controlling the False Discovery Rate](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) · `wrk:970336d353e9d54ac3c4`
- **Refinement (2002):** [A Direct Approach to False Discovery Rates](https://doi.org/10.1111/1467-9868.00346) · `wrk:f31750d3bce31cd118fe`

### Comment

An autonomous agent should report the complete candidate universe or a valid approximation. Hidden search makes any multiplicity adjustment unreliable.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `982cc3b8cfaf74c5e01bd97f47c5a4660a64984a6cb0d55931601328d4a4b46c`

---

## `meta:statistics-causality:positivity` — Effects Are Learnable Only Where Treatment Alternatives Have Support

**Epistemic type:** positivity assumption  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `positivity`, `overlap`, `support`, `extrapolation`

### Argument & interpretation

For every covariate stratum relevant to the target population, each compared treatment must have nonzero probability. Without overlap, observed data contain no counterfactual comparison for unsupported regions, and estimates rely on extrapolation.

### Boundary & conditions

- Near-violations can cause extreme weights and unstable estimates even when probabilities are technically nonzero.
- Structural positivity violations may require redefining the target population or intervention.
- High-dimensional covariates make overlap difficult to assess.

### Application

- causal inference
- personalized medicine
- policy evaluation
- off-policy learning

### Basics

Positivity is embedded in causal identification results and survey weighting. Modern propensity-score and targeted-learning methods emphasize diagnostics and truncation.

### Paper / work evidence

- **Foundation (2020):** [Causal Inference: What If](https://www.hsph.harvard.edu/miguel-hernan/causal-inference-book/) · `wrk:be9a66e196b5e7a67825`
- **Application (2008):** [Practical Positivity Violations in Longitudinal Marginal Structural Models](https://doi.org/10.1097/EDE.0b013e31815b0f9f) · `wrk:3e19426cf76fcf2799ff`

### Comment

A new Principle should state its empirical support region. Universal treatment claims based on one narrow operating regime violate this root.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `39120e8950b8162a96d5cbffcb2727ce51fd716a8b02786f6fee9765ed5a2ce2`

---

## `meta:statistics-causality:bootstrap` — Empirical Resampling Approximates Sampling Uncertainty Under Stability Conditions

**Epistemic type:** bootstrap principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `bootstrap`, `resampling`, `uncertainty`, `stability`

### Argument & interpretation

The bootstrap replaces repeated sampling from an unknown population with repeated resampling from the empirical distribution. For smooth statistics under regularity conditions, the bootstrap consistently approximates sampling distributions and supports standard errors and intervals.

### Boundary & conditions

- Naive bootstrap can fail for dependent data, extremes, boundary parameters, non-smooth statistics, or very small samples.
- Block, parametric, wild, or subsampling variants may be required.
- Resampling cannot repair biased sampling or missing populations.

### Application

- uncertainty estimation
- model stability
- small-sample analysis
- algorithm evaluation

### Basics

Bradley Efron introduced the bootstrap in 1979, extending jackknife ideas. Subsequent theory characterized consistency and failure cases.

### Paper / work evidence

- **Foundation (1979):** [Bootstrap Methods: Another Look at the Jackknife](https://doi.org/10.1214/aos/1176344552) · `wrk:06b17a1896c1b2e7246e`
- **Reference (1997):** [Bootstrap Methods and Their Application](https://doi.org/10.1017/CBO9780511802843) · `wrk:25d4d7a207bab7d16cd5`

### Comment

Principia should record the resampling unit and scheme. Resampling rows in clustered or temporal data can manufacture false precision.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `7232ceee1aeb4bed6b2564dcc95f9a43f95af89703ca5605b1a62facfc196f51`

---

## `meta:statistics-causality:bayes-rule` — Evidence Updates Odds by a Likelihood Ratio

**Epistemic type:** Bayes theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_theorem`  
**Introduced / developed:** 1763–present  
**Tags:** `bayes`, `likelihood-ratio`, `posterior`, `evidence`

### Argument & interpretation

Bayes’ rule decomposes posterior belief into prior belief and evidential fit: $P(H\mid E)=P(E\mid H)P(H)/P(E)$. In odds form, posterior odds equal prior odds multiplied by a likelihood ratio, making the contribution of new evidence explicit.

### Boundary & conditions

- The theorem is exact, but conclusions depend on the chosen hypotheses, prior, and likelihood.
- A posterior probability is conditional on the model and is not a model-free truth probability.
- Poorly calibrated or dependent evidence can dominate the update.

### Application

- diagnosis
- model comparison
- sequential learning
- forecasting
- sensor fusion

### Basics

Thomas Bayes’s posthumous essay appeared in 1763; Laplace generalized inverse probability and developed its scientific use.

### Paper / work evidence

- **Foundation (1763):** [An Essay towards Solving a Problem in the Doctrine of Chances](https://doi.org/10.1098/rstl.1763.0053) · `wrk:46a8ff0371d05d7cd21f`
- **Modern Reference (2013):** [Bayesian Data Analysis](https://doi.org/10.1201/b16018) · `wrk:cc088e595ee4e229d153`

### Foundation relations

- `refines` → `meta:statistics-causality:likelihood-and-evidence` — Bayes rule converts relative likelihood and prior odds into posterior odds.

### Comment

Principia should retain the exact competing hypotheses and prior source when it uses Bayesian support to update a Principle.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `38e640abf306c32456aa0f2d99543a365f42c56fff76777fcee3b61a9cff7461`

---

## `meta:statistics-causality:conformal-coverage` — Exchangeability Enables Distribution-Free Marginal Predictive Coverage

**Epistemic type:** conformal prediction theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_landmark`  
**Introduced / developed:** 1998–present  
**Tags:** `conformal-prediction`, `coverage`, `calibration`, `distribution-free`

### Argument & interpretation

Conformal prediction wraps a predictive model with calibration scores to produce sets or intervals satisfying finite-sample marginal coverage, typically $P\{Y_{n+1}\in C(X_{n+1})\}\ge 1-lpha$, under exchangeability. The guarantee is model-agnostic but not automatically conditional on every subgroup or input.

### Boundary & conditions

- Exchangeability or an appropriate online symmetry is required.
- Marginal coverage can hide poor conditional coverage for important subgroups.
- Adaptive reuse of calibration data and distribution shift require modified methods.

### Application

- uncertainty quantification
- medical prediction
- LLM output sets
- risk control
- distribution-free inference

### Basics

Vovk, Gammerman, and collaborators developed conformal prediction in the 1990s; modern split and adaptive variants made it widely practical.

### Paper / work evidence

- **Foundation (2005):** [Algorithmic Learning in a Random World](https://link.springer.com/book/10.1007/b106715) · `wrk:760308875ce887317514`
- **Refinement (2018):** [Distribution-Free Predictive Inference for Regression](https://doi.org/10.1080/01621459.2017.1307116) · `wrk:c00d4eafca681160bf6b`

### Foundation relations

- `refines` → `meta:statistics-causality:calibration` — Conformal methods provide explicit set-coverage calibration under exchangeability.

### Comment

Principia should label the exact coverage target—marginal, group-conditional, risk-controlling, or time-uniform—rather than displaying a generic confidence badge.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `83deb858a7a469f8c08c05cc0f18160b9eb2f55e563d659e0f2448c8364d902d`

---

## `meta:statistics-causality:de-finetti-exchangeability` — Exchangeable Sequences Behave as Mixtures of IID Processes

**Epistemic type:** de Finetti representation theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_theorem`  
**Introduced / developed:** 1930s  
**Tags:** `exchangeability`, `mixtures`, `iid`, `symmetry`

### Argument & interpretation

An infinite sequence of binary random variables is exchangeable if and only if its joint law is a mixture of IID Bernoulli laws. More general representation theorems show that symmetry assumptions can induce latent-variable structures without assuming literal independence.

### Boundary & conditions

- The classical theorem concerns infinite exchangeable sequences; finite forms are approximate.
- Partial exchangeability yields different latent structures.
- Exchangeability is an assumption about invariance under permutations, not an empirical fact guaranteed by random sampling labels.

### Application

- Bayesian modeling
- hierarchical models
- causal exchangeability
- population inference
- sequence modeling

### Basics

Bruno de Finetti formulated the representation in the 1930s; Hewitt and Savage generalized it to broader spaces.

### Paper / work evidence

- **Foundation (1931):** [Funzione caratteristica di un fenomeno aleatorio](https://doi.org/10.1007/BF03014853) · `wrk:191c411f396b60a54fe7`
- **Generalization (1955):** [Symmetric measures on Cartesian products](https://doi.org/10.1090/S0002-9947-1955-0076206-8) · `wrk:8da57835aaa2839404fd`

### Foundation relations

- `refines` → `meta:statistics-causality:exchangeability` — The representation theorem gives a structural interpretation of exchangeability.

### Comment

This theorem clarifies why exchangeability can justify latent-mixture models, while also exposing the strength of the symmetry assumption.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `8acb564e6a78415eb722cf733052686ce0c1f59df3a2e3f8a9d420f6a3be7a4c`

---

## `meta:statistics-causality:regression-to-mean` — Extreme Observations Tend to Be Followed by Less Extreme Ones Without Intervention

**Epistemic type:** statistical phenomenon  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `regression-to-mean`, `selection`, `longitudinal`, `controls`

### Argument & interpretation

When repeated measurements contain random variation, selecting units for extreme initial values causes later values to move toward the population mean on average, even if no causal change occurs. The effect follows imperfect correlation between measurements.

### Boundary & conditions

- Regression to the mean depends on selection on noisy extremes and repeat-measure correlation.
- Real interventions can occur simultaneously; controls are needed to separate them.
- The relevant mean may shift under nonstationarity.

### Application

- clinical improvement
- quality control
- sports performance
- anomaly remediation
- policy evaluation

### Basics

Francis Galton described regression toward mediocrity in hereditary data in the 1880s. The concept became fundamental to experimental controls and longitudinal analysis.

### Paper / work evidence

- **Foundation (1886):** [Regression towards Mediocrity in Hereditary Stature](https://doi.org/10.2307/2841583) · `wrk:c5ec7348628defa29a95`
- **Application (1998):** [Regression to the Mean: What It Is and How to Deal with It](https://doi.org/10.1093/ije/27.4.532) · `wrk:cb7ca8b248ccb85451d0`

### Comment

Before attributing improvement after selecting failures, Principia should compare untreated or historical controls and model measurement noise.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `b07afed6257e67665725bd6752d851190a9bab5e45e053db031566e32e5190e6`

---

## `meta:statistics-causality:cramer-rao` — Fisher Information Lower-Bounds the Variance of Unbiased Estimators

**Epistemic type:** Cramér–Rao bound  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_theorem`  
**Introduced / developed:** 1940s  
**Tags:** `fisher-information`, `estimation`, `lower-bound`, `precision`

### Argument & interpretation

Under regularity conditions, the covariance of an unbiased estimator is bounded below by the inverse Fisher information. The bound links experimental sensitivity, sample size, and attainable precision, and supplies a benchmark for efficient estimation.

### Boundary & conditions

- Unbiasedness and differentiability regularity conditions matter.
- The bound may be unattainable at finite sample size or with nuisance parameters.
- Biased estimators can have lower mean-squared error than the unbiased bound suggests.

### Application

- experimental design
- sensor precision
- parameter estimation
- quantum metrology
- system identification

### Basics

Cramér and Rao independently developed information bounds in the 1940s, building on Fisher’s information concept.

### Paper / work evidence

- **Foundation (1945):** [Information and the Accuracy Attainable in the Estimation of Statistical Parameters](https://doi.org/10.1007/BF02888332) · `wrk:feb74e119e6f31856bf7`
- **Foundation (1946):** [Mathematical Methods of Statistics](https://press.princeton.edu/books/paperback/9780691005633/mathematical-methods-of-statistics) · `wrk:7aebcc2d0c41eeb22fba`

### Foundation relations

- `depends_on` → `meta:statistics-causality:identifiability` — Positive Fisher information requires local identifiability.

### Comment

Use the bound as an information-limited precision target, not as evidence that a specific estimator or instrument is unbiased.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `392d2a2ff4c99c7856ffbbd1e2cdd2883da091c028312eddc531454cc1aa8519`

---

## `meta:statistics-causality:likelihood-and-evidence` — Likelihood Measures Relative Support Within a Statistical Model

**Epistemic type:** inference principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `likelihood`, `evidence`, `model-comparison`, `inference`

### Argument & interpretation

For observed data $x$ and parameter $\theta$, the likelihood $L(\theta;x)=p_\theta(x)$ compares how well parameter values predict the realized data under a declared model. Likelihood ratios provide relative evidence within that model; they are not probabilities over parameters unless combined with a prior.

### Boundary & conditions

- Likelihood depends on the specified sampling model and can be misleading under misspecification.
- Optional stopping and selection require care depending on the inferential framework.
- Likelihood alone does not encode decision costs, prior plausibility, or causal identification.

### Application

- parameter estimation
- model comparison
- scientific evidence scoring
- sequential analysis

### Basics

Fisher developed likelihood as a central statistical concept in the 1920s. Neyman–Pearson theory formalized likelihood-ratio testing for simple hypotheses.

### Paper / work evidence

- **Foundation (1922):** [On the Mathematical Foundations of Theoretical Statistics](https://doi.org/10.1098/rsta.1922.0009) · `wrk:b6b7409a974356f6deb4`
- **Formalization (1933):** [On the Problem of the Most Efficient Tests of Statistical Hypotheses](https://doi.org/10.1098/rsta.1933.0009) · `wrk:5482fcd2e3c967328c56`

### Comment

Principia should store the compared model class. A high likelihood cannot validate assumptions omitted from every candidate model.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `6c993923a0d2915c09b25387e3da3ed22c6169c45ed5b2ded77c50630d1a88e5`

---

## `meta:statistics-causality:missing-data-mechanisms` — Missingness Is Part of the Data-Generating Process

**Epistemic type:** missing-data framework  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `missing-data`, `mcar`, `mar`, `mnar`

### Argument & interpretation

Inference from incomplete data depends on why values are missing. Rubin's distinctions—MCAR, MAR, and MNAR—separate missingness independent of data, conditionally explainable missingness, and missingness depending on unobserved values. Ignoring the mechanism can bias estimates and uncertainty.

### Boundary & conditions

- MAR is an assumption conditional on observed variables and is generally not testable from observed data alone.
- Complete-case analysis is valid only in restricted settings.
- Imputation models must preserve uncertainty and substantive relationships.

### Application

- clinical records
- surveys
- sensor failures
- longitudinal studies
- industrial logs

### Basics

Donald Rubin formalized modern missing-data mechanisms in 1976; Little, Rubin, and many others developed likelihood, multiple-imputation, and sensitivity methods.

### Paper / work evidence

- **Foundation (1976):** [Inference and Missing Data](https://doi.org/10.1093/biomet/63.3.581) · `wrk:df81d1c2b8c013d4b9eb`
- **Refinement (1987):** [Multiple Imputation for Nonresponse in Surveys](https://doi.org/10.1002/9780470316696) · `wrk:8f264945c299d05d74ba`

### Comment

‘Missing’ is not a neutral null value. Principia should connect missingness patterns to process events and require sensitivity analysis when MNAR is plausible.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `68745d3e6f858ef2d42fbed1cdde7b5f54ec5f9b4b2207d25ae84f8f940591ec`

---

## `meta:statistics-causality:markov-equivalence` — Observational Data Often Identify a Causal Equivalence Class, Not a Unique DAG

**Epistemic type:** causal graph equivalence theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_causal_boundary`  
**Introduced / developed:** 1990s  
**Tags:** `causal-dag`, `markov-equivalence`, `observational-limits`, `orientation`

### Argument & interpretation

Directed acyclic graphs with the same skeleton and unshielded colliders entail the same conditional-independence relations and are Markov equivalent. Purely observational conditional-independence information therefore generally identifies an equivalence class rather than a unique causal orientation.

### Boundary & conditions

- Faithfulness and causal sufficiency assumptions may fail.
- Interventions, time order, non-Gaussianity, or functional assumptions can orient additional edges.
- Statistical errors in independence tests can alter the recovered class.

### Application

- causal discovery
- system identification
- biological networks
- scientific graph construction

### Basics

Verma and Pearl characterized Markov equivalence; completed partially directed acyclic graphs became a standard representation of observational uncertainty.

### Paper / work evidence

- **Foundation (1990):** [Equivalence and Synthesis of Causal Models](https://ftp.cs.ucla.edu/pub/stat_ser/r150.pdf) · `wrk:d894c52d220df3ade975`
- **Refinement (1997):** [A Characterization of Markov Equivalence Classes for Directed Acyclic Graphs](https://doi.org/10.1214/aos/1032181154) · `wrk:7d178b4cf2e5f1837b7a`

### Foundation relations

- `specializes` → `meta:statistics-causality:identifiability` — Markov equivalence is a concrete non-identifiability result.

### Comment

Principia should not convert one member of an observational equivalence class into a canonical causal relation without extra evidence.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `7f9068948961323b2c1a9527231e961c10eaacf38a3d58363cd80ba2fb849499`

---

## `meta:statistics-causality:neyman-pearson` — Optimal Tests Depend on Explicit Error Trade-offs and Alternatives

**Epistemic type:** Neyman-Pearson lemma  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `hypothesis-testing`, `power`, `errors`, `likelihood-ratio`

### Argument & interpretation

For testing a simple null against a simple alternative at fixed type-I error, the likelihood-ratio test is most powerful. The result makes hypothesis testing a constrained decision problem: evidence thresholds reflect tolerated false positives and the alternative of interest.

### Boundary & conditions

- The lemma does not uniquely solve composite hypotheses, model misspecification, optional selection, or multiple testing.
- Statistical power depends on effect size and design, not only the test rule.
- A low $p$-value does not measure effect importance or posterior truth.

### Application

- experimental testing
- anomaly detection
- quality control
- clinical trials
- benchmark claims

### Basics

Jerzy Neyman and Egon Pearson developed the framework in a series of papers culminating in 1933. It contrasted with Fisher's evidential interpretation of significance tests.

### Paper / work evidence

- **Foundation (1933):** [On the Problem of the Most Efficient Tests of Statistical Hypotheses](https://doi.org/10.1098/rsta.1933.0009) · `wrk:5482fcd2e3c967328c56`

### Comment

Principia should store the decision criterion, error rates, and alternative. Reporting only ‘significant’ hides the operating characteristics that make the result meaningful.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `742057ce7386478f8bebe341c1ad84d88cce7ff8ab37218e04767114e9dd8326`

---

## `meta:statistics-causality:identifiability` — Parameters or Causal Effects Require Distinct Observable Implications

**Epistemic type:** identifiability principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `identifiability`, `observational-equivalence`, `inverse-problem`, `causality`

### Argument & interpretation

A target is identifiable when no two admissible data-generating mechanisms imply the same observed distribution while assigning different target values. Without identifiability, more data from the same regime cannot resolve the ambiguity; new assumptions, measurements, or interventions are required.

### Boundary & conditions

- Identifiability is relative to a model class and observation regime.
- Local, generic, or partial identifiability may be enough for some tasks.
- Numerical instability can make an identifiable target practically unrecoverable.

### Application

- latent-variable models
- causal effects
- inverse problems
- mixture models
- system identification

### Basics

Identifiability has long been central to parametric statistics and econometrics. Modern causal inference separates graphical identification from estimation.

### Paper / work evidence

- **Foundation (1949):** [Identification Problems in the Social Sciences](https://doi.org/10.2307/1911965) · `wrk:6727f4469d3f35424897`
- **Causal Formalization (1995):** [Causal Diagrams for Empirical Research](https://doi.org/10.1093/biomet/82.4.669) · `wrk:8c95f90d314217f0bf74`

### Comment

Principia should not treat precise estimates as evidence of identification. If multiple mechanisms fit equally well, the output must preserve an identified set or unresolved alternatives.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `63c6ac60eae1ee747254db15ca6fcab847e424486240b9e76cce70bed181eb55`

---

## `meta:statistics-causality:calibration` — Probabilistic Predictions Must Match Long-Run Frequencies in Their Reference Class

**Epistemic type:** calibration principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `calibration`, `probability`, `forecasting`, `confidence`

### Argument & interpretation

A forecasting system is calibrated when events assigned probability $p$ occur at frequency approximately $p$ within appropriate groups. Calibration complements discrimination: a model can rank cases well yet systematically overstate or understate risk.

### Boundary & conditions

- Calibration can hold marginally while failing in important subgroups.
- Perfect calibration alone permits uninformative constant forecasts.
- Distribution shift can destroy prior calibration.

### Application

- risk prediction
- weather forecasting
- clinical decision support
- AI confidence
- early warning systems

### Basics

Brier's 1950 score formalized verification of probabilistic forecasts. Reliability diagrams, proper scoring rules, and recalibration methods extended the framework.

### Paper / work evidence

- **Foundation (1950):** [Verification of Forecasts Expressed in Terms of Probability](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2) · `wrk:964a60691a9ea20a00f5`
- **Application (2017):** [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html) · `wrk:8f9820418d8e01ff9a41`

### Comment

Principia should not interpret a language-model confidence phrase as a calibrated probability. Calibration requires repeated outcomes and a declared reference class.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `0dbd652b4f9b0ece2b1bc99a276c0e29a81c30f40ae37f75452f3bea6626ad35`

---

## `meta:statistics-causality:sufficiency` — Sufficient Statistics Preserve Parameter Information Relative to a Model

**Epistemic type:** sufficiency theorem family  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `sufficiency`, `compression`, `statistics`, `information`

### Argument & interpretation

A statistic $T(X)$ is sufficient for parameter $\theta$ when the conditional distribution of $X$ given $T(X)$ does not depend on $\theta$. Under the factorization criterion, data can be compressed to $T$ without losing information about $\theta$ within the assumed family.

### Boundary & conditions

- Sufficiency is model- and parameter-specific; it can discard information relevant to another question.
- Minimal sufficient statistics may not exist in a convenient finite form.
- Robustness to model misspecification is not guaranteed.

### Application

- data reduction
- scientific compression
- distributed inference
- privacy-aware summaries

### Basics

Fisher introduced sufficiency in the 1920s; Neyman and factorization results provided operational characterizations. Exponential families often admit low-dimensional sufficient statistics.

### Paper / work evidence

- **Foundation (1922):** [On the Mathematical Foundations of Theoretical Statistics](https://doi.org/10.1098/rsta.1922.0009) · `wrk:b6b7409a974356f6deb4`
- **Refinement (1935):** [Statistical Estimation When Sufficiency Is Not Necessary](https://doi.org/10.1214/aoms/1177701141) · `wrk:9ae80d277f1278908d9e`

### Comment

This is a formal foundation for compact Principle records, but only for declared inference targets. A summary sufficient for a mean can be useless for tails, causality, or anomalies.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `cfa52f16b891acee057c51cc09e072e9fcebcf4179274b4de55f315d16cfbfd1`

---

## `meta:statistics-causality:transport-formula` — Transport Requires Modeling Population Differences, Not Merely Reweighting Labels

**Epistemic type:** transportability theorem family  
**Principia kind:** `theorem`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `transportability`, `data-fusion`, `population`, `external-validity`

### Argument & interpretation

Causal effects can sometimes be transported by combining an invariant causal mechanism with measured differences between source and target populations. Selection diagrams and transport formulas identify which distributions must be observed in each environment.

### Boundary & conditions

- Transport may be impossible when effect-modifying variables are unmeasured or support is absent.
- Reweighting observed covariates cannot repair changed measurement or intervention definitions.
- The target estimand must be stated before selecting transport variables.

### Application

- multi-site trials
- domain adaptation
- policy transfer
- industrial scale-up

### Basics

Pearl and Bareinboim formalized transportability using causal diagrams in the 2010s, connecting external validity to do-calculus and data fusion.

### Paper / work evidence

- **Foundation (2014):** [External Validity: From Do-Calculus to Transportability Across Populations](https://doi.org/10.1214/14-STS486) · `wrk:91668f3e85522cca2c69`
- **Refinement (2016):** [Data-Fusion Problems with Statistical and Causal Data Sources](https://doi.org/10.1073/pnas.1510507113) · `wrk:e6cdc3ef83bde530649f`

### Comment

This entry refines the cross-domain invariance root. Principia should encode which mechanisms are assumed stable and which population distributions are allowed to differ.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `97de0ba79ffdedc2d607476fd4c63b3f0f64d7ef1cf9bc6e29ece861b600a9d2`

---

## `meta:statistics-causality:interference` — Units Can Causally Affect One Another

**Epistemic type:** causal observation  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `interference`, `spillovers`, `networks`, `causal-effects`

### Argument & interpretation

In networked or shared systems, one unit's treatment can change another unit's outcome. Potential outcomes then depend on an assignment vector or exposure mapping, and direct, spillover, total, and overall effects become distinct targets.

### Boundary & conditions

- Arbitrary interference is high-dimensional and generally not identifiable without structural assumptions.
- Cluster designs help only when cross-cluster interference is negligible.
- Exposure mappings can miss relevant network pathways or timing.

### Application

- epidemiology
- social networks
- multi-agent systems
- marketplaces
- distributed interventions

### Basics

Classical experiments often assumed no interference. Modern causal work by Halloran, Hudgens, Aronow, Samii, and others developed estimands and designs for partial and network interference.

### Paper / work evidence

- **Foundation (2008):** [Causal Inference with Interference](https://doi.org/10.1198/016214508000000292) · `wrk:754e2863c616b8566a2c`
- **Refinement (2017):** [Estimating Average Causal Effects Under General Interference](https://doi.org/10.1214/17-AOAS1008) · `wrk:a38012cf2db31aab5bcb`

### Comment

This Meta-Principle is especially relevant to multi-agent and social systems: treating interactions as independent rows can reverse conclusions about collective interventions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `474a1b925a46f609467d628acf60362af17afb1fddd34fbb498def3925d1930b`

---

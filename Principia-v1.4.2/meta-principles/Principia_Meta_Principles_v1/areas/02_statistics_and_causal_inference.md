# Statistics and Causal Inference: Meta-Principles

This file contains 17 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `statistics-causality`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:statistics-causality:likelihood-and-evidence — Likelihood Measures Relative Support Within a Statistical Model

- **Epistemic type:** `inference principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `likelihood`, `evidence`, `model-comparison`, `inference`

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

- **Foundation:** [On the Mathematical Foundations of Theoretical Statistics](https://doi.org/10.1098/rsta.1922.0009) (1922)
- **Formalization:** [On the Problem of the Most Efficient Tests of Statistical Hypotheses](https://doi.org/10.1098/rsta.1933.0009) (1933)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should store the compared model class. A high likelihood cannot validate assumptions omitted from every candidate model.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `cc55eb71fa89ef13ee10d9cee0d93c1d9c5a244a266f5601834a481f748e5775`</sub>

---

## meta:statistics-causality:sufficiency — Sufficient Statistics Preserve Parameter Information Relative to a Model

- **Epistemic type:** `sufficiency theorem family`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `sufficiency`, `compression`, `statistics`, `information`

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

- **Foundation:** [On the Mathematical Foundations of Theoretical Statistics](https://doi.org/10.1098/rsta.1922.0009) (1922)
- **Refinement:** [Statistical Estimation When Sufficiency Is Not Necessary](https://doi.org/10.1214/aoms/1177701141) (1935)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

This is a formal foundation for compact Principle records, but only for declared inference targets. A summary sufficient for a mean can be useless for tails, causality, or anomalies.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `520fd9eb392cacee1b7ab8ceb0f5f30362299b51abaf265573156a668bf713ec`</sub>

---

## meta:statistics-causality:law-large-numbers — Averages Stabilize Under Repeated Sampling Assumptions

- **Epistemic type:** `law of large numbers`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `law-large-numbers`, `averaging`, `sampling`, `convergence`

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

- **Foundation:** [The Strong Law of Large Numbers](https://encyclopediaofmath.org/wiki/Strong_law_of_large_numbers) (2020)
- **Formalization:** [Foundations of the Theory of Probability](https://archive.org/details/foundationsofthe00kolm) (1933)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

A large dataset is not automatically informative if observations are strongly correlated or systematically selected. Principia should store the effective unit of independence.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `f465988e066a48b90992c933d544aa09ff219f771ecf139eeb3f887b760dca89`</sub>

---

## meta:statistics-causality:central-limit — Aggregated Fluctuations Often Approach Gaussian Form

- **Epistemic type:** `central limit theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `central-limit`, `gaussian`, `aggregation`, `sampling`

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

- **Foundation:** [Central Limit Theorem](https://encyclopediaofmath.org/wiki/Central_limit_theorem) (2020)
- **Reference:** [An Introduction to Probability Theory and Its Applications, Vol. II](https://www.wiley.com/en-us/An+Introduction+to+Probability+Theory+and+Its+Applications%2C+Volume+2%2C+2nd+Edition-p-9780471257097) (1971)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Gaussian assumptions should be justified by an aggregation mechanism and diagnostics, not used by default. Tail-sensitive Principles need explicit finite-sample or extreme-value analysis.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b8b89f1e63b7f76fe06b93c5f602943a747d85e3527d414fac5cf253ae3f8047`</sub>

---

## meta:statistics-causality:identifiability — Parameters or Causal Effects Require Distinct Observable Implications

- **Epistemic type:** `identifiability principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `identifiability`, `observational-equivalence`, `inverse-problem`, `causality`

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

- **Foundation:** [Identification Problems in the Social Sciences](https://doi.org/10.2307/1911965) (1949)
- **Causal formalization:** [Causal Diagrams for Empirical Research](https://doi.org/10.1093/biomet/82.4.669) (1995)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should not treat precise estimates as evidence of identification. If multiple mechanisms fit equally well, the output must preserve an identified set or unresolved alternatives.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `468ae2c7853da9a0f685afac885f4d8cfc349ddd5b4a3940f4e2c44e5db4a13c`</sub>

---

## meta:statistics-causality:neyman-pearson — Optimal Tests Depend on Explicit Error Trade-offs and Alternatives

- **Epistemic type:** `Neyman-Pearson lemma`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `hypothesis-testing`, `power`, `errors`, `likelihood-ratio`

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

- **Foundation:** [On the Problem of the Most Efficient Tests of Statistical Hypotheses](https://doi.org/10.1098/rsta.1933.0009) (1933)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should store the decision criterion, error rates, and alternative. Reporting only ‘significant’ hides the operating characteristics that make the result meaningful.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `67632f4a6ec469a6316b3de87e880a79cc12ca588e2a8412e165377901e181bb`</sub>

---

## meta:statistics-causality:false-discovery-rate — Discovery Lists Require Control of Expected False Proportions

- **Epistemic type:** `false discovery rate theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `fdr`, `multiple-testing`, `discovery`, `screening`

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

- **Foundation:** [Controlling the False Discovery Rate](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) (1995)
- **Refinement:** [A Direct Approach to False Discovery Rates](https://doi.org/10.1111/1467-9868.00346) (2002)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

An autonomous agent should report the complete candidate universe or a valid approximation. Hidden search makes any multiplicity adjustment unreliable.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b2abe4396b1c92679c73fe1ea47cdde1bf0754749f7dea96a5a400801515d9e2`</sub>

---

## meta:statistics-causality:bootstrap — Empirical Resampling Approximates Sampling Uncertainty Under Stability Conditions

- **Epistemic type:** `bootstrap principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `bootstrap`, `resampling`, `uncertainty`, `stability`

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

- **Foundation:** [Bootstrap Methods: Another Look at the Jackknife](https://doi.org/10.1214/aos/1176344552) (1979)
- **Reference:** [Bootstrap Methods and Their Application](https://doi.org/10.1017/CBO9780511802843) (1997)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should record the resampling unit and scheme. Resampling rows in clustered or temporal data can manufacture false precision.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `330788f76b904a6f3f96582b1e4195bfd766864a3e9c910b2691e56b2633eed4`</sub>

---

## meta:statistics-causality:missing-data-mechanisms — Missingness Is Part of the Data-Generating Process

- **Epistemic type:** `missing-data framework`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `missing-data`, `mcar`, `mar`, `mnar`

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

- **Foundation:** [Inference and Missing Data](https://doi.org/10.1093/biomet/63.3.581) (1976)
- **Refinement:** [Multiple Imputation for Nonresponse in Surveys](https://doi.org/10.1002/9780470316696) (1987)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

‘Missing’ is not a neutral null value. Principia should connect missingness patterns to process events and require sensitivity analysis when MNAR is plausible.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `11dfa2253d59ecae79712585ee772cca6245a8285dcdeab307a1cd150edc2a0c`</sub>

---

## meta:statistics-causality:sutva-consistency — Causal Effects Require Well-Defined Treatments and Potential Outcomes

- **Epistemic type:** `causal consistency principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `sutva`, `consistency`, `treatment-definition`, `interference`

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

- **Foundation:** [Randomization Analysis of Experimental Data: The Fisher Randomization Test](https://doi.org/10.1080/01621459.1980.10477512) (1980)
- **Refinement:** [Interference Between Units in Randomized Experiments](https://doi.org/10.3102/107699860250040425) (2000)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

A Principle claiming an intervention effect should name the intervention. ‘Use AI’ or ‘increase quality’ is not a well-defined treatment without implementation details.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `f8eb673d878f9e0966ee9b16b79d3906b97d82610a630797e42ab4072f1c0675`</sub>

---

## meta:statistics-causality:exchangeability — Causal Comparison Requires Exchangeability or a Design Substitute

- **Epistemic type:** `causal assumption`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `exchangeability`, `confounding`, `adjustment`, `causal-identification`

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

- **Foundation:** [The Central Role of the Propensity Score in Observational Studies for Causal Effects](https://doi.org/10.1093/biomet/70.1.41) (1983)
- **Refinement:** [Causal Knowledge as a Prerequisite for Confounding Evaluation](https://doi.org/10.1093/aje/kwq368) (2011)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should never infer exchangeability from predictive accuracy alone. It should preserve the proposed adjustment set and reasons why relevant common causes are measured.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `9e19eb38f3ed98c00f8d5f4da551145276668849b887c3f900ef0b6a32223608`</sub>

---

## meta:statistics-causality:positivity — Effects Are Learnable Only Where Treatment Alternatives Have Support

- **Epistemic type:** `positivity assumption`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `positivity`, `overlap`, `support`, `extrapolation`

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

- **Foundation:** [Causal Inference: What If](https://www.hsph.harvard.edu/miguel-hernan/causal-inference-book/) (2020)
- **Application:** [Practical Positivity Violations in Longitudinal Marginal Structural Models](https://doi.org/10.1097/EDE.0b013e31815b0f9f) (2008)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

A new Principle should state its empirical support region. Universal treatment claims based on one narrow operating regime violate this root.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0c47e466b8bd640329137c3905fbc9867251d1c9e38e07d61c20651deb3c6127`</sub>

---

## meta:statistics-causality:interference — Units Can Causally Affect One Another

- **Epistemic type:** `causal observation`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `interference`, `spillovers`, `networks`, `causal-effects`

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

- **Foundation:** [Causal Inference with Interference](https://doi.org/10.1198/016214508000000292) (2008)
- **Refinement:** [Estimating Average Causal Effects Under General Interference](https://doi.org/10.1214/17-AOAS1008) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

This Meta-Principle is especially relevant to multi-agent and social systems: treating interactions as independent rows can reverse conclusions about collective interventions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `82ec29a3598e10de0f78bc8894ff94a4798b7f478b2d3307468f8ae4adb68245`</sub>

---

## meta:statistics-causality:simpson-paradox — Aggregation Can Reverse Conditional Associations

- **Epistemic type:** `statistical paradox`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `simpson-paradox`, `aggregation`, `conditioning`, `confounding`

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

- **Foundation:** [The Interpretation of Interaction in Contingency Tables](https://doi.org/10.1111/j.2517-6161.1951.tb00088.x) (1951)
- **Causal interpretation:** [Causal Diagrams for Empirical Research](https://doi.org/10.1093/biomet/82.4.669) (1995)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should preserve subgroup and aggregation definitions. A Meta-Principle linking should ask whether the paper-level relation survives relevant stratification.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `9d977accb0acab8598ee59c732b3f6dc836610d43b77c8d7327ac8a3a5d306de`</sub>

---

## meta:statistics-causality:regression-to-mean — Extreme Observations Tend to Be Followed by Less Extreme Ones Without Intervention

- **Epistemic type:** `statistical phenomenon`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `regression-to-mean`, `selection`, `longitudinal`, `controls`

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

- **Foundation:** [Regression towards Mediocrity in Hereditary Stature](https://doi.org/10.2307/2841583) (1886)
- **Application:** [Regression to the Mean: What It Is and How to Deal with It](https://doi.org/10.1093/ije/27.4.532) (1998)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Before attributing improvement after selecting failures, Principia should compare untreated or historical controls and model measurement noise.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `90c7041287d6a8e7a5829527102acbeea159c27efecc6fb039dc49a9488b2481`</sub>

---

## meta:statistics-causality:calibration — Probabilistic Predictions Must Match Long-Run Frequencies in Their Reference Class

- **Epistemic type:** `calibration principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `calibration`, `probability`, `forecasting`, `confidence`

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

- **Foundation:** [Verification of Forecasts Expressed in Terms of Probability](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2) (1950)
- **Application:** [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

Principia should not interpret a language-model confidence phrase as a calibrated probability. Calibration requires repeated outcomes and a declared reference class.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `41a26015dc2e2904a2a390857c7c5449f56075e67a74cff065789856006d446a`</sub>

---

## meta:statistics-causality:transport-formula — Transport Requires Modeling Population Differences, Not Merely Reweighting Labels

- **Epistemic type:** `transportability theorem family`
- **Principia kind:** `theorem`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `transportability`, `data-fusion`, `population`, `external-validity`

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

- **Foundation:** [External Validity: From Do-Calculus to Transportability Across Populations](https://doi.org/10.1214/14-STS486) (2014)
- **Refinement:** [Data-Fusion Problems with Statistical and Causal Data Sources](https://doi.org/10.1073/pnas.1510507113) (2016)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What sampling, assignment, or causal assumptions make the new Principle identifiable?
- How would violations of this Meta-Principle alter the claimed effect or uncertainty?

### Comment

This entry refines the cross-domain invariance root. Principia should encode which mechanisms are assumed stable and which population distributions are allowed to differ.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `23eba7afb813e8dda342f7ecf9720b4fdbd2bedbbba7d1b69710f64e57bd74c4`</sub>


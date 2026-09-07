# Medicine and Epidemiology: Meta-Principles

This file contains 17 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `medicine-epidemiology`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:medicine-epidemiology:randomization-causal-balance — Random Assignment Creates Comparable Treatment Groups in Expectation

- **Epistemic type:** `causal design principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `randomization`, `causal-inference`, `clinical-trial`, `allocation`

### Argument & interpretation

Random allocation makes treatment assignment independent of pre-treatment potential outcomes under the assignment mechanism. It balances measured and unmeasured baseline causes in expectation, supporting causal estimation when adherence, outcome ascertainment, and analysis are appropriately handled.

### Boundary & conditions

- Finite samples can remain imbalanced by chance.
- Post-randomization selection, nonadherence, interference, missing outcomes, or unblinding can bias estimates.
- Randomization identifies effects in the enrolled population and intervention protocol, not automatic transport to all patients.

### Application

- clinical trials
- public-health interventions
- digital health
- behavioral medicine
- policy experiments

### Basics

Fisher formalized randomization in experimental design. The 1948 MRC streptomycin trial became a landmark randomized therapeutic trial coordinated with Austin Bradford Hill.

### Paper / work evidence

- **Foundation:** [The Design of Experiments](https://archive.org/details/designofexperime00fish) (1935)
- **Clinical landmark:** [Streptomycin Treatment of Pulmonary Tuberculosis](https://doi.org/10.1136/bmj.2.4582.769) (1948)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Randomization is a design property, not a guarantee of good measurement or external validity. Reports should preserve allocation, concealment, adherence, attrition, and analysis details.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `fc2b00e9ce308bd4e4c91a3398c02f3ae4ffa775d5bf3d3887eded566a22b4cd`</sub>

---

## meta:medicine-epidemiology:intention-to-treat — Intention-to-Treat Preserves the Causal Meaning of Random Assignment

- **Epistemic type:** `clinical-trial analysis principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `intention-to-treat`, `estimand`, `adherence`, `randomized-trial`

### Argument & interpretation

Analyzing participants according to their randomized assignment estimates the effect of offering or assigning a treatment strategy and preserves baseline comparability. Per-protocol or as-treated analyses answer different questions and generally require additional assumptions because adherence is post-randomization.

### Boundary & conditions

- Intention-to-treat can be diluted by nonadherence or crossover and may not estimate biological efficacy.
- Missing outcomes can still bias the estimate.
- Noninferiority trials require particular care because nonadherence can bias toward equivalence.

### Application

- clinical-trial analysis
- pragmatic trials
- implementation research
- comparative effectiveness

### Basics

The principle developed with modern randomized trial methodology and was codified in regulatory and CONSORT guidance. The distinction between assignment effects and adherence effects is now formalized using causal estimands.

### Paper / work evidence

- **Foundation:** [Statistical Principles for Clinical Trials: ICH E9](https://database.ich.org/sites/default/files/E9_Guideline.pdf) (1998)
- **Modern refinement:** [Estimands and Sensitivity Analysis in Clinical Trials: ICH E9(R1)](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

A study should state the estimand rather than treat intention-to-treat as a ritual. Assignment, adherence, treatment received, and outcome observation are distinct variables.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0ef32a3b35076647896e2b438cf01a72ca91cd38a8d4aea77290d9b3556b9c23`</sub>

---

## meta:medicine-epidemiology:bradford-hill-viewpoints — Causal Interpretation Requires Converging Evidence, Not a Mechanical Checklist

- **Epistemic type:** `causal-evidence heuristic`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `bradford-hill`, `causation`, `triangulation`, `epidemiology`

### Argument & interpretation

Strength, consistency, temporality, dose–response, plausibility, experiment, analogy, and related considerations can organize causal assessment in observational medicine. No single viewpoint is necessary or sufficient; temporality is indispensable, while strong causal effects can violate several other heuristics.

### Boundary & conditions

- The viewpoints are not a scoring rule or proof of causation.
- Mechanistic plausibility is limited by current knowledge and can bias against novel effects.
- Consistency may fail under genuine effect heterogeneity.

### Application

- epidemiology
- toxicology
- public health
- pharmacovigilance
- occupational medicine

### Basics

Austin Bradford Hill presented the viewpoints in 1965 when discussing environmental and occupational causes of disease.

### Paper / work evidence

- **Foundation:** [The Environment and Disease: Association or Causation?](https://doi.org/10.1177/003591576505800503) (1965)
- **Critical refinement:** [Causal Inference in Epidemiology: The Need for a Pluralistic Approach](https://doi.org/10.1093/ije/dyh134) (2004)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Misuse as a checklist can create false confidence. Principia should encode each evidence strand and contradiction separately and preserve uncertainty about unmeasured confounding.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `86b65d23ada30f1c14f82d50ce6f3fd46e180a0aab992d097730c9d69a3bd714`</sub>

---

## meta:medicine-epidemiology:base-rate-predictive-value — Clinical Test Meaning Depends on Prevalence as Well as Sensitivity and Specificity

- **Epistemic type:** `Bayesian diagnostic theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `base-rate`, `predictive-value`, `diagnosis`, `bayes`

### Argument & interpretation

A positive result changes disease odds by the likelihood ratio, but the resulting positive predictive value also depends on pretest probability. When prevalence is low, even a test with high sensitivity and specificity can yield many false positives; the same test has different meaning in screening and symptomatic populations.

### Boundary & conditions

- Prevalence must match the target setting and time.
- Verification bias, spectrum effects, changing thresholds, and imperfect reference standards alter estimates.
- Repeated or dependent tests require joint modeling rather than naive multiplication.

### Application

- diagnostics
- screening
- biomarkers
- medical AI
- quality control

### Basics

Bayes’s theorem supplies the mathematical basis. Clinical epidemiology developed likelihood ratios and pretest/posttest probability as operational diagnostic tools.

### Paper / work evidence

- **Foundation:** [The Interpretation of Diagnostic Data](https://doi.org/10.1056/NEJM197503062921003) (1975)
- **Clinical operationalization:** [Simple Likelihood Ratios and Multiple Diagnostic Tests](https://doi.org/10.1016/S0140-6736(75)91923-1) (1975)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Medical AI reports that emphasize AUROC without calibrated predictive values at deployment prevalence are incomplete. Principia should link diagnostic claims to target prevalence and decision threshold.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `f27fe78707a6cc167a3cec93824dc1e0c7a1c62f4d76f04224f87ac171e3f617`</sub>

---

## meta:medicine-epidemiology:screening-benefit-harm — Screening Can Improve Outcomes Only If Earlier Detection Changes Net Patient Benefit

- **Epistemic type:** `clinical decision proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `screening`, `overdiagnosis`, `lead-time-bias`, `net-benefit`

### Argument & interpretation

A screening program is beneficial when it detects clinically relevant disease early enough for effective intervention and when mortality or morbidity reductions exceed harms from false positives, overdiagnosis, overtreatment, anxiety, and resource diversion. Earlier diagnosis alone is not evidence of benefit.

### Boundary & conditions

- Lead-time, length, and healthy-volunteer biases can make survival appear better without changing mortality.
- Benefits and harms depend on prevalence, age, risk, test threshold, treatment effectiveness, and follow-up.
- A sensitive test can worsen net benefit if it detects indolent disease.

### Application

- cancer screening
- newborn screening
- population health
- medical imaging
- biomarkers

### Basics

Modern screening evaluation developed from twentieth-century epidemiology. Wilson and Jungner formulated classic criteria in 1968; later work emphasized overdiagnosis and randomized outcome evidence.

### Paper / work evidence

- **Foundation:** [Principles and Practice of Screening for Disease](https://iris.who.int/handle/10665/37650) (1968)
- **Harm refinement:** [Quantifying Overdiagnosis in Cancer Screening](https://doi.org/10.1093/jnci/djp483) (2010)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Principia should distinguish detection yield, stage shift, disease-specific mortality, all-cause outcomes, and patient-centered net benefit.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `d43e938af45bae920e034d5a0ae016e282a73623f6cbdeb4e94f1f8ef1036756`</sub>

---

## meta:medicine-epidemiology:heterogeneous-treatment-effects — Average Treatment Effects Can Conceal Clinically Important Effect Heterogeneity

- **Epistemic type:** `causal-effect proposition`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `treatment-effect-heterogeneity`, `subgroups`, `interaction`, `personalized-medicine`

### Argument & interpretation

A population-average effect does not imply that every patient benefits equally or in the same direction. Treatment effects may vary with baseline risk, biology, co-treatment, adherence, or context. Valid heterogeneity claims require interaction-based reasoning, adequate power, prespecification, shrinkage, or independent validation.

### Boundary & conditions

- Small subgroups and many candidate modifiers produce unstable false discoveries.
- Differences in within-subgroup significance do not prove a between-subgroup interaction.
- Effect heterogeneity depends on the effect scale.

### Application

- personalized medicine
- trial design
- risk stratification
- clinical guidelines
- medical AI

### Basics

Subgroup analysis has long accompanied trials; methodological work from the 1990s–2000s clarified multiplicity, interaction testing, and reporting requirements.

### Paper / work evidence

- **Foundation:** [Reporting of Subgroup Analyses in Clinical Trials](https://doi.org/10.1056/NEJMsr077003) (2007)
- **Methodological guidance:** [Subgroup Analysis in Randomised Controlled Trials](https://doi.org/10.1016/S0140-6736(05)17709-5) (2005)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Personalization is attractive but fragile. Principia should mark post hoc subgroups as hypotheses unless independently replicated or supported by strong prior mechanism.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3ed0d026f0c3e407370e18a35fa1da6ca1ff7dac85c15e718f8e56815ae0cfbf`</sub>

---

## meta:medicine-epidemiology:surrogate-endpoint-risk — A Surrogate Endpoint Is Valid Only When It Reliably Mediates the Treatment Effect on the Clinical Outcome

- **Epistemic type:** `clinical inference proposition`
- **Principia kind:** `hypothesis`
- **Maturity:** `contested`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `surrogate-endpoint`, `biomarker`, `mediation`, `clinical-outcome`

### Argument & interpretation

A biomarker or intermediate outcome can replace a patient-relevant endpoint only when treatment effects on the surrogate predict treatment effects on the clinical outcome across relevant interventions and mechanisms. Correlation with prognosis is insufficient because treatment can affect the surrogate and outcome through different paths.

### Boundary & conditions

- Validity is treatment-class, disease-stage, population, and endpoint specific.
- A surrogate can fail when off-target effects bypass it or when causal mediation changes.
- Statistical criteria are difficult to satisfy and cannot replace biological scrutiny.

### Application

- drug development
- biomarkers
- accelerated approval
- clinical-trial design
- digital endpoints

### Basics

Prentice proposed influential statistical criteria in 1989. Later meta-analytic and causal frameworks showed that surrogate validity is contextual and requires cross-trial evidence.

### Paper / work evidence

- **Foundation:** [Surrogate Endpoints in Clinical Trials: Definition and Operational Criteria](https://doi.org/10.1002/sim.4780080507) (1989)
- **Definition refinement:** [Biomarkers and Surrogate Endpoints: Preferred Definitions and Conceptual Framework](https://doi.org/10.1067/mcp.2001.113989) (2001)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Surrogate endpoints can speed trials but have produced harmful reversals. Principia should represent surrogate status as a scoped hypothesis, not an established substitution rule.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `721e35fcd464fc43a411b3451bbb10d95590905fb96a4bb3131457ba268118d6`</sub>

---

## meta:medicine-epidemiology:external-validity-transport — Trial Efficacy Does Not Automatically Transport to New Patients or Settings

- **Epistemic type:** `transportability proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `external-validity`, `transportability`, `trial-population`, `implementation`

### Argument & interpretation

A causal estimate from a trial applies directly to its study population, treatment implementation, comparator, outcome definition, and follow-up. Transport to routine care requires that effect modifiers, adherence, co-interventions, measurement, and healthcare delivery are sufficiently comparable or explicitly adjusted.

### Boundary & conditions

- Biological mechanisms can be stable even when absolute effects change with baseline risk.
- Eligibility restrictions and volunteer selection can limit representativeness.
- Pragmatic trials improve some aspects of transport but may reduce treatment contrast or measurement control.

### Application

- comparative effectiveness
- guidelines
- global health
- medical AI deployment
- real-world evidence

### Basics

External validity has been discussed since early clinical trials. Rothwell’s 2005 review systematized applicability concerns; causal transportability methods later formalized selection diagrams and reweighting.

### Paper / work evidence

- **Foundation:** [External Validity of Randomised Controlled Trials](https://doi.org/10.1016/S0140-6736(04)17323-7) (2005)
- **Formalization:** [Transportability of Causal and Statistical Relations](https://doi.org/10.1073/pnas.1204599109) (2012)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

“Real-world” is not a guarantee of representativeness. New Principles should specify target population, care pathway, and effect scale.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `d22348fc9caf655a9359358bc671d9c62304fc5fe5e0e23d12ea9eb8b6eadd31`</sub>

---

## meta:medicine-epidemiology:absolute-relative-risk — Clinical Importance Depends on Absolute Risk, Not Relative Effect Alone

- **Epistemic type:** `clinical decision proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `absolute-risk`, `relative-risk`, `nnt`, `clinical-significance`

### Argument & interpretation

A constant relative risk reduction produces very different absolute benefit at different baseline risks. Absolute risk difference, number needed to treat, time horizon, competing events, and harms determine clinical impact and resource value.

### Boundary & conditions

- Number needed to treat varies with baseline risk, follow-up, outcome definition, and effect measure.
- Nonconstant hazards and competing risks can make simple summaries misleading.
- Relative effects may transport more or less stably than absolute effects, depending on mechanism.

### Application

- clinical communication
- guidelines
- health economics
- risk prediction
- shared decision-making

### Basics

The number-needed-to-treat measure was formalized in the late 1980s to translate trial results into clinical terms; evidence-based medicine promoted absolute-effect reporting.

### Paper / work evidence

- **Foundation:** [Number Needed to Treat: A Clinically Useful Measure of Treatment Effect](https://doi.org/10.1056/NEJM198806303182605) (1988)
- **Clinical guidance:** [Users’ Guides to the Medical Literature: How to Use an Article About Therapy or Prevention](https://doi.org/10.1001/jama.1994.03520110075039) (1994)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Relative-risk headlines can exaggerate benefits in low-risk populations. Principia should retain both relative and absolute scales with the baseline-risk source.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c8f7b501444a8c3ec68aa7fa2643631f072fb57226c4f5b730495042e977bc14`</sub>

---

## meta:medicine-epidemiology:reproduction-number-threshold — Epidemic Growth Depends on the Effective Reproduction Number Crossing One

- **Epistemic type:** `epidemic threshold theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `R0`, `epidemic-threshold`, `transmission`, `infectious-disease`

### Argument & interpretation

For a specified transmission model and population state, infections tend to grow when the effective reproduction number $R_t>1$ and decline when $R_t<1$. The basic reproduction number $R_0$ summarizes transmission in a wholly susceptible reference population, but it is not an intrinsic pathogen constant independent of behavior and setting.

### Boundary & conditions

- Threshold interpretation depends on model structure, generation intervals, heterogeneity, stochasticity, and importation.
- Local outbreaks can die out by chance even when $R_t>1$.
- Estimated reproduction numbers are sensitive to delays, under-ascertainment, and changing contact patterns.

### Application

- infectious-disease modeling
- public health
- vaccination
- hospital epidemiology
- network contagion

### Basics

Kermack and McKendrick’s 1927 epidemic model introduced the modern threshold logic; next-generation matrix theory generalized it to structured populations.

### Paper / work evidence

- **Foundation:** [A Contribution to the Mathematical Theory of Epidemics](https://doi.org/10.1098/rspa.1927.0118) (1927)
- **Generalization:** [Reproduction Numbers and Sub-Threshold Endemic Equilibria for Compartmental Models](https://doi.org/10.1016/S0025-5564(01)00095-8) (2002)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

A single $R$ value can conceal superspreading, spatial variation, and subgroup-specific transmission. Principia should store the model and estimation window.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `2212d20025152007c28daca367abaae22c08426fb1d63e281a53f24b7b6b8404`</sub>

---

## meta:medicine-epidemiology:herd-immunity — Population Immunity Reduces Transmission Nonlinearly Through Contact Structure

- **Epistemic type:** `epidemiological mechanism`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `herd-immunity`, `vaccination`, `indirect-effect`, `contact-network`

### Argument & interpretation

Immune individuals can indirectly protect susceptible people by interrupting transmission chains. In homogeneous idealized models with a perfect sterilizing vaccine, the critical immune fraction is approximately $1-1/R_0$; real thresholds depend on heterogeneity, waning, variant evolution, assortative mixing, and vaccine effects on infection and transmission.

### Boundary & conditions

- The simple formula assumes homogeneous mixing and durable complete immunity.
- Clustering of susceptible people can sustain outbreaks above an average threshold.
- Herd immunity is not an ethical justification for uncontrolled infection.

### Application

- vaccination policy
- infectious-disease control
- public-health planning
- network epidemiology

### Basics

The concept emerged in veterinary and human epidemiology in the early twentieth century. Modern treatments relate it to reproduction numbers and structured transmission.

### Paper / work evidence

- **Foundation:** [Herd Immunity: A Rough Guide](https://doi.org/10.1093/cid/cir007) (2011)
- **Quantitative formulation:** [A Quantitative Approach to the Herd-Immunity Effect](https://doi.org/10.1016/0140-6736(85)92748-6) (1985)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Thresholds are often communicated as precise universal numbers. They should instead be represented as model-dependent ranges with uncertainty and equity considerations.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `69f6fcae5e30ccfaa4f4ed2f16e4ae6c1b416a95fd3cc51247d474451863049b`</sub>

---

## meta:medicine-epidemiology:prevention-paradox — A Small Benefit to Many Can Prevent More Disease Than a Large Benefit to a Few

- **Epistemic type:** `population-health observation`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `prevention-paradox`, `population-strategy`, `risk-distribution`, `public-health`

### Argument & interpretation

When risk is continuously distributed, most cases may arise from the large population at ordinary or moderately elevated risk rather than the small high-risk tail. Population-wide shifts can therefore produce more aggregate prevention even though each individual benefits only slightly.

### Boundary & conditions

- Population strategies can expose many people to small costs or harms.
- High-risk strategies may be preferable when interventions are expensive, invasive, or targeted mechanisms dominate.
- The result depends on the risk distribution and intervention effect.

### Application

- public health
- screening policy
- environmental health
- workplace safety
- risk communication

### Basics

Geoffrey Rose articulated the prevention paradox and contrasted population and high-risk strategies in the 1980s.

### Paper / work evidence

- **Foundation:** [Sick Individuals and Sick Populations](https://doi.org/10.1093/ije/14.1.32) (1985)
- **Book synthesis:** [The Strategy of Preventive Medicine](https://global.oup.com/academic/product/the-strategy-of-preventive-medicine-9780192630971) (1992)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Aggregate benefit can conceal unequal burdens. Principia should report distributional effects and not use population averages to erase individual consent or subgroup harm.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `7c5bd260c537d4cdfa73181bd99643a84b0855a1a29d1dc830009a1403a16132`</sub>

---

## meta:medicine-epidemiology:competing-risks — Competing Events Change the Probability and Interpretation of Clinical Outcomes

- **Epistemic type:** `survival-analysis proposition`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `competing-risks`, `survival-analysis`, `cumulative-incidence`, `estimand`

### Argument & interpretation

When one event prevents or alters observation of another, treating the competing event as ordinary independent censoring generally misstates cumulative incidence. Cause-specific hazards and subdistribution functions answer different questions and should be chosen according to the scientific estimand.

### Boundary & conditions

- Methods require clear event definitions and follow-up.
- Hazard ratios are conditional instantaneous contrasts and do not directly equal risk differences.
- Interventions can affect competing causes, changing interpretation of endpoint-specific benefit.

### Application

- oncology
- cardiology
- geriatrics
- reliability medicine
- longitudinal studies

### Basics

Competing-risk theory developed within survival analysis; Fine and Gray’s 1999 subdistribution model became widely used for cumulative-incidence regression.

### Paper / work evidence

- **Foundation:** [A Proportional Hazards Model for the Subdistribution of a Competing Risk](https://doi.org/10.1080/01621459.1999.10474144) (1999)
- **Tutorial refinement:** [Competing Risks and Multistate Models](https://doi.org/10.1002/sim.2712) (2007)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Choosing an estimator for convenience can answer the wrong clinical question. Principia should store the estimand, competing events, and whether censoring assumptions are credible.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `962283333d02a63405e2ddd12601b8b2bf7d040135edf9eaeb3e52c2d0265f84`</sub>

---

## meta:medicine-epidemiology:decision-threshold-net-benefit — Prediction Is Clinically Useful Only When It Improves Decisions at Relevant Thresholds

- **Epistemic type:** `clinical decision principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `decision-threshold`, `net-benefit`, `clinical-prediction`, `utility`

### Argument & interpretation

A risk model has value when using it changes actions and yields greater expected benefit than reasonable alternatives at a specified threshold trade-off between false positives and false negatives. Discrimination and calibration are necessary but not sufficient for clinical utility.

### Boundary & conditions

- Thresholds encode values, costs, harms, and capacity constraints and may differ across patients and systems.
- Decision-curve assumptions can be violated if interventions have heterogeneous or delayed effects.
- A model can have high AUROC yet no net benefit over treat-all or treat-none strategies.

### Application

- clinical prediction
- medical AI
- triage
- screening
- shared decisions

### Basics

Decision analysis has long linked probability to action. Decision-curve analysis, introduced by Vickers and Elkin in 2006, provided a practical net-benefit framework for prediction models.

### Paper / work evidence

- **Foundation:** [Decision Curve Analysis: A Novel Method for Evaluating Prediction Models](https://doi.org/10.1177/0272989X06295361) (2006)
- **Book synthesis:** [Clinical Prediction Models](https://doi.org/10.1007/978-0-387-77244-8) (2009)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Model deployment should be evaluated as an intervention, including workflow, automation bias, equity, and downstream treatment effects.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `e3f37a50cc3680a79db4e06358b2baa1e13cdddd415370da061c2f90b2d6e1f7`</sub>

---

## meta:medicine-epidemiology:measurement-and-case-definition — Disease Frequency and Effect Estimates Depend on Case Definitions and Measurement Processes

- **Epistemic type:** `measurement proposition`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `case-definition`, `measurement`, `phenotyping`, `surveillance`

### Argument & interpretation

Clinical outcomes are produced by biological states filtered through diagnostic criteria, instruments, coding, healthcare access, and surveillance intensity. Changing a case definition or ascertainment process can create apparent incidence, prevalence, severity, or treatment-effect changes without equivalent biological change.

### Boundary & conditions

- Some diseases have highly specific objective markers; others are syndromic or spectrum-based.
- Differential measurement by treatment, site, or subgroup can create bias.
- Harmonization can improve comparability but may discard clinically relevant local detail.

### Application

- surveillance
- phenotyping
- electronic health records
- medical AI
- multisite studies

### Basics

Epidemiology has long distinguished disease occurrence from observed cases. Modern electronic phenotyping and reporting-standard work formalized reproducible operational definitions.

### Paper / work evidence

- **Foundation:** [Modern Epidemiology](https://www.wolterskluwer.com/en/solutions/ovid/modern-epidemiology-4001) (2008)
- **Digital extension:** [Electronic Health Record Phenotypes and the Meaning of Meaningful Use](https://doi.org/10.1197/jamia.M2920) (2009)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Principia should store the case definition and its version as part of a Principle’s scope. Label quality is not merely a preprocessing detail.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `a33af8f04ec91a727071578099f8d5dd420c22e6dc4daf792d598cf7834927ac`</sub>

---

## meta:medicine-epidemiology:benefit-harm-balance — Clinical Recommendations Require Joint Evaluation of Benefits, Harms, Burdens, and Uncertainty

- **Epistemic type:** `normative decision principle`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `benefit-harm`, `clinical-decision`, `guideline`, `uncertainty`

### Argument & interpretation

An intervention should not be judged by efficacy on one endpoint alone. Decisions combine absolute benefits, adverse effects, treatment burden, opportunity cost, uncertainty, patient preferences, and distribution across populations. The preferred action can change with baseline risk and values even when the causal effect is stable.

### Boundary & conditions

- Benefits and harms may occur on different timescales and be difficult to combine.
- Preferences are heterogeneous and can change with information and experience.
- Population policy and individual decision making may use different objectives.

### Application

- clinical guidelines
- regulatory decisions
- shared decision-making
- health technology assessment
- public health

### Basics

Evidence-based medicine, decision analysis, and guideline frameworks such as GRADE integrated effect certainty with benefit–harm judgments.

### Paper / work evidence

- **Foundation:** [GRADE: An Emerging Consensus on Rating Quality of Evidence and Strength of Recommendations](https://doi.org/10.1136/bmj.39489.470347.AD) (2008)
- **Synthesis:** [Users’ Guides to the Medical Literature: A Manual for Evidence-Based Clinical Practice](https://jamaevidence.mhmedical.com/book.aspx?bookid=847) (2015)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

“Do no harm” is not a zero-risk rule because inaction also carries risk. Principia should preserve the comparator and value assumptions behind a recommendation.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b211f9fd64e30f8ac9d47203bb47f9602ed135991c17d22f32a9ecc0eeee7c23`</sub>

---

## meta:medicine-epidemiology:triangulation-evidence — Concordance Across Differently Biased Designs Strengthens Medical Causal Inference

- **Epistemic type:** `methodological proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `triangulation`, `evidence-synthesis`, `causal-inference`, `bias`

### Argument & interpretation

Randomized trials, natural experiments, prospective cohorts, negative controls, genetic instruments, mechanistic studies, and surveillance data have different failure modes. A conclusion is more credible when independent designs with nonoverlapping biases converge on compatible estimates and boundaries.

### Boundary & conditions

- Apparent independence can fail when studies share data, assumptions, measurement, or publication bias.
- Discordance may reflect genuine heterogeneity rather than error.
- Triangulation does not mechanically average incompatible estimands.

### Application

- pharmacoepidemiology
- environmental health
- nutrition
- rare diseases
- evidence synthesis

### Basics

Epidemiologists have long combined evidence types; modern “triangulation” frameworks explicitly emphasize orthogonal bias structures rather than hierarchy alone.

### Paper / work evidence

- **Foundation:** [Triangulation in Aetiological Epidemiology](https://doi.org/10.1093/ije/dyw314) (2016)
- **Framework:** [Integrating Evidence to Improve Causal Inference](https://doi.org/10.1146/annurev-publhealth-031914-122841) (2015)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

The highest formal design is not always available or transportable. Principia relations should record whether evidence adds independent leverage or merely repeats the same assumptions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `71d7abd6de8cd9c0a10932a07707a5574950d53c584667a4579258e18334b20e`</sub>


# Medicine and Epidemiology Meta-Principles

> **Area ID:** `medicine-epidemiology`  
> **Records:** 25  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:medicine-epidemiology:prevention-paradox` — A Small Benefit to Many Can Prevent More Disease Than a Large Benefit to a Few

**Epistemic type:** population-health observation  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `prevention-paradox`, `population-strategy`, `risk-distribution`, `public-health`

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

- **Foundation (1985):** [Sick Individuals and Sick Populations](https://doi.org/10.1093/ije/14.1.32) · `wrk:e29defe1247427cf0e89`
- **Book Synthesis (1992):** [The Strategy of Preventive Medicine](https://global.oup.com/academic/product/the-strategy-of-preventive-medicine-9780192630971) · `wrk:5e70197808149793b8d7`

### Comment

Aggregate benefit can conceal unequal burdens. Principia should report distributional effects and not use population averages to erase individual consent or subgroup harm.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `db918982d6cb93e37a315cf3b47c501851d70328342dd50a7d251a20f184bbbf`

---

## `meta:medicine-epidemiology:surrogate-endpoint-risk` — A Surrogate Endpoint Is Valid Only When It Reliably Mediates the Treatment Effect on the Clinical Outcome

**Epistemic type:** clinical inference proposition  
**Principia kind:** `hypothesis`  
**Maturity:** `contested` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `surrogate-endpoint`, `biomarker`, `mediation`, `clinical-outcome`

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

- **Foundation (1989):** [Surrogate Endpoints in Clinical Trials: Definition and Operational Criteria](https://doi.org/10.1002/sim.4780080507) · `wrk:99472f98240c91fc4b2f`
- **Definition Refinement (2001):** [Biomarkers and Surrogate Endpoints: Preferred Definitions and Conceptual Framework](https://doi.org/10.1067/mcp.2001.113989) · `wrk:4c1e5715716ce0448463`

### Comment

Surrogate endpoints can speed trials but have produced harmful reversals. Principia should represent surrogate status as a scoped hypothesis, not an established substitution rule.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `7a1084ffcb0fea65856e003aa8b83aa6e7ddf15b0a9cdac8b1109207b0035830`

---

## `meta:medicine-epidemiology:autophagy` — Autophagy Recycles Intracellular Material and Maintains Cellular Quality Under Stress

**Epistemic type:** cellular recycling mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2016_landmark`  
**Introduced / developed:** 1993–present  
**Tags:** `autophagy`, `lysosome`, `quality-control`, `nobel-2016`

### Argument & interpretation

Autophagy sequesters cytoplasmic components into membrane-bound structures that fuse with lysosomes for degradation and recycling. The pathway supports nutrient adaptation, organelle quality control, development, immunity, and stress survival.

### Boundary & conditions

- Autophagy can be protective or harmful depending on timing and disease state.
- Flux must be distinguished from static marker accumulation.
- Different forms of selective and bulk autophagy use distinct machinery.

### Application

- neurodegeneration
- cancer
- infection
- metabolism
- aging

### Basics

Yoshinori Ohsumi used yeast genetics in the early 1990s to identify autophagy genes and mechanisms; he received the 2016 medicine prize.

### Paper / work evidence

- **Foundation (1993):** [Isolation and characterization of autophagy-defective mutants of Saccharomyces cerevisiae](https://doi.org/10.1016/0014-5793(93)80398-E) · `wrk:a01ad7bf72d72412a60e`
- **Recognition (2016):** [The Nobel Prize in Physiology or Medicine 2016](https://www.nobelprize.org/prizes/medicine/2016/summary/) · `wrk:ec8dd0ed0eba41e0d5a8`

### Foundation relations

- `specializes` → `meta:biology-evolution:homeostasis` — Autophagy maintains cellular material and energy balance.
- `analogous_to` → `meta:engineering-optimization:safety-factor-reliability` — Selective removal and replacement sustain system reliability.

### Comment

A child Principle should measure pathway flux and causal intervention; marker changes alone can be misread as increased or decreased autophagy.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `2a6a5ff5fc2a0c06ac9bff826c95d4bdfd7c3f21263634dbb85c6a7acf437a28`

---

## `meta:medicine-epidemiology:heterogeneous-treatment-effects` — Average Treatment Effects Can Conceal Clinically Important Effect Heterogeneity

**Epistemic type:** causal-effect proposition  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `treatment-effect-heterogeneity`, `subgroups`, `interaction`, `personalized-medicine`

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

- **Foundation (2007):** [Reporting of Subgroup Analyses in Clinical Trials](https://doi.org/10.1056/NEJMsr077003) · `wrk:380b15278c0bdc0e255d`
- **Methodological Guidance (2005):** [Subgroup Analysis in Randomised Controlled Trials](https://doi.org/10.1016/S0140-6736(05)17709-5) · `wrk:b5ae324533f1eab9204e`

### Comment

Personalization is attractive but fragile. Principia should mark post hoc subgroups as hypotheses unless independently replicated or supported by strong prior mechanism.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `bf4e487fa64d4a34a59fa65f6a6265064549fa302e80f4712232449abdcb50c7`

---

## `meta:medicine-epidemiology:immune-checkpoint-blockade` — Blocking Inhibitory Immune Checkpoints Can Restore Antitumor T-Cell Activity

**Epistemic type:** cancer-immunotherapy mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2018_landmark`  
**Introduced / developed:** 1992–present  
**Tags:** `checkpoint-blockade`, `ctla-4`, `pd-1`, `nobel-2018`

### Argument & interpretation

Tumors can exploit inhibitory pathways such as CTLA-4 and PD-1/PD-L1 that normally restrain T-cell activation. Antibody blockade can release this brake, enabling durable antitumor responses in a subset of patients and demonstrating that host immunity can be therapeutically reactivated.

### Boundary & conditions

- Response depends on tumor antigens, immune infiltration, checkpoint dependence, microbiome, and host condition.
- Immune-related adverse events arise because tolerance is deliberately weakened.
- Many tumors remain resistant or develop escape mechanisms.

### Application

- oncology
- biomarker development
- combination therapy
- immune monitoring
- translational immunology

### Basics

James Allison demonstrated CTLA-4 blockade in preclinical cancer models; Tasuku Honjo discovered PD-1. They received the 2018 medicine prize.

### Paper / work evidence

- **Foundation (1996):** [Enhancement of Antitumor Immunity by CTLA-4 Blockade](https://doi.org/10.1126/science.271.5256.1734) · `wrk:e0e970db0f02301fb4cf`
- **Discovery (1992):** [Induced expression of PD-1, a novel member of the immunoglobulin gene superfamily, upon programmed cell death](https://pubmed.ncbi.nlm.nih.gov/1396582/) · `wrk:bc0d8353e8dd8357c808`
- **Recognition (2018):** [The Nobel Prize in Physiology or Medicine 2018](https://www.nobelprize.org/prizes/medicine/2018/summary/) · `wrk:7512d48ec7e478872290`

### Foundation relations

- `contradicts` → `meta:medicine-epidemiology:peripheral-immune-tolerance-treg-foxp3` — Checkpoint therapy deliberately relaxes tolerance controls.
- `depends_on` → `meta:biology-evolution:red-queen` — Tumors can evolve immune-evasion strategies under therapy.

### Comment

The framework is a powerful causal mechanism, but “more immune activation” is not universally beneficial; toxicity and compensatory escape are central boundaries.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `c2912f9680974cfe76448ef462b1640eb46b772089ca0b3519fa959ae2976c95`

---

## `meta:medicine-epidemiology:hallmarks-of-cancer` — Cancer Emerges Through Recurrent Functional Capabilities Rather Than One Universal Mutation

**Epistemic type:** integrative disease framework  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `highly_influential_consensus_framework`  
**Introduced / developed:** 2000–present  
**Tags:** `cancer`, `hallmarks`, `systems-oncology`, `consensus`

### Argument & interpretation

Diverse tumors repeatedly acquire capabilities such as sustained proliferation, resistance to cell death, angiogenesis, invasion, immune evasion, and metabolic reprogramming. These hallmarks organize heterogeneous molecular alterations into functional mechanisms and enabling conditions.

### Boundary & conditions

- The framework is a taxonomy and heuristic, not a complete causal law.
- Hallmarks differ by tumor type, stage, microenvironment, and treatment history.
- Categories overlap and continue to evolve as evidence changes.

### Application

- oncology
- drug development
- combination therapy
- biomarkers
- cancer systems biology

### Basics

Douglas Hanahan and Robert Weinberg proposed six hallmarks in 2000, expanded them in 2011, and updated the framework in 2022.

### Paper / work evidence

- **Foundation (2000):** [The Hallmarks of Cancer](https://doi.org/10.1016/S0092-8674(00)81683-9) · `wrk:72ba03cdba62ffe53662`
- **Extension (2011):** [Hallmarks of Cancer: The Next Generation](https://doi.org/10.1016/j.cell.2011.02.013) · `wrk:113010d334d82afdf8d4`
- **Update (2022):** [Hallmarks of Cancer: New Dimensions](https://doi.org/10.1158/2159-8290.CD-21-1059) · `wrk:c107d273aa0a2e0801f0`

### Foundation relations

- `depends_on` → `meta:biology-evolution:red-queen` — Tumor populations evolve capabilities under selection.
- `depends_on` → `meta:biology-evolution:niche-construction` — The microenvironment shapes which cancer capabilities are advantageous.

### Comment

Because the framework is influential, Principia should prevent children from treating a hallmark label as mechanistic proof or therapeutic validation.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `dd59ff3333fa5290140ec14c31ceddce870a55bf55941cbd707a9dee13043e26`

---

## `meta:medicine-epidemiology:bradford-hill-viewpoints` — Causal Interpretation Requires Converging Evidence, Not a Mechanical Checklist

**Epistemic type:** causal-evidence heuristic  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `bradford-hill`, `causation`, `triangulation`, `epidemiology`

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

- **Foundation (1965):** [The Environment and Disease: Association or Causation?](https://doi.org/10.1177/003591576505800503) · `wrk:800dcc87f69ece3cadf3`
- **Critical Refinement (2004):** [Causal Inference in Epidemiology: The Need for a Pluralistic Approach](https://doi.org/10.1093/ije/dyh134) · `wrk:841bf6c83ff458563db0`

### Comment

Misuse as a checklist can create false confidence. Principia should encode each evidence strand and contradiction separately and preserve uncertainty about unmeasured confounding.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `9286f313f99d50160136b868884bbe3f22427ebfd31c2d79421c77bc983d8184`

---

## `meta:medicine-epidemiology:absolute-relative-risk` — Clinical Importance Depends on Absolute Risk, Not Relative Effect Alone

**Epistemic type:** clinical decision proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `absolute-risk`, `relative-risk`, `nnt`, `clinical-significance`

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

- **Foundation (1988):** [Number Needed to Treat: A Clinically Useful Measure of Treatment Effect](https://doi.org/10.1056/NEJM198806303182605) · `wrk:1353eb6f1e6d4399f6f0`
- **Clinical Guidance (1994):** [Users’ Guides to the Medical Literature: How to Use an Article About Therapy or Prevention](https://doi.org/10.1001/jama.1994.03520110075039) · `wrk:a23803a9080c4d75fb51`

### Comment

Relative-risk headlines can exaggerate benefits in low-risk populations. Principia should retain both relative and absolute scales with the baseline-risk source.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `afc13cbfb0e89a5d1f095adf48660607cc711038286197078b4fb0b45afeeec4`

---

## `meta:medicine-epidemiology:benefit-harm-balance` — Clinical Recommendations Require Joint Evaluation of Benefits, Harms, Burdens, and Uncertainty

**Epistemic type:** normative decision principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `benefit-harm`, `clinical-decision`, `guideline`, `uncertainty`

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

- **Foundation (2008):** [GRADE: An Emerging Consensus on Rating Quality of Evidence and Strength of Recommendations](https://doi.org/10.1136/bmj.39489.470347.AD) · `wrk:60810a354bb98b2bf8f9`
- **Synthesis (2015):** [Users’ Guides to the Medical Literature: A Manual for Evidence-Based Clinical Practice](https://jamaevidence.mhmedical.com/book.aspx?bookid=847) · `wrk:137eaaf93b77b667c634`

### Comment

“Do no harm” is not a zero-risk rule because inaction also carries risk. Principia should preserve the comparator and value assumptions behind a recommendation.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `dd880cd0171eabda40f9eb29d9aec3b8a7983c1766b096aea2e85622ff96df71`

---

## `meta:medicine-epidemiology:base-rate-predictive-value` — Clinical Test Meaning Depends on Prevalence as Well as Sensitivity and Specificity

**Epistemic type:** Bayesian diagnostic theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `base-rate`, `predictive-value`, `diagnosis`, `bayes`

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

- **Foundation (1975):** [The Interpretation of Diagnostic Data](https://doi.org/10.1056/NEJM197503062921003) · `wrk:8a7e23dff4e2a989aad6`
- **Clinical Operationalization (1975):** [Simple Likelihood Ratios and Multiple Diagnostic Tests](https://doi.org/10.1016/S0140-6736(75)91923-1) · `wrk:24143fd3e8074d4d9bb5`

### Comment

Medical AI reports that emphasize AUROC without calibrated predictive values at deployment prevalence are incomplete. Principia should link diagnostic claims to target prevalence and decision threshold.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `a78f439dc2484062e03e415f9e82535f47fdf7117196af1840887d7a639b9254`

---

## `meta:medicine-epidemiology:competing-risks` — Competing Events Change the Probability and Interpretation of Clinical Outcomes

**Epistemic type:** survival-analysis proposition  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `competing-risks`, `survival-analysis`, `cumulative-incidence`, `estimand`

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

- **Foundation (1999):** [A Proportional Hazards Model for the Subdistribution of a Competing Risk](https://doi.org/10.1080/01621459.1999.10474144) · `wrk:367f9395ae010949ed28`
- **Tutorial Refinement (2007):** [Competing Risks and Multistate Models](https://doi.org/10.1002/sim.2712) · `wrk:9159dbb0abfd9a69df85`

### Comment

Choosing an estimator for convenience can answer the wrong clinical question. Principia should store the estimand, competing events, and whether censoring assumptions are credible.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `2927c8132d9d65be7f25fedf539decdbdd51b91de695479ca83d01df37f068e7`

---

## `meta:medicine-epidemiology:triangulation-evidence` — Concordance Across Differently Biased Designs Strengthens Medical Causal Inference

**Epistemic type:** methodological proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `triangulation`, `evidence-synthesis`, `causal-inference`, `bias`

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

- **Foundation (2016):** [Triangulation in Aetiological Epidemiology](https://doi.org/10.1093/ije/dyw314) · `wrk:0b791a1f5dadc2d7a8ba`
- **Framework (2015):** [Integrating Evidence to Improve Causal Inference](https://doi.org/10.1146/annurev-publhealth-031914-122841) · `wrk:8f2145916293973c8945`

### Comment

The highest formal design is not always available or transportable. Principia relations should record whether evidence adds independent leverage or merely repeats the same assumptions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `5bafe104e418019f7b44fdee369d5455b05683f9b61b4b77c4acbe87e126114a`

---

## `meta:medicine-epidemiology:induced-pluripotency` — Differentiated Cell Identity Can Be Reprogrammed by a Small Set of Transcription Factors

**Epistemic type:** cellular reprogramming principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2012_landmark`  
**Introduced / developed:** 2006–present  
**Tags:** `ipsc`, `reprogramming`, `pluripotency`, `nobel-2012`

### Argument & interpretation

Forced expression of selected transcription factors can reset differentiated somatic cells toward a pluripotent state, showing that mature cell identity is actively maintained and can be reconfigured without changing the genome sequence.

### Boundary & conditions

- Reprogramming is inefficient and can introduce genetic, epigenetic, or tumorigenic risk.
- Pluripotent state quality and differentiation competence vary by protocol.
- Partial reprogramming and direct conversion have different safety and identity boundaries.

### Application

- regenerative medicine
- disease modeling
- drug screening
- cell therapy
- aging research

### Basics

Shinya Yamanaka and Kazutoshi Takahashi generated induced pluripotent stem cells in 2006. Yamanaka shared the 2012 medicine prize with John Gurdon for cellular reprogramming.

### Paper / work evidence

- **Foundation (2006):** [Induction of Pluripotent Stem Cells from Mouse Embryonic and Adult Fibroblast Cultures by Defined Factors](https://doi.org/10.1016/j.cell.2006.07.024) · `wrk:ef67e19de74c78a51e34`
- **Recognition (2012):** [The Nobel Prize in Physiology or Medicine 2012](https://www.nobelprize.org/prizes/medicine/2012/summary/) · `wrk:e58d7e2b25d82d7193ce`

### Foundation relations

- `specializes` → `meta:biology-evolution:central-dogma` — Transcription-factor perturbation can move a cell between stable regulatory states.
- `analogous_to` → `meta:neuroscience-cognition:attractor-dynamics` — Cell identities can be viewed as attractor-like states in regulatory dynamics.

### Comment

The fundamental insight is reversibility of regulatory state, not guaranteed therapeutic safety or complete erasure of cellular history.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `a2d1251170fdcffe23a51ee0804f4f977bc7dff0519af9d4df13bf50554a07fc`

---

## `meta:medicine-epidemiology:measurement-and-case-definition` — Disease Frequency and Effect Estimates Depend on Case Definitions and Measurement Processes

**Epistemic type:** measurement proposition  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `case-definition`, `measurement`, `phenotyping`, `surveillance`

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

- **Foundation (2008):** [Modern Epidemiology](https://www.wolterskluwer.com/en/solutions/ovid/modern-epidemiology-4001) · `wrk:66e7bd3ced5cf582d01f`
- **Digital Extension (2009):** [Electronic Health Record Phenotypes and the Meaning of Meaningful Use](https://doi.org/10.1197/jamia.M2920) · `wrk:4a259ebe8b7d91e5ff11`

### Comment

Principia should store the case definition and its version as part of a Principle’s scope. Label quality is not merely a preprocessing detail.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `4ac17a793a9afd8230dc3e6e3b550cdf18c2c841ac9539eba05b287406755551`

---

## `meta:medicine-epidemiology:reproduction-number-threshold` — Epidemic Growth Depends on the Effective Reproduction Number Crossing One

**Epistemic type:** epidemic threshold theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `R0`, `epidemic-threshold`, `transmission`, `infectious-disease`

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

- **Foundation (1927):** [A Contribution to the Mathematical Theory of Epidemics](https://doi.org/10.1098/rspa.1927.0118) · `wrk:0b5651521a4bc40f8f34`
- **Generalization (2002):** [Reproduction Numbers and Sub-Threshold Endemic Equilibria for Compartmental Models](https://doi.org/10.1016/S0025-5564(01)00095-8) · `wrk:e41b30ea12e137424b0a`

### Comment

A single $R$ value can conceal superspreading, spatial variation, and subgroup-specific transmission. Principia should store the model and estimation window.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `e076ff057f3a07f3bbdceaf264c44de3dcc9b66e1f17c5b18db739826b9f6980`

---

## `meta:medicine-epidemiology:peripheral-immune-tolerance-treg-foxp3` — FOXP3-Dependent Regulatory T Cells Enforce Peripheral Immune Tolerance

**Epistemic type:** immune-tolerance mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2025_landmark`  
**Introduced / developed:** 1995–present  
**Tags:** `regulatory-t-cells`, `foxp3`, `tolerance`, `nobel-2025`

### Argument & interpretation

A specialized population of regulatory T cells suppresses inappropriate immune activation outside central lymphoid selection. FOXP3 is a central transcriptional regulator of this lineage, and disruption can produce severe autoimmunity, showing that active peripheral control is required in addition to deletion of self-reactive clones.

### Boundary & conditions

- Regulatory T-cell identity and function are context- and tissue-dependent.
- FOXP3 expression alone may not establish stable suppressive function in every setting.
- Excess suppression can protect tumors or chronic infections.

### Application

- autoimmune disease
- transplantation
- cancer immunology
- allergy
- cell therapy

### Basics

Shimon Sakaguchi identified suppressive CD4+CD25+ cells in 1995; Mary Brunkow, Fred Ramsdell, and others linked FOXP3 to immune dysregulation. Brunkow, Ramsdell, and Sakaguchi received the 2025 medicine prize.

### Paper / work evidence

- **Foundation (1995):** [Immunologic self-tolerance maintained by activated T cells expressing IL-2 receptor alpha-chains](https://pubmed.ncbi.nlm.nih.gov/7636184/) · `wrk:f72672f83477f698cbb5`
- **Mechanism (2001):** [Disruption of a new forkhead/winged-helix protein, scurfin, results in the fatal lymphoproliferative disorder of the scurfy mouse](https://doi.org/10.1038/83784) · `wrk:98d202a9ef66ad259feb`
- **Recognition (2025):** [The Nobel Prize in Physiology or Medicine 2025](https://www.nobelprize.org/prizes/medicine/2025/summary/) · `wrk:1b1cf60b5a607592e3af`

### Foundation relations

- `specializes` → `meta:biology-evolution:homeostasis` — Regulatory T cells stabilize immune activity around a viable operating range.
- `contradicts` → `meta:medicine-epidemiology:immune-checkpoint-blockade` — Cancer therapy may deliberately release inhibitory immune control.

### Comment

Tolerance is a controlled balance rather than global immune suppression; child Principles must specify target tissue, antigen, and disease context.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `46f717bdfc326e347c2f36a83cc3988f09e351903f867d824bd66c163b0bfdc6`

---

## `meta:medicine-epidemiology:oxygen-sensing-hif` — HIF Signaling Couples Cellular Gene Expression to Oxygen Availability

**Epistemic type:** oxygen-sensing mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2019_landmark`  
**Introduced / developed:** 1992–present  
**Tags:** `hif`, `oxygen-sensing`, `hypoxia`, `nobel-2019`

### Argument & interpretation

Hypoxia-inducible factors coordinate transcriptional responses to low oxygen. Oxygen-dependent hydroxylation controls HIF degradation through the VHL pathway, allowing cells to adjust erythropoiesis, angiogenesis, metabolism, and survival according to oxygen availability.

### Boundary & conditions

- Responses differ across cell type, duration, and severity of hypoxia.
- Chronic HIF activation can support tumors and pathological vascularization.
- Oxygen sensing interacts with metabolites, inflammation, and mitochondrial state.

### Application

- anemia
- cancer
- ischemia
- high-altitude physiology
- metabolic disease

### Basics

Gregg Semenza identified HIF-mediated regulation; Peter Ratcliffe and William Kaelin connected oxygen-dependent degradation and VHL. They received the 2019 medicine prize.

### Paper / work evidence

- **Foundation (1992):** [Hypoxia-inducible nuclear factors bind to an enhancer element located 3′ to the human erythropoietin gene](https://doi.org/10.1073/pnas.89.13.5680) · `wrk:ee76df2e2ca83eb3500e`
- **Recognition (2019):** [The Nobel Prize in Physiology or Medicine 2019](https://www.nobelprize.org/prizes/medicine/2019/summary/) · `wrk:98fc8780e8a4e6380ba1`

### Foundation relations

- `specializes` → `meta:biology-evolution:homeostasis` — HIF is a molecular feedback system for oxygen homeostasis.

### Comment

The Principle should ground claims about oxygen adaptation while preserving the distinction between acute compensation and chronic disease-promoting signaling.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `fd01f0cb53a9aa293d355985cf6203375687f5a5c31b9f2f907541e86191e421`

---

## `meta:medicine-epidemiology:intention-to-treat` — Intention-to-Treat Preserves the Causal Meaning of Random Assignment

**Epistemic type:** clinical-trial analysis principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `intention-to-treat`, `estimand`, `adherence`, `randomized-trial`

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

- **Foundation (1998):** [Statistical Principles for Clinical Trials: ICH E9](https://database.ich.org/sites/default/files/E9_Guideline.pdf) · `wrk:be8ca376dee5e6584e4d`
- **Modern Refinement (2019):** [Estimands and Sensitivity Analysis in Clinical Trials: ICH E9(R1)](https://database.ich.org/sites/default/files/E9-R1_Step4_Guideline_2019_1203.pdf) · `wrk:df2c73a9b34a8df26380`

### Comment

A study should state the estimand rather than treat intention-to-treat as a ritual. Assignment, adherence, treatment received, and outcome observation are distinct variables.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `a496f71e60d3ec99b1654f30c55220de32269b6fa5db7dd09a841f6e783b8632`

---

## `meta:medicine-epidemiology:modified-mrna-innate-immunity` — Nucleoside Modification Can Suppress Innate Sensing and Enable Therapeutic mRNA

**Epistemic type:** molecular intervention principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2023_landmark`  
**Introduced / developed:** 2005–present  
**Tags:** `mrna`, `nucleoside-modification`, `vaccines`, `nobel-2023`

### Argument & interpretation

Substituting selected modified nucleosides into in-vitro-transcribed mRNA can reduce recognition by innate immune receptors while improving translation and tolerability. Delivery systems then make transient intracellular protein expression a programmable therapeutic modality.

### Boundary & conditions

- Effects depend on sequence, purity, formulation, dose, route, and cell type.
- Innate activation is not always undesirable and may contribute to vaccination.
- Durability, biodistribution, and rare adverse events remain product-specific.

### Application

- vaccines
- protein replacement
- cancer immunotherapy
- gene editing delivery
- rapid therapeutic design

### Basics

Katalin Karikó, Drew Weissman, and colleagues demonstrated the immune effects of nucleoside modification in 2005; Karikó and Weissman received the 2023 medicine prize.

### Paper / work evidence

- **Foundation (2005):** [Suppression of RNA Recognition by Toll-like Receptors: The Impact of Nucleoside Modification and the Evolutionary Origin of RNA](https://doi.org/10.1016/j.immuni.2005.06.008) · `wrk:b74e57850912569dfffb`
- **Recognition (2023):** [The Nobel Prize in Physiology or Medicine 2023](https://www.nobelprize.org/prizes/medicine/2023/summary/) · `wrk:75fc177bbac24ea2f4ed`

### Foundation relations

- `specializes` → `meta:biology-evolution:homeostasis` — The intervention tunes innate sensing to enable a therapeutic payload.

### Comment

The Meta-Principle is a platform-enabling control of innate recognition, not a universal claim that modified mRNA is non-immunogenic.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `5811822683d46f49db13cc88bf7cf4a981310def4a72f1906a339d9d439695f3`

---

## `meta:medicine-epidemiology:herd-immunity` — Population Immunity Reduces Transmission Nonlinearly Through Contact Structure

**Epistemic type:** epidemiological mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `herd-immunity`, `vaccination`, `indirect-effect`, `contact-network`

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

- **Foundation (2011):** [Herd Immunity: A Rough Guide](https://doi.org/10.1093/cid/cir007) · `wrk:b003f986a41e5ea492e7`
- **Quantitative Formulation (1985):** [A Quantitative Approach to the Herd-Immunity Effect](https://doi.org/10.1016/0140-6736(85)92748-6) · `wrk:3c0f4f338c26ed5b0211`

### Comment

Thresholds are often communicated as precise universal numbers. They should instead be represented as model-dependent ranges with uncertainty and equity considerations.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `9a59f5609fd05cf8afa1cb9752742b95ffea4e393f6704bd6aa7bde1cc773998`

---

## `meta:medicine-epidemiology:decision-threshold-net-benefit` — Prediction Is Clinically Useful Only When It Improves Decisions at Relevant Thresholds

**Epistemic type:** clinical decision principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `decision-threshold`, `net-benefit`, `clinical-prediction`, `utility`

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

- **Foundation (2006):** [Decision Curve Analysis: A Novel Method for Evaluating Prediction Models](https://doi.org/10.1177/0272989X06295361) · `wrk:ca6e433adb91fec0d358`
- **Book Synthesis (2009):** [Clinical Prediction Models](https://doi.org/10.1007/978-0-387-77244-8) · `wrk:82fdcd48f875342d7f50`

### Comment

Model deployment should be evaluated as an intervention, including workflow, automation bias, equity, and downstream treatment effects.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `db60993ce652d99b12d7a2823e4b9961c49d5765abcf45df021d723c15376a2c`

---

## `meta:medicine-epidemiology:randomization-causal-balance` — Random Assignment Creates Comparable Treatment Groups in Expectation

**Epistemic type:** causal design principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `randomization`, `causal-inference`, `clinical-trial`, `allocation`

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

- **Foundation (1935):** [The Design of Experiments](https://archive.org/details/designofexperime00fish) · `wrk:c824369df72b477bcdf7`
- **Clinical Landmark (1948):** [Streptomycin Treatment of Pulmonary Tuberculosis](https://doi.org/10.1136/bmj.2.4582.769) · `wrk:8491af5d7fec976ea3ad`

### Comment

Randomization is a design property, not a guarantee of good measurement or external validity. Reports should preserve allocation, concealment, adherence, attrition, and analysis details.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `d8aec7e9d244f4e308948ca18cb1c84857c68a144a8b61ee3eb2a2906791d366`

---

## `meta:medicine-epidemiology:screening-benefit-harm` — Screening Can Improve Outcomes Only If Earlier Detection Changes Net Patient Benefit

**Epistemic type:** clinical decision proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `screening`, `overdiagnosis`, `lead-time-bias`, `net-benefit`

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

- **Foundation (1968):** [Principles and Practice of Screening for Disease](https://iris.who.int/handle/10665/37650) · `wrk:4cd07d09b7334672e179`
- **Harm Refinement (2010):** [Quantifying Overdiagnosis in Cancer Screening](https://doi.org/10.1093/jnci/djp483) · `wrk:fc0dff0881c756477dba`

### Comment

Principia should distinguish detection yield, stage shift, disease-specific mortality, all-cause outcomes, and patient-centered net benefit.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `d4e8640cf8a4ec8a940896c6b9317c7a28bd4b5d43eda86897a5aa50a6ac6139`

---

## `meta:medicine-epidemiology:external-validity-transport` — Trial Efficacy Does Not Automatically Transport to New Patients or Settings

**Epistemic type:** transportability proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `external-validity`, `transportability`, `trial-population`, `implementation`

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

- **Foundation (2005):** [External Validity of Randomised Controlled Trials](https://doi.org/10.1016/S0140-6736(04)17323-7) · `wrk:28a875f0fc0ce9ae03d3`
- **Formalization (2012):** [Transportability of Causal and Statistical Relations](https://doi.org/10.1073/pnas.1204599109) · `wrk:9870f0bc64181d5c5c7e`

### Comment

“Real-world” is not a guarantee of representativeness. New Principles should specify target population, care pathway, and effect scale.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8bb536a04bf2f6f5a7652cba006ab6fd02e189b1267cae55217f82b8be391933`

---

## `meta:medicine-epidemiology:clonal-evolution-cancer` — Tumors Evolve Through Heritable Variation, Selection, Drift, and Ecological Interaction

**Epistemic type:** cancer evolution principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_disease_evolution_principle`  
**Introduced / developed:** 1976–present  
**Tags:** `clonal-evolution`, `cancer`, `heterogeneity`, `resistance`

### Argument & interpretation

A tumor is a heterogeneous evolving population. Heritable genetic and epigenetic changes generate variation, while microenvironmental conditions, immune pressure, and therapy select lineages; drift and spatial structure further shape clonal dynamics and resistance.

### Boundary & conditions

- Not every detectable subclone is functionally important.
- Sampling captures only part of spatial and temporal heterogeneity.
- Non-genetic plasticity and cell–cell cooperation complicate simple branching models.

### Application

- precision oncology
- resistance management
- liquid biopsy
- combination therapy
- tumor phylogenetics

### Basics

Peter Nowell articulated the clonal-evolution model of cancer in 1976; sequencing and longitudinal sampling later revealed branched and convergent evolution.

### Paper / work evidence

- **Foundation (1976):** [The Clonal Evolution of Tumor Cell Populations](https://doi.org/10.1126/science.959840) · `wrk:466da5c9636900d00c26`
- **Genomic-Evidence (2012):** [Intratumor Heterogeneity and Branched Evolution Revealed by Multiregion Sequencing](https://doi.org/10.1056/NEJMoa1113205) · `wrk:23376983694374e31e87`

### Foundation relations

- `specializes` → `meta:biology-evolution:natural-selection` — Tumor lineages undergo selection in a somatic ecosystem.
- `depends_on` → `meta:biology-evolution:mutation-selection-drift` — Stochastic lineage dynamics can matter, especially in small or spatially isolated populations.

### Comment

This is a root for adaptive therapy and resistance claims, but child relations must distinguish observed lineage structure from inferred fitness or causal resistance.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `a3ce615947b997273dafdf2706d0dc69a501ebe0b7ae5f9b62dd1e522816c878`

---

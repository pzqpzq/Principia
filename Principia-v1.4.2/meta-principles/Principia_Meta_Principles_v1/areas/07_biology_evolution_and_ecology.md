# Biology, Evolution, and Ecology: Meta-Principles

This file contains 16 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `biology-evolution`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:biology-evolution:natural-selection — Heritable Variation with Differential Reproduction Produces Adaptive Change

- **Epistemic type:** `evolutionary principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `natural-selection`, `heritability`, `fitness`, `adaptation`

### Argument & interpretation

When individuals or replicators differ in heritable traits that affect survival or reproduction, trait frequencies change across generations. Selection can create adaptation without foresight by cumulatively retaining variants that reproduce better in the current environment.

### Boundary & conditions

- Selection requires heritable variation and differential reproductive success.
- Drift, mutation, migration, developmental constraints, and changing environments also shape evolution.
- A trait can be a by-product, historical legacy, or neutral rather than an adaptation.

### Application

- evolutionary biology
- breeding
- pathogen evolution
- evolutionary computation
- ecology

### Basics

Darwin and Wallace formulated natural selection in 1858–1859; population genetics by Fisher, Haldane, and Wright integrated it with Mendelian inheritance in the twentieth century.

### Paper / work evidence

- **Foundation:** [On the Origin of Species](https://darwin-online.org.uk/Variorum/1859/1859-1-c-1859.html) (1859)
- **Population-genetic foundation:** [The Correlation Between Relatives on the Supposition of Mendelian Inheritance](https://doi.org/10.1017/S0021859600009644) (1918)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Adaptationist stories are easy to invent after the fact. Principia should require fitness comparisons, heritability, and plausible historical alternatives.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `67d2193714aeda3bee708b7d0cad8d1c3d8f104d08f9067b8dd324feb9bad1fd`</sub>

---

## meta:biology-evolution:mutation-selection-drift — Evolution Reflects Mutation, Selection, Drift, and Gene Flow Together

- **Epistemic type:** `population-genetic framework`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `mutation`, `selection`, `drift`, `gene-flow`

### Argument & interpretation

Allele-frequency change results from new variation, systematic fitness differences, finite-population sampling, migration, and recombination. Their relative strength depends on effective population size, selection coefficient, mutation rate, and population structure.

### Boundary & conditions

- Simple models often assume random mating, constant fitness, and fixed population size.
- Linked selection, demographic history, and spatial structure alter effective parameters.
- Phenotypic evolution also depends on development and environment.

### Application

- population genomics
- conservation
- microbial evolution
- breeding

### Basics

Fisher, Haldane, and Wright established mathematical population genetics in the 1920s–1930s. The modern synthesis connected these forces to natural history.

### Paper / work evidence

- **Foundation:** [Evolution in Mendelian Populations](https://doi.org/10.1093/genetics/16.2.97) (1931)
- **Synthesis:** [The Genetical Theory of Natural Selection](https://doi.org/10.1093/oso/9780198504405.001.0001) (1930)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

No single force should be inferred from a frequency trajectory without competing models. Large changes can arise from bottlenecks or migration rather than adaptation.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `7add1c5da811ed6406b1808e5a680417fdde8cfd79d7383981fda4375845a842`</sub>

---

## meta:biology-evolution:neutral-theory — Much Molecular Change Can Be Selectively Neutral or Nearly Neutral

- **Epistemic type:** `neutral theory`
- **Principia kind:** `hypothesis`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `neutral-theory`, `genetic-drift`, `molecular-evolution`, `null-model`

### Argument & interpretation

Many molecular substitutions and polymorphisms can spread by genetic drift because their fitness effects are zero or small relative to $1/N_e$. Molecular evolution therefore need not be interpreted as adaptation at every site.

### Boundary & conditions

- The fraction of neutral change varies by genome region, organism, population size, and environment.
- Positive and purifying selection remain pervasive.
- Demography can mimic selection in polymorphism data.

### Application

- molecular evolution
- phylogenetics
- population genomics
- comparative biology

### Basics

Motoo Kimura proposed the neutral theory in 1968; King and Jukes independently assembled supporting arguments in 1969. Ohta developed nearly neutral theory.

### Paper / work evidence

- **Foundation:** [Evolutionary Rate at the Molecular Level](https://doi.org/10.1038/217624a0) (1968)
- **Co-foundation:** [Non-Darwinian Evolution](https://doi.org/10.1126/science.164.3881.788) (1969)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The theory is a null model, not a denial of selection. Principia should treat adaptive claims as requiring evidence beyond sequence change alone.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `cf2387988f6f29360b79c46b310e94fb881b257f317da5652e16c7351bbd9494`</sub>

---

## meta:biology-evolution:price-equation — Evolutionary Change Decomposes into Selection and Transmission Terms

- **Epistemic type:** `Price equation`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `price-equation`, `selection`, `transmission`, `covariance`

### Argument & interpretation

The Price equation writes change in mean trait as a covariance between trait and relative fitness plus expected within-lineage change: $\Delta\bar z=\operatorname{Cov}(w,z)/\bar w+E(w\Delta z)/\bar w$. It is an accounting identity applicable across levels.

### Boundary & conditions

- The equation does not by itself specify mechanisms or predict dynamics.
- Choice of entities, traits, and fitness determines interpretation.
- Causal conclusions require additional assumptions.

### Application

- multilevel selection
- cultural evolution
- quantitative genetics
- evolutionary epidemiology

### Basics

George Price derived the equation around 1970; Hamilton and later authors used and generalized it for selection at multiple levels.

### Paper / work evidence

- **Foundation:** [Selection and Covariance](https://doi.org/10.1038/227520a0) (1970)
- **Exposition:** [Natural Selection and the Concept of a Breeding Value](https://doi.org/10.1111/j.1558-5646.1997.tb05096.x) (1997)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The equation organizes reasoning but can become tautological if variables are chosen post hoc. Principia should link mechanistic models that make its terms predictive.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c6931df7c77032d1a966d139fdfc6fb888b91d8cd0a0cbe544865139e3070106`</sub>

---

## meta:biology-evolution:hamilton-rule — Social Traits Can Spread When Relatedness-Weighted Benefits Exceed Costs

- **Epistemic type:** `Hamilton rule`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `hamilton-rule`, `inclusive-fitness`, `cooperation`, `relatedness`

### Argument & interpretation

Under appropriate definitions, a social trait is favored when $rB>C$, where $C$ is the actor’s fitness cost, $B$ the recipient benefit, and $r$ genetic relatedness or regression linking their genotypes. The rule captures indirect fitness effects.

### Boundary & conditions

- Simple additive forms can fail with nonlinear interactions, demographic feedback, or complex class structure.
- Relatedness is not merely genealogical closeness; it is model-dependent statistical association.
- Group-selection and inclusive-fitness descriptions can be equivalent or contentious depending on formulation.

### Application

- social evolution
- cooperation
- microbial communities
- evolutionary game theory

### Basics

W. D. Hamilton developed inclusive-fitness theory in two 1964 papers, building on Fisher, Haldane, and population genetics.

### Paper / work evidence

- **Foundation:** [The Genetical Evolution of Social Behaviour I](https://doi.org/10.1016/0022-5193(64)90038-4) (1964)
- **Continuation:** [The Genetical Evolution of Social Behaviour II](https://doi.org/10.1016/0022-5193(64)90039-6) (1964)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The rule is powerful but often invoked qualitatively without measuring costs, benefits, and relatedness in a consistent fitness currency.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `371735c6078e6b88d7408cc2b1e718a61e21d6450cf53591c11f5a3a754c047d`</sub>

---

## meta:biology-evolution:evolutionarily-stable-strategy — An ESS Resists Invasion by Rare Alternatives

- **Epistemic type:** `evolutionary game theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `ess`, `evolutionary-game-theory`, `invasion`, `stability`

### Argument & interpretation

A strategy is evolutionarily stable if, when common, no rare mutant strategy can increase under the specified game and population dynamics. ESS strengthens Nash equilibrium with invasion resistance conditions.

### Boundary & conditions

- ESS depends on payoff structure, population mixing, mutation, and dynamics.
- A game can have multiple ESSs, cycles, or no ESS.
- Finite populations and stochasticity alter invasion probabilities.

### Application

- behavioral ecology
- host-pathogen interactions
- cooperation
- adaptive dynamics

### Basics

John Maynard Smith and George Price introduced ESS in the early 1970s, importing game theory into evolutionary biology.

### Paper / work evidence

- **Foundation:** [The Logic of Animal Conflict](https://doi.org/10.1038/246015a0) (1973)
- **Synthesis:** [Evolution and the Theory of Games](https://doi.org/10.1017/CBO9780511806292) (1982)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

An ESS is not morally desirable or globally optimal. Principia should distinguish equilibrium stability from welfare and transient accessibility.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `42155b3fa2467ef3d03f7d37e62c90138c25c8eaa3cfcf9ed199aef98f117e36`</sub>

---

## meta:biology-evolution:life-history-tradeoffs — Finite Resources Create Trade-offs Among Growth, Reproduction, and Survival

- **Epistemic type:** `life-history principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `life-history`, `tradeoff`, `allocation`, `fitness`

### Argument & interpretation

Organisms allocate limited energy and time among maintenance, growth, current reproduction, future reproduction, and defense. Improvements in one component often reduce another, shaping age at maturity, fecundity, lifespan, and parental investment.

### Boundary & conditions

- Trade-offs can be masked by resource acquisition differences or environmental quality.
- Physiological mechanisms and genetic correlations vary among species.
- Plasticity can shift allocation with conditions.

### Application

- evolutionary ecology
- aging
- reproductive biology
- conservation

### Basics

Life-history theory developed through Fisher, Cole, Williams, Lack, and later synthesis by Stearns and Roff.

### Paper / work evidence

- **Foundation:** [The Evolution of Life Histories](https://global.oup.com/academic/product/the-evolution-of-life-histories-9780198577416) (1992)
- **Application:** [Pleiotropy, Natural Selection, and the Evolution of Senescence](https://doi.org/10.1111/j.1558-5646.1957.tb02911.x) (1957)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Observed positive correlations do not disprove trade-offs if high-quality individuals acquire more resources. Experimental manipulation is often required.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `435c9368a1089190c8bc029b8a935ca24131ced0fa13c4f35da96662f9cae120`</sub>

---

## meta:biology-evolution:robustness-plasticity-evolvability — Biological Systems Balance Robustness, Plasticity, and Evolvability

- **Epistemic type:** `evolutionary systems principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `robustness`, `plasticity`, `evolvability`, `canalization`

### Argument & interpretation

Robustness buffers perturbations, plasticity changes phenotype within a lifetime, and evolvability enables heritable innovation. Redundancy, modularity, neutral networks, and regulatory architecture can support one property while constraining or facilitating others.

### Boundary & conditions

- Relationships are not universally antagonistic or synergistic.
- Robustness at one scale can create fragility at another.
- Plastic responses can be adaptive, neutral, or maladaptive.

### Application

- development
- gene regulation
- systems biology
- evolutionary design
- resilience

### Basics

Canalization and genetic assimilation were developed by Waddington; modern network and protein studies connected robustness with evolvability in the 1990s–2000s.

### Paper / work evidence

- **Foundation:** [Robustness and Evolvability in Living Systems](https://doi.org/10.1515/9781400831566) (2005)
- **Empirical perspective:** [Robustness and Evolvability in Living Systems](https://doi.org/10.1038/nature01765) (2003)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Principia should avoid one-dimensional “fitness improvement” narratives. A change may improve immediate robustness while reducing future adaptive capacity.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `4af1c095588d0effec8de51634aeb2a3a00ccf0ed00255343306f23f53d2d966`</sub>

---

## meta:biology-evolution:central-dogma — Sequence Information Normally Flows from Nucleic Acid to Protein, Not Back from Protein

- **Epistemic type:** `central dogma`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `central-dogma`, `information-flow`, `dna`, `protein`

### Argument & interpretation

The central dogma constrains transfer of sequence information: DNA can be copied to DNA and transcribed to RNA; RNA can be copied or reverse-transcribed; nucleic-acid sequence specifies protein, but protein sequence is not copied back into nucleic acid by templated information transfer.

### Boundary & conditions

- Epigenetic inheritance, prions, and regulatory feedback alter states without violating the narrow sequence-information claim.
- Reverse transcription is allowed in Crick’s clarified formulation.
- Horizontal transfer changes lineage but not the molecular direction rule.

### Application

- molecular biology
- genetics
- biotechnology
- evolution

### Basics

Francis Crick proposed the central dogma in 1958 and clarified it in a 1970 Nature paper after discovery of reverse transcriptase.

### Paper / work evidence

- **Foundation:** [Central Dogma of Molecular Biology](https://doi.org/10.1038/227561a0) (1970)
- **Origin:** [On Protein Synthesis](https://profiles.nlm.nih.gov/spotlight/sc/catalog/nlm:nlmuid-101584582X90-doc) (1958)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The slogan “DNA makes RNA makes protein” is incomplete. Principia should retain the precise prohibition and avoid claiming genes unidirectionally determine phenotype.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `69fb08a05d77c7e0e21fd1e892bb89668cb3a99421b2eede1ec2d3ef51ca34bd`</sub>

---

## meta:biology-evolution:homeostasis — Feedback Maintains Internal Variables Within Viable Ranges

- **Epistemic type:** `physiological principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `homeostasis`, `feedback`, `regulation`, `physiology`

### Argument & interpretation

Homeostatic systems sense deviations from regulated variables and adjust effectors to keep temperature, pH, glucose, osmolarity, activity, or other quantities within viable ranges. Regulation is dynamic and can involve anticipatory and hierarchical control.

### Boundary & conditions

- Set points can change with development, circadian state, disease, and environment.
- Perfect constancy is neither possible nor always adaptive.
- Observed stability may reflect passive constraints rather than active feedback.

### Application

- physiology
- cell biology
- neuroscience
- synthetic biology
- medicine

### Basics

Claude Bernard emphasized the internal environment in the nineteenth century; Walter Cannon coined and developed homeostasis in the 1920s–1930s.

### Paper / work evidence

- **Foundation:** [The Wisdom of the Body](https://archive.org/details/wisdomofbody0000cann) (1932)
- **Review:** [Homeostasis: The Underappreciated and Far Too Often Ignored Central Organizing Principle of Physiology](https://doi.org/10.3389/fphys.2020.00200) (2020)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Homeostasis should not be used as a generic claim that biology “seeks balance.” The regulated variable, sensor, controller, effector, and disturbance must be identified.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `22ef0936cef1a7fa68d2e0c1127241a7b30263b05d3b79138758843dff0d1cce`</sub>

---

## meta:biology-evolution:niche-construction — Organisms Modify the Selective Environments That Shape Them

- **Epistemic type:** `niche-construction principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `niche-construction`, `feedback`, `ecological-inheritance`, `ecosystem-engineering`

### Argument & interpretation

Organisms alter resources, habitats, signals, and ecological interactions, thereby changing selection pressures for themselves and others. Evolution is therefore coupled between inherited traits and inherited environmental modifications.

### Boundary & conditions

- Environmental modification is not always adaptive or heritable.
- Standard evolutionary models can often incorporate feedback without treating niche construction as a separate evolutionary process.
- The strength of ecological inheritance varies widely.

### Application

- ecology
- evolution
- microbiomes
- human cultural evolution
- ecosystem engineering

### Basics

Lewontin highlighted reciprocal organism–environment construction; Odling-Smee, Laland, and Feldman developed niche-construction theory from the 1980s onward.

### Paper / work evidence

- **Foundation:** [Niche Construction: The Neglected Process in Evolution](https://press.princeton.edu/books/paperback/9780691044378/niche-construction) (2003)
- **Application:** [Niche Construction Theory: A Practical Guide for Ecologists](https://doi.org/10.1086/593707) (2008)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The framework is influential but debated as an extension versus reformulation of standard evolutionary theory. Principia should mark the specific feedback loop rather than the label alone.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `6c710051f92c9b5f5b73e13b262155c34d91294cc10b789b9b280bb697e6ad8b`</sub>

---

## meta:biology-evolution:competitive-exclusion — Stable Coexistence Requires Niche Differentiation or Countervailing Processes

- **Epistemic type:** `competitive-exclusion principle`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `competitive-exclusion`, `coexistence`, `niche`, `resources`

### Argument & interpretation

Under stable conditions, species that depend on exactly the same limiting resource and interact identically cannot coexist indefinitely; one excludes the other. Coexistence requires differentiation, temporal or spatial variability, predation, trade-offs, immigration, or other stabilizing/equalizing mechanisms.

### Boundary & conditions

- Natural communities rarely satisfy identical-niche, equilibrium, and closed-system assumptions.
- Neutral dynamics and slow exclusion can mimic coexistence.
- Multiple resources and nonlinear interactions change outcomes.

### Application

- community ecology
- microbial consortia
- resource competition
- ecosystem design

### Basics

Gause’s experiments in the 1930s and later formulations by Hardin established the competitive-exclusion principle; modern coexistence theory refined the mechanisms.

### Paper / work evidence

- **Foundation:** [The Competitive Exclusion Principle](https://doi.org/10.1126/science.131.3409.1292) (1960)
- **Refinement:** [Mechanisms of Maintenance of Species Diversity](https://doi.org/10.1146/annurev.es.31.110101.160617) (2000)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Use as a boundary condition, not a universal claim that similar species cannot coexist. Principia should identify the limiting resource and stabilizing mechanism.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `de75ab8d49aea37a5f62f137eeebd577c7ad1a422c86481f5a4c30b7130745c9`</sub>

---

## meta:biology-evolution:major-transitions — New Evolutionary Individuals Arise When Cooperation Suppresses Lower-Level Conflict

- **Epistemic type:** `major-transitions principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `major-transitions`, `cooperation`, `individuality`, `multilevel-selection`

### Argument & interpretation

Major transitions—genes to chromosomes, cells to eukaryotes, cells to multicellular organisms, organisms to societies—combine previously independent units into higher-level individuals through cooperation, division of labor, information transmission, and conflict control.

### Boundary & conditions

- The boundaries and number of major transitions are debated.
- Not every association becomes a new evolutionary individual.
- Conflict persists and can re-emerge as cancer, cheating, or segregation distortion.

### Application

- multicellularity
- symbiosis
- social evolution
- origin of life
- multi-agent organization

### Basics

Maynard Smith and Szathmáry synthesized the major-transitions framework in the 1990s; multilevel-selection and individuality research refined criteria.

### Paper / work evidence

- **Foundation:** [The Major Transitions in Evolution](https://global.oup.com/academic/product/the-major-transitions-in-evolution-9780198502944) (1995)
- **Refinement:** [Major Evolutionary Transitions in Individuality](https://doi.org/10.1098/rstb.2016.0396) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The analogy to artificial multi-agent systems is useful only when reproduction, heritability, and conflict-control mechanisms are mapped explicitly.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `11354f9efebae65211e471dac3a4eae1df5bf48b366392c7d96f1ef3ee87b2a3`</sub>

---

## meta:biology-evolution:allometric-scaling — Biological Rates and Forms Scale Systematically with Size

- **Epistemic type:** `allometric observation`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `allometry`, `scaling`, `body-size`, `metabolism`

### Argument & interpretation

Many physiological rates, lifespans, structures, and ecological quantities scale approximately as powers of body mass, $Y=Y_0M^b$. Such relations reveal geometric, transport, energetic, and life-history constraints across size ranges.

### Boundary & conditions

- Exponents vary among taxa, traits, temperature regimes, and statistical methods.
- A fitted power law need not imply one universal network mechanism.
- Phylogenetic nonindependence and restricted ranges can bias slopes.

### Application

- physiology
- ecology
- biomechanics
- drug dosing
- evolution

### Basics

Kleiber documented metabolic scaling in the 1930s. West, Brown, and Enquist proposed network-based quarter-power explanations in the 1990s, sparking extensive debate.

### Paper / work evidence

- **Foundation:** [A General Model for the Origin of Allometric Scaling Laws in Biology](https://doi.org/10.1126/science.276.5309.122) (1997)
- **Synthesis:** [Scaling in Biology](https://global.oup.com/academic/product/scaling-in-biology-9780195131421) (2000)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Principia should preserve taxonomic range and uncertainty in exponent $b$. “Three-quarter law” is not exact across all organisms and conditions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `4303220f3abcb1e9f5815c2e57c7003ca6c7fdb08ef3e9fa1a1bf842745d9ac2`</sub>

---

## meta:biology-evolution:red-queen — Relative Fitness Can Require Continuous Adaptation in Coevolving Systems

- **Epistemic type:** `Red Queen hypothesis`
- **Principia kind:** `hypothesis`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `red-queen`, `coevolution`, `arms-race`, `frequency-dependence`

### Argument & interpretation

When antagonists or competitors adapt in response to one another, a lineage may need continual evolutionary change merely to maintain relative fitness. Host–pathogen arms races and frequency-dependent selection can sustain turnover without long-term absolute improvement.

### Boundary & conditions

- Coevolution can stabilize, cycle, escalate, or terminate depending on costs and ecological structure.
- Not all rapid evolution is Red Queen dynamics.
- Evidence requires reciprocal adaptation, not one-sided environmental change.

### Application

- host-pathogen evolution
- sexual reproduction
- immune systems
- competitive ecology

### Basics

Leigh Van Valen proposed the Red Queen hypothesis in 1973 from extinction patterns; later theory and experiments linked it to coevolution and sex.

### Paper / work evidence

- **Foundation:** [A New Evolutionary Law](https://ebme.marine.rutgers.edu/HistoryEarthSystems/HistEarthSystems_Fall2010/VanValen%201973%20Evol%20Theory.pdf) (1973)
- **Refinement:** [The Red Queen and the Court Jester](https://doi.org/10.1111/j.1461-0248.2009.01398.x) (2009)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

The metaphor can obscure measurable mechanisms. Principia should identify the interacting lineages, feedback, and fitness metric.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c8f27c7d187042c9b1ea7c7a62b73d601da06a15932bb0813fd4a7a8d955b548`</sub>

---

## meta:biology-evolution:ecological-resilience — Ecosystems Can Absorb Disturbance Yet Shift Abruptly Between Regimes

- **Epistemic type:** `resilience principle`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `resilience`, `regime-shift`, `hysteresis`, `ecosystems`

### Argument & interpretation

Ecological resilience is the capacity of a system to persist within a regime despite disturbance. Nonlinear feedbacks can create alternative stable states, thresholds, and hysteresis, so recovery after crossing a boundary may require more than reversing the original pressure.

### Boundary & conditions

- Evidence for alternative stable states requires ruling out slow transients and external forcing.
- Resilience of one function can conflict with biodiversity or social goals.
- Thresholds are often uncertain and scale-dependent.

### Application

- ecosystem management
- conservation
- fisheries
- microbiomes
- climate adaptation

### Basics

C. S. Holling distinguished engineering resilience from ecological regime persistence in 1973; later work on critical transitions and adaptive cycles expanded the framework.

### Paper / work evidence

- **Foundation:** [Resilience and Stability of Ecological Systems](https://doi.org/10.1146/annurev.es.04.110173.000245) (1973)
- **Refinement:** [Catastrophic Shifts in Ecosystems](https://doi.org/10.1038/35098000) (2001)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- What unit, environment, timescale, and heritable variation make the new biological Principle operate?
- Does the claim separate selection, drift, constraint, plasticity, and feedback?

### Comment

Resilience is not equivalent to desirability. A degraded state can be highly resilient. Principia should name the regime, function, disturbance, and recovery criterion.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `00bebffafeaefd076da3d365870bbbac2590d3f286b16aaaa6c3535b1fdd1499`</sub>


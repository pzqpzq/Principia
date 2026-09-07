# Neuroscience and Cognition: Meta-Principles

This file contains 15 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `neuroscience-cognition`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:neuroscience-cognition:hebbian-plasticity — Correlated Activity Can Strengthen Functional Connections

- **Epistemic type:** `Hebbian principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `hebbian`, `synaptic-plasticity`, `association`, `learning`

### Argument & interpretation

When presynaptic activity repeatedly contributes to postsynaptic firing, synaptic efficacy can increase. Hebbian rules convert correlated activity into associative structure and provide a local mechanism for learning representations and memories.

### Boundary & conditions

- Pure Hebbian growth is unstable without normalization, inhibition, decay, or homeostasis.
- Correlation does not reveal whether a synapse caused the postsynaptic response.
- Biological plasticity depends on timing, neuromodulators, dendrites, and cell type.

### Application

- learning
- memory
- sensory development
- neuromorphic AI

### Basics

Donald Hebb articulated the cell-assembly rule in 1949. Long-term potentiation, spike-timing-dependent plasticity, and BCM theory provided physiological and mathematical refinements.

### Paper / work evidence

- **Foundation:** [The Organization of Behavior](https://archive.org/details/organizationofbe00hebb) (1949)
- **Formal refinement:** [A Generalized Theory of the Development of Selectivity in Visual Cortex](https://doi.org/10.1523/JNEUROSCI.02-01-00032.1982) (1982)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

“Fire together, wire together” is a mnemonic, not a complete learning law. Principia should preserve induction protocol and stabilizing mechanism.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3c00a26b3ca44556507fbcae41e0ee2d0cd590692cef15c030a5b4b2359a1885`</sub>

---

## meta:neuroscience-cognition:homeostatic-plasticity — Neural Circuits Stabilize Activity While Retaining Capacity to Learn

- **Epistemic type:** `homeostatic plasticity principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `homeostasis`, `synaptic-scaling`, `stability`, `plasticity`

### Argument & interpretation

Neurons and circuits adjust excitability, synaptic scaling, and inhibition to keep firing and network activity within functional ranges. Slow negative feedback counterbalances destabilizing positive-feedback learning rules.

### Boundary & conditions

- Homeostatic targets vary by cell, state, development, and timescale.
- Compensation can be local or network-wide and may become maladaptive in disease.
- Stable average rate does not guarantee stable information coding.

### Application

- development
- epilepsy
- continual learning
- neuromorphic systems

### Basics

Activity-dependent compensation was observed across preparations; Turrigiano and colleagues established synaptic scaling in the 1990s, and reviews integrated multiple mechanisms.

### Paper / work evidence

- **Foundation:** [Homeostatic Plasticity in the Developing Nervous System](https://doi.org/10.1038/nrn1327) (2004)
- **Evidence:** [Activity-Dependent Scaling of Quantal Amplitude in Neocortical Neurons](https://doi.org/10.1038/36103) (1998)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

This principle is a root for stability–plasticity trade-offs. A new learning rule should specify how runaway excitation or silence is prevented.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `6f5b3e472781029fff5d4edf896e1df20e997209c450062f5f87e1dc937b5bd5`</sub>

---

## meta:neuroscience-cognition:efficient-coding — Sensory Systems Adapt Codes to Input Statistics and Resource Constraints

- **Epistemic type:** `efficient coding hypothesis`
- **Principia kind:** `hypothesis`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `efficient-coding`, `information`, `sensory`, `resource-constraint`

### Argument & interpretation

Neural representations can maximize transmitted information or task utility subject to limits on spikes, noise, wiring, and dynamic range. Whitening, gain control, sparse responses, and receptive-field adaptation can emerge from matching codes to environmental statistics.

### Boundary & conditions

- The objective may be behaviorally weighted rather than raw information maximization.
- Metabolic, developmental, and robustness constraints can dominate.
- Observed efficiency does not uniquely identify the optimized quantity.

### Application

- sensory neuroscience
- neural coding
- compression
- neuromorphic AI

### Basics

Horace Barlow proposed efficient coding in 1961; Laughlin, Atick, Redlich, and later work tested statistical predictions in sensory systems.

### Paper / work evidence

- **Foundation:** [Possible Principles Underlying the Transformations of Sensory Messages](https://www.cns.nyu.edu/~eero/NOTES/02-barLow61.pdf) (1961)
- **Evidence:** [A Simple Coding Procedure Enhances a Neuron’s Information Capacity](https://doi.org/10.1007/BF00342793) (1981)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

The hypothesis is powerful but flexible. Principia should require a declared input ensemble, resource constraint, and quantitative objective.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `a39fa687e8fbbbfdfaff6c665ce795d3074b664d93471789003fc5d694242c0a`</sub>

---

## meta:neuroscience-cognition:sparse-coding — Sparse Population Activity Can Support Efficient and Separable Representations

- **Epistemic type:** `coding principle`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `sparse-coding`, `representation`, `energy`, `receptive-fields`

### Argument & interpretation

A sparse code represents each input with a small active subset of units, reducing activity cost and overlap while supporting associative capacity and linear readout. Learning sparse generative models of natural images produces localized receptive fields resembling visual cortex.

### Boundary & conditions

- Lifetime and population sparseness are distinct.
- Extreme sparsity can reduce robustness and information throughput.
- Sparse activity alone does not prove an efficient or causal representation.

### Application

- visual cortex
- memory
- olfaction
- representation learning

### Basics

Barlow’s efficient-coding ideas motivated sparse representations; Olshausen and Field demonstrated receptive-field emergence in 1996. Experimental studies later clarified definitions.

### Paper / work evidence

- **Foundation:** [Emergence of Simple-Cell Receptive Field Properties by Learning a Sparse Code](https://doi.org/10.1038/381607a0) (1996)
- **Boundary:** [Sparse Coding in Striate and Extrastriate Visual Cortex](https://doi.org/10.1152/jn.00594.2010) (2011)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

Principia should record the sparsity metric, coding accuracy, energy cost, and task. “Sparse” is not a single property.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `085610fee8522dad716e910300d919760b1980f59b404935877490797aad350c`</sub>

---

## meta:neuroscience-cognition:predictive-coding — Hierarchical Circuits May Encode Prediction Errors Rather Than Raw Inputs

- **Epistemic type:** `predictive coding hypothesis`
- **Principia kind:** `hypothesis`
- **Maturity:** `supported`
- **Stability:** `contested`
- **Review status:** `curated_draft`
- **Tags:** `predictive-coding`, `hierarchy`, `prediction-error`, `inference`

### Argument & interpretation

Predictive-coding models propose that higher levels generate predictions of lower-level activity, while feedforward signals convey residual errors. Updating latent causes and predictions can approximate probabilistic inference and explain contextual modulation.

### Boundary & conditions

- Multiple architectures can produce similar neural signatures.
- Prediction-error neurons and generative messages are not uniquely identified by suppression effects.
- Some models require biologically disputed weight symmetry or timing.

### Application

- perception
- hierarchical inference
- attention
- learning
- AI

### Basics

Predictive ideas trace to Helmholtz and early coding theory; Rao and Ballard formulated a cortical model in 1999, and Friston developed free-energy formulations.

### Paper / work evidence

- **Foundation:** [Predictive Coding in the Visual Cortex](https://doi.org/10.1038/4580) (1999)
- **Refinement:** [An Approximation of the Error Backpropagation Algorithm in a Predictive Coding Network](https://doi.org/10.1162/neco_a_00949) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

This remains a broad model family, not a single established circuit law. Principia should preserve the exact computational and anatomical implementation.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `7deac449b6a62007c2307ec47ebb5645db47fef5717531bef58fa7168be9a53c`</sub>

---

## meta:neuroscience-cognition:population-coding — Variables Are Often Represented by Distributed Population Activity

- **Epistemic type:** `coding observation`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `population-coding`, `distributed-representation`, `decoding`, `neural-manifold`

### Argument & interpretation

Behaviorally relevant variables can be encoded across the joint activity of many neurons rather than by one dedicated unit. Population vectors, probabilistic codes, and manifold representations exploit tuning diversity and redundancy.

### Boundary & conditions

- Decoding success does not prove the brain uses the same decoder.
- Correlated noise can limit information.
- Representations can be mixed, dynamic, and task-dependent.

### Application

- motor control
- sensory coding
- brain–computer interfaces
- systems neuroscience

### Basics

Georgopoulos and colleagues demonstrated population-vector coding of movement direction in the 1980s; later work developed probabilistic and high-dimensional population codes.

### Paper / work evidence

- **Foundation:** [Neuronal Population Coding of Movement Direction](https://doi.org/10.1126/science.3749885) (1986)
- **Refinement:** [Probabilistic Population Codes and the Exponential Family of Distributions](https://doi.org/10.1371/journal.pcbi.0020092) (2006)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

A linear decoder can recover information that is not causally used. Intervention and temporal evidence should accompany mechanistic claims.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `6387f2f6dfdc769062d472ad97d615c2d9aacda90b6abc71e37581ac2576c1d8`</sub>

---

## meta:neuroscience-cognition:excitation-inhibition-balance — Strong Excitation Can Be Stabilized by Matching Inhibition

- **Epistemic type:** `network-dynamics principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `excitation`, `inhibition`, `balance`, `asynchronous-state`

### Argument & interpretation

In many cortical regimes, large excitatory and inhibitory currents approximately cancel, leaving fluctuation-driven irregular activity. Balanced networks can support sensitivity, wide dynamic range, and stable asynchronous states.

### Boundary & conditions

- Balance varies across brain regions, states, layers, and timescales.
- Mean current cancellation is not the only form of E/I balance.
- Measured E/I ratios can be distorted by recording methods.

### Application

- cortical dynamics
- epilepsy
- network models
- neuromorphic systems

### Basics

van Vreeswijk and Sompolinsky developed balanced-network theory in the 1990s; intracellular and population studies tested related predictions.

### Paper / work evidence

- **Foundation:** [Chaos in Neuronal Networks with Balanced Excitatory and Inhibitory Activity](https://doi.org/10.1126/science.274.5293.1724) (1996)
- **Review:** [The Asynchronous State in Cortical Circuits](https://doi.org/10.1016/j.neuron.2009.08.026) (2009)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

“E/I imbalance” is too vague as an explanation. The currents, conductances, cell classes, and temporal regime must be specified.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `638a3ecc170aa1d5a432d32c12d80fce786fd274edbd42271d619258015b648e`</sub>

---

## meta:neuroscience-cognition:critical-periods — Plasticity Is Gated by Developmental Windows and Circuit Maturation

- **Epistemic type:** `developmental principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `critical-period`, `development`, `plasticity`, `maturation`

### Argument & interpretation

Experience has disproportionately strong effects during critical or sensitive periods when inhibition, neuromodulation, extracellular matrix, and gene programs permit circuit reorganization. Later plasticity persists but often requires stronger conditions.

### Boundary & conditions

- Window timing differs by function, species, and deprivation history.
- Some apparent closure reflects reduced motivation or access rather than irreversible circuit limits.
- Pathology and interventions can reopen plasticity mechanisms.

### Application

- sensory development
- language
- rehabilitation
- education

### Basics

Hubel and Wiesel’s deprivation experiments established sensitive periods in visual cortex; later work identified molecular brakes and reopening mechanisms.

### Paper / work evidence

- **Foundation:** [The Period of Susceptibility to the Physiological Effects of Unilateral Eye Closure in Kittens](https://doi.org/10.1113/jphysiol.1970.sp008455) (1970)
- **Review:** [Critical Period Plasticity in Local Cortical Circuits](https://doi.org/10.1038/nrn1787) (2005)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

Critical periods should not be generalized into deterministic age deadlines. Principia should state function, evidence, and reversibility.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `4e404876dad1627764e757ff0dd9169a4c91aa5400727dc733b755d55fa383ea`</sub>

---

## meta:neuroscience-cognition:attractor-dynamics — Recurrent Networks Can Store Stable or Metastable Activity Patterns

- **Epistemic type:** `attractor principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `attractor`, `recurrent-network`, `memory`, `dynamics`

### Argument & interpretation

Recurrent interactions can create fixed points, limit cycles, or continuous attractors toward which activity evolves. Attractor basins support pattern completion, working memory, decisions, and low-dimensional latent dynamics.

### Boundary & conditions

- Neural activity can be transient, chaotic, input-driven, or sequential rather than attractor-like.
- Finite noise creates switching and drift.
- Fitted low-dimensional states do not prove recurrent attractor causality.

### Application

- memory
- decision making
- navigation
- motor control
- recurrent AI

### Basics

Hopfield connected associative memory to energy-based attractors in 1982; continuous attractor and dynamical-systems neuroscience expanded the framework.

### Paper / work evidence

- **Foundation:** [Neural Networks and Physical Systems with Emergent Collective Computational Abilities](https://doi.org/10.1073/pnas.79.8.2554) (1982)
- **Evidence:** [Attractor Dynamics in the Hippocampal Representation of the Local Environment](https://doi.org/10.1126/science.1126092) (2006)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

Principia should require perturbation recovery, recurrence evidence, or dynamical signatures—not merely clustering of neural states.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0d3ae24750c67bd28d7de6d9fdac1fed31768ea77fdd2d1508c12f53090910c9`</sub>

---

## meta:neuroscience-cognition:reward-prediction-error — Dopaminergic Signals Track Reward Prediction Errors

- **Epistemic type:** `reinforcement-learning mechanism`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `dopamine`, `prediction-error`, `reward`, `reinforcement-learning`

### Argument & interpretation

Phasic activity in many midbrain dopamine neurons resembles a temporal-difference error: response shifts from unexpected reward to its predictor and dips when expected reward is omitted. Such signals can update values and policies.

### Boundary & conditions

- Dopamine populations are heterogeneous and also encode movement, salience, uncertainty, and state.
- A correlation with TD error does not imply every dopamine signal is scalar reward.
- Learning depends on receptor, timing, and target circuit.

### Application

- reinforcement learning
- motivation
- addiction
- decision neuroscience

### Basics

Schultz, Dayan, and Montague linked primate dopamine recordings to reinforcement-learning prediction errors in 1997.

### Paper / work evidence

- **Foundation:** [A Neural Substrate of Prediction and Reward](https://doi.org/10.1126/science.275.5306.1593) (1997)
- **Review:** [Dopamine Reward Prediction Error Coding](https://doi.org/10.1152/physrev.00023.2015) (2016)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

The canonical result is strong but simplified. Principia should avoid reducing all dopamine function to reward prediction error.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b3b511381f5f80f12f49c3e618d54ac19dbf0baa6f8c20b57c90f2785d9edb9d`</sub>

---

## meta:neuroscience-cognition:working-memory-capacity — Active Working Memory Has Severe Capacity and Interference Limits

- **Epistemic type:** `cognitive observation`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `working-memory`, `capacity`, `chunking`, `interference`

### Argument & interpretation

Only a small number of independent chunks can be actively maintained with high fidelity, and capacity depends on chunking, attention, modality, delay, and interference. Long-term knowledge can compress multiple elements into one functional chunk.

### Boundary & conditions

- A single universal item count is not supported.
- Continuous-resource and slot-like models fit different tasks.
- Performance includes encoding, attention, and retrieval limits.

### Application

- cognition
- interface design
- education
- reasoning agents

### Basics

Miller’s 1956 “seven plus or minus two” emphasized chunking; Cowan later argued for a roughly four-chunk focus under controlled conditions.

### Paper / work evidence

- **Foundation:** [The Magical Number Seven, Plus or Minus Two](https://doi.org/10.1037/h0043158) (1956)
- **Refinement:** [The Magical Number 4 in Short-Term Memory](https://doi.org/10.1017/S0140525X01003922) (2001)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

Principia should treat memory budget as task-dependent. Long prompts or explanations can exceed usable working memory even if token storage is available.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0fcfa1b6685e4e4563e15714eb1a57259d37d821adde9ed682cbbe7edf416975`</sub>

---

## meta:neuroscience-cognition:degeneracy — Different Biological Structures Can Support the Same Function

- **Epistemic type:** `degeneracy principle`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `degeneracy`, `robustness`, `redundancy`, `compensation`

### Argument & interpretation

Degeneracy means structurally different components or pathways can produce similar outputs under some conditions while differing under others. It supports robustness, adaptation, and evolutionary innovation without exact duplication.

### Boundary & conditions

- Functional equivalence is context-dependent and may disappear under perturbation.
- Degeneracy is distinct from simple redundancy.
- Multiple mechanisms complicate causal localization and biomarker interpretation.

### Application

- neural circuits
- genetic networks
- motor control
- resilience

### Basics

Edelman used degeneracy in neural selection theory; Edelman and Gally synthesized biological examples in 2001.

### Paper / work evidence

- **Foundation:** [Degeneracy and Complexity in Biological Systems](https://doi.org/10.1073/pnas.98.24.13763) (2001)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

Ablation failure does not prove irrelevance if compensation exists. Principia should compare acute perturbation, chronic adaptation, and environmental conditions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `9620b20dab1d7592d2eb704755f8c347e3380dc2126507ee57b64221b7ad3d00`</sub>

---

## meta:neuroscience-cognition:integration-segregation — Adaptive Cognition Requires Both Specialized Modules and Their Coordination

- **Epistemic type:** `network principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `integration`, `segregation`, `brain-network`, `modularity`

### Argument & interpretation

Neural systems combine functional segregation—specialized local processing—with integration across distant regions. Effective behavior depends on dynamic coordination rather than maximal global connectivity or complete modular isolation.

### Boundary & conditions

- Measures of integration depend on scale, parcellation, and statistical model.
- Global synchrony can reduce information capacity or accompany pathology.
- Anatomical connectivity does not imply effective information flow.

### Application

- brain networks
- consciousness research
- cognitive control
- multi-agent architecture

### Basics

Tononi, Sporns, and Edelman formalized complexity as a balance of integration and segregation in the 1990s; network neuroscience expanded empirical measures.

### Paper / work evidence

- **Foundation:** [A Measure for Brain Complexity](https://doi.org/10.1073/pnas.91.11.5033) (1994)
- **Application:** [The Human Connectome: A Structural Description of the Human Brain](https://doi.org/10.1371/journal.pcbi.0010042) (2005)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

The balance is not a single optimum across tasks. Principia should specify the computation, timescale, and connectivity measure.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `fa6582284d9e240046adb00b7d1db56cbfb5cc75c6b37e6ea23efbe9ee9a6dfe`</sub>

---

## meta:neuroscience-cognition:active-inference — Agents May Act to Reduce Expected Prediction Error and Uncertainty

- **Epistemic type:** `active-inference hypothesis`
- **Principia kind:** `hypothesis`
- **Maturity:** `contested`
- **Stability:** `contested`
- **Review status:** `curated_draft`
- **Tags:** `active-inference`, `free-energy`, `control`, `generative-model`

### Argument & interpretation

Active-inference models propose that perception and action minimize variational or expected free energy under a generative model. Actions change observations to fulfill prior preferences and reduce uncertainty, linking inference, control, and exploration.

### Boundary & conditions

- The framework is broad and can become difficult to falsify without a precise generative model.
- Alternative reinforcement-learning and control formulations can make similar predictions.
- Biological implementation and objective interpretation remain debated.

### Application

- perception-action loops
- motor control
- psychiatry
- robotics
- AI agents

### Basics

Friston and collaborators developed the free-energy principle and active inference in the 2000s–2010s, drawing on predictive coding, Bayesian inference, and control.

### Paper / work evidence

- **Foundation:** [The Free-Energy Principle: A Unified Brain Theory?](https://doi.org/10.1038/nrn2787) (2010)
- **Critical comparison:** [Active Inference: Demystified and Compared](https://doi.org/10.1162/neco_a_00912) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

This is explicitly a contested hypothesis family. Principia should require discriminating predictions against simpler control or RL models.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `32e6acfb7e357fc0870a01e2490050dd68e34e89a0b95182fd06264b33b37310`</sub>

---

## meta:neuroscience-cognition:stability-plasticity — Learning New Patterns Without Destroying Old Ones Requires Complementary Mechanisms

- **Epistemic type:** `stability-plasticity principle`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `stability-plasticity`, `continual-learning`, `consolidation`, `interference`

### Argument & interpretation

A learning system must remain plastic enough to acquire new knowledge yet stable enough to retain established representations. Replay, consolidation, sparse allocation, modularity, metaplasticity, and complementary fast/slow systems reduce catastrophic interference.

### Boundary & conditions

- No mechanism eliminates interference under unlimited nonstationary learning.
- Retention and rapid adaptation can trade off.
- Biological evidence supports multiple consolidation processes rather than one universal architecture.

### Application

- continual learning
- memory consolidation
- development
- adaptive AI

### Basics

Grossberg framed the stability–plasticity dilemma in adaptive resonance theory; McClelland, McNaughton, and O’Reilly proposed complementary hippocampal and cortical learning systems.

### Paper / work evidence

- **Foundation:** [How Does a Brain Build a Cognitive Code?](https://doi.org/10.1007/BF00337249) (1980)
- **Refinement:** [Why There Are Complementary Learning Systems in the Hippocampus and Neocortex](https://doi.org/10.1037/0033-295X.102.3.419) (1995)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- At which neural scale and timescale does the new Principle operate?
- Which behavioral, circuit, and intervention evidence separates this mechanism from alternatives?

### Comment

Principia should connect lifelong-learning claims to explicit retention tests and distribution sequences, not only final average accuracy.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `df1c5737b0ece5f60d07417f1b005f08795266ff1cf310410ef4b32c1ce6c135`</sub>


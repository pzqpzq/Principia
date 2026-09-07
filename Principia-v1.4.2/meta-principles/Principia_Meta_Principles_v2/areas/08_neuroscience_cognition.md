# Neuroscience and Cognition Meta-Principles

> **Area ID:** `neuroscience-cognition`  
> **Records:** 23  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:neuroscience-cognition:working-memory-capacity` — Active Working Memory Has Severe Capacity and Interference Limits

**Epistemic type:** cognitive observation  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `working-memory`, `capacity`, `chunking`, `interference`

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

- **Foundation (1956):** [The Magical Number Seven, Plus or Minus Two](https://doi.org/10.1037/h0043158) · `wrk:30ade8e97d1b4904ea3b`
- **Refinement (2001):** [The Magical Number 4 in Short-Term Memory](https://doi.org/10.1017/S0140525X01003922) · `wrk:93593399140ffa118410`

### Comment

Principia should treat memory budget as task-dependent. Long prompts or explanations can exceed usable working memory even if token storage is available.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `9676921b0fbfc8e1f27916b90a8fa13ab70a4a757e6457d12e3f299aaeca95de`

---

## `meta:neuroscience-cognition:integration-segregation` — Adaptive Cognition Requires Both Specialized Modules and Their Coordination

**Epistemic type:** network principle  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `integration`, `segregation`, `brain-network`, `modularity`

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

- **Foundation (1994):** [A Measure for Brain Complexity](https://doi.org/10.1073/pnas.91.11.5033) · `wrk:a4b2e58b6c2bcc10780c`
- **Application (2005):** [The Human Connectome: A Structural Description of the Human Brain](https://doi.org/10.1371/journal.pcbi.0010042) · `wrk:0c4139b0c743c0ee2d12`

### Comment

The balance is not a single optimum across tasks. Principia should specify the computation, timescale, and connectivity measure.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `eb0e290e262742f6ee0233fc90f8a341573adea3a1b44efc127d547d36e0fbe9`

---

## `meta:neuroscience-cognition:active-inference` — Agents May Act to Reduce Expected Prediction Error and Uncertainty

**Epistemic type:** active-inference hypothesis  
**Principia kind:** `hypothesis`  
**Maturity:** `contested` · **Stability:** `contested` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `active-inference`, `free-energy`, `control`, `generative-model`

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

- **Foundation (2010):** [The Free-Energy Principle: A Unified Brain Theory?](https://doi.org/10.1038/nrn2787) · `wrk:2bef5ee6423318e6cd00`
- **Critical Comparison (2017):** [Active Inference: Demystified and Compared](https://doi.org/10.1162/neco_a_00912) · `wrk:2cbef7463ad84aa70a26`

### Comment

This is explicitly a contested hypothesis family. Principia should require discriminating predictions against simpler control or RL models.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `f841fdcf7a274cf02f09f0ea3db605b6c347a43c49aad89c1ef020657c711814`

---

## `meta:neuroscience-cognition:global-neuronal-workspace` — Conscious Access May Require Global Broadcasting of Locally Processed Information

**Epistemic type:** global neuronal workspace hypothesis  
**Principia kind:** `hypothesis`  
**Maturity:** `contested` · **Stability:** `contested` · **Review:** `curated_draft`  
**Significance:** `influential_cognitive_theory`  
**Introduced / developed:** 1988–present  
**Tags:** `global-workspace`, `conscious-access`, `broadcast`, `cognition`

### Argument & interpretation

Specialized processors operate largely locally, while a subset of information gains conscious access when recurrent amplification makes it globally available to attention, memory, report, and control systems. The theory predicts late, widespread, and task-dependent ignition signatures.

### Boundary & conditions

- Neural signatures vary with report requirements, attention, and task design.
- Competing theories explain overlapping phenomena.
- Global availability is difficult to separate experimentally from consciousness itself.

### Application

- consciousness science
- attention
- cognitive architecture
- anesthesia
- AI consciousness debates

### Basics

Baars proposed a cognitive global workspace in the 1980s; Dehaene, Changeux, and colleagues developed a neuronal implementation and experimental program.

### Paper / work evidence

- **Foundation (1988):** [A Cognitive Theory of Consciousness](https://www.cambridge.org/core/books/cognitive-theory-of-consciousness/62D79055F4D36BBD39644A0B65A92B69) · `wrk:976abae89ac3147cbde6`
- **Refinement (2014):** [Toward a computational theory of conscious processing](https://doi.org/10.1016/j.conb.2014.01.018) · `wrk:b3c0e65bb4366b7924ad`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:integration-segregation` — Workspace theories require coordinated integration across specialized systems.

### Comment

Keep this as a contested hypothesis. A broadcast-like software architecture is not evidence of phenomenal consciousness.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `1417312f0c855f0067953b4c300c0adaa5f8a914172f5978dab8ddb11846a68a`

---

## `meta:neuroscience-cognition:hebbian-plasticity` — Correlated Activity Can Strengthen Functional Connections

**Epistemic type:** Hebbian principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `hebbian`, `synaptic-plasticity`, `association`, `learning`

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

- **Foundation (1949):** [The Organization of Behavior](https://archive.org/details/organizationofbe00hebb) · `wrk:2769130524f9d2049f95`
- **Formal Refinement (1982):** [A Generalized Theory of the Development of Selectivity in Visual Cortex](https://doi.org/10.1523/JNEUROSCI.02-01-00032.1982) · `wrk:4456e84858d332ce36c3`

### Comment

“Fire together, wire together” is a mnemonic, not a complete learning law. Principia should preserve induction protocol and stabilizing mechanism.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `cd6acf5dc870a39827521a40051a3ee619c1f1b7bd48d91eb6bd975abaa8ef20`

---

## `meta:neuroscience-cognition:degeneracy` — Different Biological Structures Can Support the Same Function

**Epistemic type:** degeneracy principle  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `degeneracy`, `robustness`, `redundancy`, `compensation`

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

- **Foundation (2001):** [Degeneracy and Complexity in Biological Systems](https://doi.org/10.1073/pnas.98.24.13763) · `wrk:338870849bb05e9be0b8`

### Comment

Ablation failure does not prove irrelevance if compensation exists. Principia should compare acute perturbation, chronic adaptation, and environmental conditions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `0a25d755506820e0d7d21c9dbdbecda12b5568036335fb0a085d0a98f41860d1`

---

## `meta:neuroscience-cognition:reward-prediction-error` — Dopaminergic Signals Track Reward Prediction Errors

**Epistemic type:** reinforcement-learning mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `dopamine`, `prediction-error`, `reward`, `reinforcement-learning`

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

- **Foundation (1997):** [A Neural Substrate of Prediction and Reward](https://doi.org/10.1126/science.275.5306.1593) · `wrk:673f7144b4084cd01c55`
- **Review (2016):** [Dopamine Reward Prediction Error Coding](https://doi.org/10.1152/physrev.00023.2015) · `wrk:9ecc1dd6a3a3e77c806b`

### Comment

The canonical result is strong but simplified. Principia should avoid reducing all dopamine function to reward prediction error.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `00d79610ef4bef9134d598b584288ea401be63b5edadad465a117a27d681d99a`

---

## `meta:neuroscience-cognition:complementary-learning-systems` — Fast Episodic Learning and Slow Statistical Learning Are Best Served by Complementary Systems

**Epistemic type:** complementary learning systems theory  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `influential_cognitive_theory`  
**Introduced / developed:** 1995–present  
**Tags:** `complementary-learning`, `episodic`, `statistical-learning`, `replay`

### Argument & interpretation

A fast-learning system can store individual episodes with minimal interference, while a slower system extracts distributed regularities across experiences. Replay and interleaving transfer information between them, resolving part of the stability–plasticity dilemma.

### Boundary & conditions

- The theory is an abstraction and biological implementations are more distributed.
- Replay can reinforce bias or outdated experience.
- Task structure may favor different timescales or more than two systems.

### Application

- continual learning
- memory architectures
- replay
- education
- adaptive agents

### Basics

McClelland, McNaughton, and O’Reilly formulated the theory in 1995, integrating hippocampal memory and connectionist learning.

### Paper / work evidence

- **Foundation (1995):** [Why there are complementary learning systems in the hippocampus and neocortex](https://doi.org/10.1037/0033-295X.102.3.419) · `wrk:286f7010db86982bd1fe`
- **Refinement (2019):** [Complementary Learning Systems](https://doi.org/10.1016/j.tics.2019.04.006) · `wrk:ea694b587c9b2aef0f7c`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:stability-plasticity` — Complementary systems implement a solution to the stability–plasticity trade-off.

### Comment

This is a strong Meta-Principle for AI memory design, but child systems should demonstrate that their fast and slow pathways actually reduce interference.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `ea9b090e85604fb3df3dd153c8bac5490fcc0605ad32fedd16d81357e10b045b`

---

## `meta:neuroscience-cognition:predictive-coding` — Hierarchical Circuits May Encode Prediction Errors Rather Than Raw Inputs

**Epistemic type:** predictive coding hypothesis  
**Principia kind:** `hypothesis`  
**Maturity:** `supported` · **Stability:** `contested` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `predictive-coding`, `hierarchy`, `prediction-error`, `inference`

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

- **Foundation (1999):** [Predictive Coding in the Visual Cortex](https://doi.org/10.1038/4580) · `wrk:80f12413db598fd9813d`
- **Refinement (2017):** [An Approximation of the Error Backpropagation Algorithm in a Predictive Coding Network](https://doi.org/10.1162/neco_a_00949) · `wrk:3d470ce24798e5a86dca`

### Comment

This remains a broad model family, not a single established circuit law. Principia should preserve the exact computational and anatomical implementation.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `a910da11335d3fccc09414c24848bcb0e083d21a866b8c72605d90aeb62943fa`

---

## `meta:neuroscience-cognition:place-cells-cognitive-map` — Hippocampal Populations Encode an Internal Map of Spatial and Relational Context

**Epistemic type:** cognitive map observation  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2014_landmark`  
**Introduced / developed:** 1971–present  
**Tags:** `place-cells`, `cognitive-map`, `hippocampus`, `nobel-2014`

### Argument & interpretation

Place cells fire selectively in particular locations or contexts, supporting the idea that hippocampal ensembles encode a relational map rather than only a stimulus–response chain. Population remapping allows different environments or task contexts to occupy distinct internal states.

### Boundary & conditions

- Place fields depend on sensory cues, behavior, task, and internal state.
- Hippocampal coding extends beyond literal physical space, so “map” is a functional abstraction.
- Correlational firing patterns do not alone establish the readout used for behavior.

### Application

- navigation
- episodic memory
- robotics
- representation learning
- context inference

### Basics

O’Keefe and Dostrovsky reported hippocampal place cells in 1971. O’Keefe, Moser, and Moser received the 2014 Nobel Prize in Physiology or Medicine for the brain’s positioning system.

### Paper / work evidence

- **Foundation (1971):** [The hippocampus as a spatial map. Preliminary evidence from unit activity in the freely-moving rat](https://doi.org/10.1016/0006-8993(71)90358-1) · `wrk:1791276412f9c0d5fa9c`
- **Recognition (2014):** [The Nobel Prize in Physiology or Medicine 2014](https://www.nobelprize.org/prizes/medicine/2014/summary/) · `wrk:97c484a32251a7d76a0c`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:population-coding` — Place coding is distributed across hippocampal populations.
- `depends_on` → `meta:neuroscience-cognition:attractor-dynamics` — Stable maps can be modeled by attractor dynamics.

### Comment

A child Principle should specify whether “space” is physical, conceptual, temporal, or task-relative and how the map is behaviorally read out.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `d368d14af7779d11e68beec7d189dfa1aab5cc1ab612294002e22db6ae24c86d`

---

## `meta:neuroscience-cognition:stability-plasticity` — Learning New Patterns Without Destroying Old Ones Requires Complementary Mechanisms

**Epistemic type:** stability-plasticity principle  
**Principia kind:** `heuristic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `stability-plasticity`, `continual-learning`, `consolidation`, `interference`

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

- **Foundation (1980):** [How Does a Brain Build a Cognitive Code?](https://doi.org/10.1007/BF00337249) · `wrk:e61fd1e10ed035406d74`
- **Refinement (1995):** [Why There Are Complementary Learning Systems in the Hippocampus and Neocortex](https://doi.org/10.1037/0033-295X.102.3.419) · `wrk:286f7010db86982bd1fe`

### Comment

Principia should connect lifelong-learning claims to explicit retention tests and distribution sequences, not only final average accuracy.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `b250c96b5be398702d9ee51cee7129807886e6b508ff930d565fd14e417a1eca`

---

## `meta:neuroscience-cognition:systems-consolidation` — Memory Representations Can Reorganize Across Brain Systems Over Time

**Epistemic type:** systems consolidation principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_memory_principle`  
**Introduced / developed:** 1950s–present  
**Tags:** `systems-consolidation`, `hippocampus`, `cortex`, `memory`

### Argument & interpretation

New episodic memories depend strongly on hippocampal–cortical interactions, while repeated reactivation can redistribute or transform their representation across neocortical networks. Consolidation is therefore a dynamic reorganization process rather than simple copying to a fixed store.

### Boundary & conditions

- Some detailed or vivid memories may remain hippocampus-dependent.
- Sleep, retrieval, schema, emotion, and interference alter consolidation.
- Standard and multiple-trace accounts disagree on the fate of episodic detail.

### Application

- memory
- sleep
- education
- trauma
- continual-learning architectures

### Basics

Patient H.M. established a distinction between memory systems. Marr, McClelland, McNaughton, O’Reilly, and others developed systems-consolidation and complementary-learning theories.

### Paper / work evidence

- **Foundation (1957):** [Scoville and Milner (1957): Loss of recent memory after bilateral hippocampal lesions](https://doi.org/10.1136/jnnp.20.1.11) · `wrk:3789dc7beea85897dc86`
- **Theory (1995):** [Why there are complementary learning systems in the hippocampus and neocortex](https://doi.org/10.1037/0033-295X.102.3.419) · `wrk:286f7010db86982bd1fe`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:stability-plasticity` — Multiple systems separate rapid plasticity from stable long-term storage.

### Comment

Principia should not equate consolidation with lossless transfer; memory content and abstraction can change during reorganization.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `4d1f30f066a1256a5235ee9e1ffdb0563f71bd2cd6c4c15e913f0cdf6383522a`

---

## `meta:neuroscience-cognition:homeostatic-plasticity` — Neural Circuits Stabilize Activity While Retaining Capacity to Learn

**Epistemic type:** homeostatic plasticity principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `homeostasis`, `synaptic-scaling`, `stability`, `plasticity`

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

- **Foundation (2004):** [Homeostatic Plasticity in the Developing Nervous System](https://doi.org/10.1038/nrn1327) · `wrk:ed7452df80445d6ff24f`
- **Evidence (1998):** [Activity-Dependent Scaling of Quantal Amplitude in Neocortical Neurons](https://doi.org/10.1038/36103) · `wrk:eeb0cfa90f0967c3b9cc`

### Comment

This principle is a root for stability–plasticity trade-offs. A new learning rule should specify how runaway excitation or silence is prevented.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `49e8ce8effbc0846e72f696e3fe65ef00da02bc072c45061f1b6d10af297e828`

---

## `meta:neuroscience-cognition:grid-cell-metric` — Periodic Population Codes Can Provide a Multi-Scale Metric for Position

**Epistemic type:** grid-cell coding observation  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2014_landmark`  
**Introduced / developed:** 2005–present  
**Tags:** `grid-cells`, `entorhinal-cortex`, `periodic-code`, `navigation`

### Argument & interpretation

Grid cells exhibit periodic firing fields arranged in hexagonal lattices. Modules with different spatial scales can jointly encode position efficiently, support path integration, and provide a metric-like basis that can be combined with landmarks and context.

### Boundary & conditions

- Grid regularity varies across environments, species, and behavioral states.
- Periodic codes are ambiguous without multiple modules or external anchoring.
- The causal role in navigation and abstract cognition depends on network and task context.

### Application

- navigation
- path integration
- vector coding
- robotics
- periodic representations

### Basics

Hafting and colleagues discovered grid cells in 2005; the Moser group shared the 2014 Nobel Prize with O’Keefe.

### Paper / work evidence

- **Foundation (2005):** [Microstructure of a spatial map in the entorhinal cortex](https://doi.org/10.1038/nature03721) · `wrk:75cf9061780674823dea`
- **Recognition (2014):** [The Nobel Prize in Physiology or Medicine 2014](https://www.nobelprize.org/prizes/medicine/2014/summary/) · `wrk:97c484a32251a7d76a0c`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:population-coding` — Grid modules form a distributed multi-scale population code.

### Comment

The key Meta-Principle is compositional periodic coding; a simple grid-like pattern in embeddings is not enough to establish a neural navigation mechanism.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `e1c7d96992f131979b9c9c5e65ecc42c63fc10014a9818de1406140ea3b0804f`

---

## `meta:neuroscience-cognition:critical-periods` — Plasticity Is Gated by Developmental Windows and Circuit Maturation

**Epistemic type:** developmental principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `critical-period`, `development`, `plasticity`, `maturation`

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

- **Foundation (1970):** [The Period of Susceptibility to the Physiological Effects of Unilateral Eye Closure in Kittens](https://doi.org/10.1113/jphysiol.1970.sp008455) · `wrk:ab2d1989703df6b38be0`
- **Review (2005):** [Critical Period Plasticity in Local Cortical Circuits](https://doi.org/10.1038/nrn1787) · `wrk:5959576d57f99d94666a`

### Comment

Critical periods should not be generalized into deterministic age deadlines. Principia should state function, evidence, and reversibility.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `ad68b46d42b60dfcc9b2b2cfbbc3c8add693abd6e563ad9b44fabbab9d1bc94a`

---

## `meta:neuroscience-cognition:neural-manifolds` — Population Activity Often Occupies a Low-Dimensional Task-Structured Manifold

**Epistemic type:** neural manifold observation  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `recent_influential_principle`  
**Introduced / developed:** 2000s–present  
**Tags:** `neural-manifold`, `population-dynamics`, `latent-space`, `geometry`

### Argument & interpretation

Although neural populations contain many recorded units, coordinated activity often lies near a lower-dimensional manifold whose geometry reflects latent dynamics, task variables, and behavioral constraints. Learning can alter trajectories within a manifold or reshape the manifold itself.

### Boundary & conditions

- Estimated dimension depends on sampling, noise, timescale, method, and task.
- Low-dimensional activity can coexist with high-dimensional representational capacity.
- A geometric manifold does not by itself identify causal circuit variables.

### Application

- brain–computer interfaces
- motor control
- representation analysis
- population dynamics
- neural decoding

### Basics

Latent-state and dimensionality-reduction methods revealed structured population trajectories; work in motor cortex and systems neuroscience consolidated the neural-manifold framework in the 2010s.

### Paper / work evidence

- **Foundation (2012):** [Neural population dynamics during reaching](https://doi.org/10.1038/nature11129) · `wrk:567a93cff7ccb7ddf109`
- **Refinement (2020):** [The Geometry of Abstraction in the Hippocampus and Prefrontal Cortex](https://doi.org/10.1016/j.cell.2020.09.031) · `wrk:28883c3fae21188d6be6`

### Foundation relations

- `refines` → `meta:neuroscience-cognition:population-coding` — Manifold geometry summarizes coordinated population codes.
- `analogous_to` → `meta:mathematics-logic:structural-abstraction` — Task structure is represented by geometry rather than raw coordinates.

### Comment

Principia should record the dimensionality estimator and task window. Manifold similarity is not automatically mechanistic equivalence.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `90498523646d2bce3afa2896f13399a365d45bd0e5cce152fd0074aae1d92f69`

---

## `meta:neuroscience-cognition:attractor-dynamics` — Recurrent Networks Can Store Stable or Metastable Activity Patterns

**Epistemic type:** attractor principle  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `attractor`, `recurrent-network`, `memory`, `dynamics`

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

- **Foundation (1982):** [Neural Networks and Physical Systems with Emergent Collective Computational Abilities](https://doi.org/10.1073/pnas.79.8.2554) · `wrk:6189a22217a53185f090`
- **Evidence (2006):** [Attractor Dynamics in the Hippocampal Representation of the Local Environment](https://doi.org/10.1126/science.1126092) · `wrk:a995fd825a20e63be497`

### Comment

Principia should require perturbation recovery, recurrence evidence, or dynamical signatures—not merely clustering of neural states.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `598bc013a6f0af9ff8c2c72c8ae1456227c755fe1653571733c1aa92b4f5e180`

---

## `meta:neuroscience-cognition:efficient-coding` — Sensory Systems Adapt Codes to Input Statistics and Resource Constraints

**Epistemic type:** efficient coding hypothesis  
**Principia kind:** `hypothesis`  
**Maturity:** `supported` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `efficient-coding`, `information`, `sensory`, `resource-constraint`

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

- **Foundation (1961):** [Possible Principles Underlying the Transformations of Sensory Messages](https://www.cns.nyu.edu/~eero/NOTES/02-barLow61.pdf) · `wrk:ac16ba245cf4332a73bf`
- **Evidence (1981):** [A Simple Coding Procedure Enhances a Neuron’s Information Capacity](https://doi.org/10.1007/BF00342793) · `wrk:77f4f7172fb1f697b48e`

### Comment

The hypothesis is powerful but flexible. Principia should require a declared input ensemble, resource constraint, and quantitative objective.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `0d2fc4e8ff8350ecb4da125386421d205c7ce936841bb8a5bc72b3ef484198c1`

---

## `meta:neuroscience-cognition:dendritic-computation` — Single Neurons Can Perform Structured Nonlinear Computation Across Dendritic Subunits

**Epistemic type:** dendritic computation principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_neuroscience_consensus`  
**Introduced / developed:** 1990s–present  
**Tags:** `dendrites`, `nonlinearity`, `single-neuron-computation`, `compartments`

### Argument & interpretation

Dendritic branches integrate inputs with local nonlinearities, active conductances, timing dependence, and compartment-specific plasticity. A neuron can therefore behave more like a multi-layer computational unit than a single weighted-sum threshold.

### Boundary & conditions

- Dendritic effects vary by cell type, state, neuromodulation, and location.
- Reduced point-neuron models can remain adequate at some scales.
- In vitro nonlinearities do not automatically establish their contribution to behavior.

### Application

- circuit modeling
- neuromorphic computing
- credit assignment
- sensory integration
- plasticity

### Basics

Cable theory established passive integration; patch-clamp and imaging work from the 1990s onward revealed local dendritic spikes and branch-specific computation.

### Paper / work evidence

- **Foundation (2001):** [Dendritic computation](https://doi.org/10.1146/annurev.neuro.24.1.779) · `wrk:9afbddbf4377fff86ca5`
- **Review (2017):** [Active dendrites and local computations](https://doi.org/10.1038/nrn.2016.169) · `wrk:6848ef772b9b7f1ccc7a`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:integration-segregation` — Dendritic branches segregate and integrate input within one cell.

### Comment

This Principle warns against overmapping artificial nodes to biological neurons and motivates multi-compartment abstractions where evidence warrants them.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `a5c253c9ff20d7d03636c6701e33d74584c0875c03157e1601dcc9204a03d346`

---

## `meta:neuroscience-cognition:sparse-coding` — Sparse Population Activity Can Support Efficient and Separable Representations

**Epistemic type:** coding principle  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `sparse-coding`, `representation`, `energy`, `receptive-fields`

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

- **Foundation (1996):** [Emergence of Simple-Cell Receptive Field Properties by Learning a Sparse Code](https://doi.org/10.1038/381607a0) · `wrk:3d3dd473d1bfe3d0b7f0`
- **Boundary (2011):** [Sparse Coding in Striate and Extrastriate Visual Cortex](https://doi.org/10.1152/jn.00594.2010) · `wrk:a2f384a6cc1dddbbb589`

### Comment

Principia should record the sparsity metric, coding accuracy, energy cost, and task. “Sparse” is not a single property.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `9f3467cf83976cf9ce194ac13fd7c231103e062b250d621e4754d23ab9797e90`

---

## `meta:neuroscience-cognition:excitation-inhibition-balance` — Strong Excitation Can Be Stabilized by Matching Inhibition

**Epistemic type:** network-dynamics principle  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `excitation`, `inhibition`, `balance`, `asynchronous-state`

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

- **Foundation (1996):** [Chaos in Neuronal Networks with Balanced Excitatory and Inhibitory Activity](https://doi.org/10.1126/science.274.5293.1724) · `wrk:f5a43283135efc4b7104`
- **Review (2009):** [The Asynchronous State in Cortical Circuits](https://doi.org/10.1016/j.neuron.2009.08.026) · `wrk:fd30ab5b8e602c82f193`

### Comment

“E/I imbalance” is too vague as an explanation. The currents, conductances, cell classes, and temporal regime must be specified.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `a1f0c2813eb90fc072be50cd7ec33df218666569b4e640fca5614b5c865ec1e5`

---

## `meta:neuroscience-cognition:synaptic-tagging-capture` — Transient Synaptic Tags Can Capture Later Plasticity Resources to Stabilize Memory

**Epistemic type:** synaptic tagging and capture hypothesis  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `medium` · **Review:** `curated_draft`  
**Significance:** `influential_memory_principle`  
**Introduced / developed:** 1997–present  
**Tags:** `synaptic-tagging`, `memory`, `plasticity`, `consolidation`

### Argument & interpretation

Weak activity can set a temporary synaptic tag without producing durable memory, while strong activity triggers plasticity-related products. Tagged synapses can capture those products within a time window, converting transient changes into long-lasting potentiation and linking nearby events.

### Boundary & conditions

- Molecular implementations and time windows differ across circuits and species.
- Behavioral tagging may involve systems beyond local synapses.
- The framework does not explain all forms of memory consolidation.

### Application

- memory consolidation
- spacing effects
- learning schedules
- neuromodulation
- continual learning analogies

### Basics

Frey and Morris proposed synaptic tagging and capture in 1997 based on late-phase long-term potentiation.

### Paper / work evidence

- **Foundation (1997):** [Synaptic tagging and long-term potentiation](https://doi.org/10.1038/385533a0) · `wrk:0945be9c7cf64571e8da`
- **Review (2012):** [Synaptic tagging and capture: from synapses to behavior](https://doi.org/10.1016/j.tins.2011.11.003) · `wrk:259a0ff4121db904eac3`

### Foundation relations

- `refines` → `meta:neuroscience-cognition:hebbian-plasticity` — Tagging explains how selected Hebbian changes become persistent.

### Comment

This Principle gives a temporal-credit mechanism for consolidation, but child links should distinguish synaptic, cellular, and systems-level evidence.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `4ab324449d0d9ebbfead78237312408f274ef45d8bba1b283bca10761f0b875a`

---

## `meta:neuroscience-cognition:population-coding` — Variables Are Often Represented by Distributed Population Activity

**Epistemic type:** coding observation  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `population-coding`, `distributed-representation`, `decoding`, `neural-manifold`

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

- **Foundation (1986):** [Neuronal Population Coding of Movement Direction](https://doi.org/10.1126/science.3749885) · `wrk:8572bf6c7895b063f8f3`
- **Refinement (2006):** [Probabilistic Population Codes and the Exponential Family of Distributions](https://doi.org/10.1371/journal.pcbi.0020092) · `wrk:5b6cb44016d96943723d`

### Comment

A linear decoder can recover information that is not causally used. Intervention and temporal evidence should accompany mechanistic claims.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `6c5e06bd9b974d3071e9fe57bda4430bf0f24d14455e1f576665fce1ca0d1937`

---

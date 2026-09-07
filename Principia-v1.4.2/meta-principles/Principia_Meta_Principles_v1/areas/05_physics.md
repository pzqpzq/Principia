# Physics: Meta-Principles

This file contains 14 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `physics`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:physics:stationary-action — Physical Trajectories Often Extremize an Action Functional

- **Epistemic type:** `variational principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `action`, `variation`, `lagrangian`, `dynamics`

### Argument & interpretation

For many classical and field systems, realized trajectories make the action $S=\int L(q,\dot q,t)\,dt$ stationary, yielding Euler–Lagrange equations. The formulation unifies dynamics, symmetries, constraints, and approximation methods.

### Boundary & conditions

- Stationary does not necessarily mean a minimum.
- Dissipative, stochastic, open, or nonlocal systems may require generalized principles.
- The action and boundary conditions must be physically justified.

### Application

- classical mechanics
- field theory
- optics
- quantum path integrals
- optimal control

### Basics

Maupertuis, Euler, Lagrange, and Hamilton developed variational mechanics from the eighteenth to nineteenth centuries; twentieth-century field theory generalized it.

### Paper / work evidence

- **Foundation:** [Mathematical Methods of Classical Mechanics](https://doi.org/10.1007/978-1-4757-1693-1) (1989)
- **Exposition:** [The Feynman Lectures on Physics, Vol. II, Ch. 19](https://www.feynmanlectures.caltech.edu/II_19.html) (1964)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

The principle is a compact generator of equations, not evidence of teleology. Specific models depend on the chosen degrees of freedom and action.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0b0d5ba0e7e12ef8c90ffaa1377a6cd6c57d5e670c6dad77014958fdeee9b502`</sub>

---

## meta:physics:noether — Continuous Symmetries Generate Conservation Laws

- **Epistemic type:** `Noether theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `noether`, `symmetry`, `conservation`, `currents`

### Argument & interpretation

For a differentiable action invariant under a continuous transformation group, Noether's theorem associates a conserved current or charge. Time translation yields energy conservation, spatial translation momentum, and rotation angular momentum under the relevant assumptions.

### Boundary & conditions

- The theorem requires an action formulation and sufficiently smooth continuous symmetry.
- Open systems, explicit symmetry breaking, anomalies, or boundary fluxes modify conservation.
- Gauge symmetries require careful interpretation of charges and constraints.

### Application

- particle physics
- continuum mechanics
- field theory
- dynamical systems

### Basics

Emmy Noether proved the foundational results in 1918 while clarifying conservation laws in general relativity and variational systems.

### Paper / work evidence

- **Foundation:** [Invariant Variation Problems](https://doi.org/10.1080/00411457108231446) (1918)
- **Exposition:** [Symmetry and the Meaning of Conservation Laws](https://doi.org/10.1073/pnas.93.25.14256) (1996)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

Every conservation claim should identify the symmetry, closed-system boundary, and possible source terms. Apparent nonconservation can signal an omitted environment.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b352d5a47efa49448a7c2cb9e1f2ecd9d336ea2e452325f5063043fd82cce21c`</sub>

---

## meta:physics:special-relativity — The Laws of Physics Are Lorentz Invariant and Light Speed Is Observer-Independent

- **Epistemic type:** `physical principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `relativity`, `lorentz-invariance`, `spacetime`, `light-speed`

### Argument & interpretation

In inertial frames, physical laws take the same Lorentz-covariant form and the invariant interval $ds^2=c^2dt^2-d\mathbf{x}^2$ replaces absolute time and space. Time dilation, length contraction, and mass–energy relations follow.

### Boundary & conditions

- The principle applies locally in general relativity and globally in flat spacetime.
- Accelerated frames and gravity require curved-spacetime treatment.
- Quantum nonlocal correlations do not permit superluminal signalling under standard theory.

### Application

- particle physics
- electrodynamics
- relativistic engineering
- cosmology

### Basics

Einstein formulated special relativity in 1905, building on Lorentz, Poincaré, and Maxwellian electrodynamics; Minkowski recast it geometrically in 1908.

### Paper / work evidence

- **Foundation:** [On the Electrodynamics of Moving Bodies](https://doi.org/10.1002/andp.19053221004) (1905)
- **Geometric refinement:** [Space and Time](https://en.wikisource.org/wiki/Translation:Space_and_Time) (1908)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

Lorentz invariance is extremely well tested but searches for violations continue. Any proposed exception must specify energy scale and frame-dependent observable.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `e334793f6d4bdcd5670c3515d7b4dbaa7ced5215c1130b9a35cc935efc715cae`</sub>

---

## meta:physics:equivalence-principle — Locally, Gravitation Is Indistinguishable from Acceleration

- **Epistemic type:** `equivalence principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `equivalence`, `gravity`, `curvature`, `free-fall`

### Argument & interpretation

Einstein’s equivalence principle relates inertial motion in curved spacetime to locally accelerated frames. In sufficiently small freely falling laboratories, nongravitational physics reduces to special relativity, motivating gravity as spacetime geometry.

### Boundary & conditions

- Tidal effects remain over finite regions and reveal curvature.
- Weak, Einstein, and strong equivalence principles are distinct.
- Alternative metric theories can satisfy some forms and violate others.

### Application

- general relativity
- gravitational experiments
- cosmology
- navigation

### Basics

Einstein developed the principle from 1907 through the 1915–1916 general theory; Eötvös-type experiments and modern clocks have tested universality of free fall.

### Paper / work evidence

- **Foundation:** [The Foundation of the General Theory of Relativity](https://doi.org/10.1002/andp.19163540702) (1916)
- **Review:** [The Confrontation between General Relativity and Experiment](https://doi.org/10.12942/lrr-2014-4) (2014)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

The local qualifier is essential. Treating gravity as removable globally ignores curvature and topology.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c9c4d9ded80a885195932f1e93d7c3ee258b76b1c8fb5bc7ccd1b8739653a9f8`</sub>

---

## meta:physics:quantum-superposition — Quantum States Combine Linearly Until Measurement or Decoherence Selects Outcomes

- **Epistemic type:** `quantum postulate`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `quantum`, `superposition`, `interference`, `decoherence`

### Argument & interpretation

If $|\psi_1\rangle$ and $|\psi_2\rangle$ are allowed states, then normalized linear combinations are also allowed. Interference depends on relative phase, making probability amplitudes rather than classical alternatives the primitive predictive objects.

### Boundary & conditions

- Superposition is representation-dependent and constrained by superselection rules.
- Macroscopic coherence is rapidly suppressed by environmental decoherence.
- Interpretations disagree about the ontology of measurement outcomes while sharing operational predictions.

### Application

- quantum computing
- spectroscopy
- interferometry
- quantum sensing

### Basics

Superposition emerged from wave mechanics and Hilbert-space formulations in the 1920s, especially work by Schrödinger, Heisenberg, Born, and Dirac.

### Paper / work evidence

- **Foundation:** [The Principles of Quantum Mechanics](https://doi.org/10.1093/acprof:oso/9780198520115.001.0001) (1930)
- **Boundary:** [Decoherence, the Measurement Problem, and Interpretations of Quantum Mechanics](https://doi.org/10.1103/RevModPhys.76.1267) (2003)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

Do not translate quantum superposition into an unrestricted metaphor for ordinary uncertainty. Observable interference is the discriminating feature.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `06df9c7c6e78803e7641f8d65430c2ee57b132dd9b02c1a44c8de4064c362bf3`</sub>

---

## meta:physics:uncertainty-principle — Conjugate Observables Have State-Dependent Precision Limits

- **Epistemic type:** `uncertainty relation`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `uncertainty`, `noncommutativity`, `quantum-measurement`, `variance`

### Argument & interpretation

For observables $A$ and $B$, quantum states obey $\Delta A\,\Delta B\geq \frac12|\langle[A,B]\rangle|$. The limit concerns preparation statistics and noncommuting operators, not merely imperfect instruments.

### Boundary & conditions

- The lower bound can vanish for special states or observables even when other uncertainty formulations remain informative.
- Measurement-disturbance relations are distinct from Robertson preparation uncertainty.
- Classical noise must be separated experimentally from quantum variance.

### Application

- quantum metrology
- sensing
- spectroscopy
- quantum information

### Basics

Heisenberg introduced the uncertainty principle in 1927; Kennard and Robertson gave general mathematical inequalities shortly afterward.

### Paper / work evidence

- **Foundation:** [The Physical Content of Quantum Kinematics and Mechanics](https://doi.org/10.1007/BF01397280) (1927)
- **Formalization:** [The Uncertainty Principle](https://doi.org/10.1103/PhysRev.34.163) (1929)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

The principle is often misused as a vague statement that “everything is uncertain.” It is a precise relation tied to operators and states.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3eff6a111b121a77a9102150a1df23f92c524776f9940e0db873ad2a0ed74c8f`</sub>

---

## meta:physics:complementarity — Experimental Arrangements Select Mutually Exclusive Classical Descriptions

- **Epistemic type:** `complementarity principle`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `context-dependent`
- **Review status:** `curated_draft`
- **Tags:** `complementarity`, `measurement`, `wave-particle`, `quantum-foundations`

### Argument & interpretation

Quantum phenomena can require mutually exclusive measurement arrangements—for example, path information versus interference visibility. Complementarity states that no single classical picture exhausts the phenomenon, while all predictions remain encoded in one quantum formalism.

### Boundary & conditions

- Quantitative wave–particle duality relations refine the qualitative principle.
- Complementarity is interpretation-laden and should not substitute for an operational measurement model.
- Joint unsharp measurements can trade rather than absolutely exclude information.

### Application

- quantum foundations
- measurement design
- interferometry
- quantum information

### Basics

Niels Bohr articulated complementarity in 1927–1928 in response to the new quantum mechanics; later experiments and information-theoretic inequalities made parts quantitative.

### Paper / work evidence

- **Foundation:** [The Quantum Postulate and the Recent Development of Atomic Theory](https://doi.org/10.1038/121580a0) (1928)
- **Quantitative refinement:** [Fringe Visibility and Which-Way Information: An Inequality](https://doi.org/10.1103/PhysRevLett.77.2154) (1996)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

Use cautiously outside quantum physics. Apparent conceptual tension in another field is not automatically Bohr complementarity.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `e52ad7cb7a0df7daebe2587dc4a7bc17a1f33dc6392d6f6ad022d8775efefc6f`</sub>

---

## meta:physics:second-law — Entropy of an Isolated Macroscopic System Does Not Decrease

- **Epistemic type:** `thermodynamic law`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `entropy`, `second-law`, `irreversibility`, `thermodynamics`

### Argument & interpretation

For an isolated macroscopic system, entropy change satisfies $\Delta S\geq0$, with equality for reversible idealizations. The law defines an arrow of time, constrains energy conversion, and connects macroscopic irreversibility to overwhelmingly probable microscopic behavior.

### Boundary & conditions

- Fluctuations can produce local or short-time entropy decreases in small systems.
- Open systems can lower internal entropy by exporting entropy.
- Entropy depends on coarse-graining and state variables; gravitational systems require care.

### Application

- thermodynamics
- engines
- statistical mechanics
- information thermodynamics
- biology

### Basics

Clausius and Kelvin formulated the second law in the nineteenth century; Boltzmann and Gibbs supplied statistical interpretations. Fluctuation theorems refined the small-system boundary.

### Paper / work evidence

- **Foundation:** [On the Moving Force of Heat](https://doi.org/10.1002/andp.18501550403) (1850)
- **Refinement:** [Entropy Production Fluctuation Theorem and the Nonequilibrium Work Relation](https://doi.org/10.1103/PhysRevE.60.2721) (1999)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

The law does not forbid local organization or evolution. Claims must include system boundary and entropy flows.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `98f578f6eb3db85f581b2c7ae3c4697326500829922f6d381b64811379a5797e`</sub>

---

## meta:physics:free-energy-minimization — Equilibrium Minimizes the Appropriate Thermodynamic Potential

- **Epistemic type:** `thermodynamic theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `free-energy`, `equilibrium`, `gibbs`, `thermodynamic-potential`

### Argument & interpretation

Under fixed temperature and volume, equilibrium minimizes Helmholtz free energy $F=U-TS$; under fixed temperature and pressure it minimizes Gibbs free energy $G=H-TS$. Chemical and phase equilibria follow from equalized intensive variables and nonpositive spontaneous potential change.

### Boundary & conditions

- The selected potential depends on controlled variables and ensemble.
- Metastable states can persist behind kinetic barriers.
- Driven nonequilibrium steady states need other principles.

### Application

- phase equilibrium
- chemical reactions
- materials
- soft matter
- statistical mechanics

### Basics

Gibbs developed thermodynamic potentials and equilibrium criteria in 1875–1878; statistical mechanics later connected them to partition functions.

### Paper / work evidence

- **Foundation:** [On the Equilibrium of Heterogeneous Substances](https://www.uvm.edu/~jdericks/EEtheory/Gibbs1878.pdf) (1878)
- **Statistical foundation:** [Elementary Principles in Statistical Mechanics](https://archive.org/details/elementaryprinci00gibbrich) (1902)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

Free-energy favorability predicts equilibrium direction, not reaction rate. Principia should connect kinetics separately.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `2901e5d900d0345ac687b074a84508cfad84b4699695963ffaeeeeb2f2ca2ebd`</sub>

---

## meta:physics:fluctuation-dissipation — Equilibrium Fluctuations Encode Linear Response

- **Epistemic type:** `fluctuation-dissipation theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `fluctuation`, `dissipation`, `linear-response`, `correlation`

### Argument & interpretation

Near equilibrium, a system’s linear response to a weak perturbation is related to spontaneous equilibrium correlation functions. Noise and dissipation are therefore two manifestations of the same microscopic dynamics under equilibrium assumptions.

### Boundary & conditions

- The theorem requires equilibrium or controlled generalizations and linear response.
- Strong driving, aging, active matter, or nonlinear response can violate simple forms.
- Measured noise may include external instrumental sources.

### Application

- condensed matter
- electrical noise
- soft matter
- climate response
- biophysics

### Basics

Einstein related diffusion and mobility; Nyquist connected thermal noise and resistance; Kubo developed the general response theory in the 1950s.

### Paper / work evidence

- **Foundation:** [The Fluctuation-Dissipation Theorem](https://doi.org/10.1143/JPSJ.12.570) (1957)
- **Precursor:** [Thermal Agitation of Electric Charge in Conductors](https://doi.org/10.1103/PhysRev.32.110) (1928)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

Applying the theorem outside equilibrium demands a justified effective temperature or generalized relation, not analogy alone.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3141bc19ea690bd26df4645edb99b575c39086911f9e283d7f1486263eeeb809`</sub>

---

## meta:physics:renormalization-universality — Long-Scale Behavior Can Forget Microscopic Details

- **Epistemic type:** `renormalization-group principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `renormalization`, `universality`, `criticality`, `coarse-graining`

### Argument & interpretation

Renormalization tracks how effective parameters change under coarse-graining. Near critical points, flows approach fixed points, and systems with different microscopic constituents share critical exponents and scaling functions when symmetry, dimension, and interaction range match.

### Boundary & conditions

- Universality classes depend on relevant variables; changing symmetry or dimensionality can change behavior.
- Finite size, disorder, long-range forces, and nonequilibrium driving modify scaling.
- Away from critical regimes, microscopic details may remain important.

### Application

- critical phenomena
- field theory
- statistical mechanics
- complex systems
- machine learning theory

### Basics

Wilson and collaborators transformed renormalization into a general theory of critical phenomena in the early 1970s, building on scaling ideas and quantum-field renormalization.

### Paper / work evidence

- **Foundation:** [Renormalization Group and Critical Phenomena. I](https://doi.org/10.1103/PhysRevB.4.3174) (1971)
- **Synthesis:** [The Renormalization Group: Critical Phenomena and the Kondo Problem](https://doi.org/10.1103/RevModPhys.47.773) (1975)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

This is a rigorous foundation for cross-domain similarity only when the relevant variables and fixed-point structure are identified.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `990a180c4be6ce8a5d73a2816c6f789a5cc0c031c498509dbf00c15cabfd6d10`</sub>

---

## meta:physics:spontaneous-symmetry-breaking — Symmetric Laws Can Have Asymmetric Stable States

- **Epistemic type:** `physical mechanism`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `symmetry-breaking`, `order-parameter`, `phase-transition`, `ground-state`

### Argument & interpretation

A system’s equations or energy can be invariant under a symmetry while its chosen ground state is not. Degenerate minima and order parameters produce broken-symmetry phases, collective modes, and phase transitions.

### Boundary & conditions

- Finite systems need not exhibit exact spontaneous breaking without a thermodynamic or appropriate limit.
- Explicit symmetry-breaking fields select states and alter modes.
- Gauge symmetry requires careful language because local gauge redundancy is not broken in the same sense.

### Application

- condensed matter
- particle physics
- phase transitions
- pattern formation

### Basics

Landau used order parameters in phase-transition theory; Nambu, Goldstone, Higgs, and others developed symmetry breaking in quantum field theory in the 1960s.

### Paper / work evidence

- **Foundation:** [Quasi-Particles and Gauge Invariance in the Theory of Superconductivity](https://doi.org/10.1103/PhysRev.117.648) (1960)
- **Refinement:** [Broken Symmetries and the Masses of Gauge Bosons](https://doi.org/10.1103/PhysRevLett.13.508) (1964)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

New Principles should distinguish symmetry of laws, data, solutions, and measurement procedures. Apparent asymmetry can be induced by boundary conditions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `04af187dc6edfc08c49973be155bd90935485f55bc2fd588985be2e01f7b1fa1`</sub>

---

## meta:physics:effective-field-theory — Low-Energy Physics Can Be Organized Without Complete Microscopic Knowledge

- **Epistemic type:** `effective field theory principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `effective-field-theory`, `cutoff`, `power-counting`, `scale`

### Argument & interpretation

At energies below a cutoff $\Lambda$, the most general theory consistent with relevant symmetries is an expansion in local operators suppressed by powers of $E/\Lambda$. Unknown high-energy effects enter through coefficients, enabling controlled approximation and uncertainty estimates.

### Boundary & conditions

- The expansion fails near the cutoff, strong nonlocality, or missing light degrees of freedom.
- Power counting and symmetry assumptions must be stated.
- Matching coefficients can require data or a more fundamental theory.

### Application

- particle physics
- nuclear physics
- condensed matter
- gravity
- multiscale modeling

### Basics

Effective descriptions are old, but Wilsonian renormalization and Weinberg’s 1979 formulation established modern EFT as a systematic method.

### Paper / work evidence

- **Foundation:** [Phenomenological Lagrangians](https://doi.org/10.1016/0370-1573(79)90023-1) (1979)
- **Application:** [The Effective Field Theory Treatment of Quantum Gravity](https://doi.org/10.1063/1.531335) (1994)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

EFT is a model of disciplined scope. Principia should prefer a bounded effective claim over an unsupported universal mechanism.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `cc270681db86da4f5eeafc5d734e1d856b9e308f73fdaea06f6ea08dc42b439d`</sub>

---

## meta:physics:locality-causality — Relativistic Causality Constrains Influence to Light Cones

- **Epistemic type:** `causal structure principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `locality`, `causality`, `light-cone`, `microcausality`

### Argument & interpretation

In relativistic field theory, events outside one another’s light cones cannot exchange causal signals, and local observables at spacelike separation satisfy microcausality conditions. The spacetime metric organizes possible causal order.

### Boundary & conditions

- Quantum entanglement violates classical factorization but does not enable controllable superluminal signalling.
- Curved spacetimes can contain horizons and global causal pathologies.
- Effective nonlocal descriptions may emerge while preserving fundamental signalling limits.

### Application

- field theory
- relativity
- quantum information
- causal modeling

### Basics

Minkowski spacetime and Einstein relativity established light-cone causality; axiomatic quantum field theory formalized locality through commutation relations.

### Paper / work evidence

- **Foundation:** [Space and Time](https://en.wikisource.org/wiki/Translation:Space_and_Time) (1908)
- **Boundary:** [On the Einstein Podolsky Rosen Paradox](https://cds.cern.ch/record/111654/files/vol1p195-200_001.pdf) (1964)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which symmetry, scale, state variables, or approximation regime connects the new Principle to this root?
- What observable would reveal that the stated physical regime has been left?

### Comment

“Nonlocal” is used ambiguously across fields. Principia should distinguish nonlocal correlations, interactions, representations, and signalling.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3e5ff83dbb9a1509e2c1428caaa3125f2d6b41ef3199663b9b9cb3e3a01e7195`</sub>


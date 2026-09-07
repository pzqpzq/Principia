# Quantum Information and Quantum Technologies Meta-Principles

> **Area ID:** `quantum-information`  
> **Records:** 14  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:quantum-information:holevo-bound` — Accessible Classical Information from a Quantum Ensemble Is Bounded by the Holevo Quantity

**Epistemic type:** Holevo theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_information_theorem`  
**Introduced / developed:** 1973–present  
**Tags:** `holevo-bound`, `accessible-information`, `quantum-channel`, `entropy`

### Argument & interpretation

For an ensemble $\{p_x,\rho_x\}$ encoded into quantum states, the mutual information obtainable by any measurement is bounded by $\chi=S(\sum_x p_x\rho_x)-\sum_x p_x S(\rho_x)$. A Hilbert space with many continuous amplitudes does not permit unlimited classical readout from one system.

### Boundary & conditions

- The bound may require collective measurements and many copies to be approached.
- Quantum communication capacity depends additionally on channel noise and coding.
- The theorem bounds classical information, not all operational quantum resources.

### Application

- quantum communication
- channel capacity
- quantum machine learning claims
- cryptography
- measurement design

### Basics

Alexander Holevo established the bound in 1973; it became a central bridge between Shannon and quantum information theory.

### Paper / work evidence

- **Foundation (1973):** [Bounds for the quantity of information transmitted by a quantum communication channel](https://doi.org/10.1007/BF01007415) · `wrk:caf069b2b76f12750b12`
- **Textbook (2000):** [Quantum Computation and Quantum Information](https://doi.org/10.1017/CBO9780511976667) · `wrk:bfe82745a9c2e49991f2`

### Foundation relations

- `specializes` → `meta:information-control-complexity:channel-capacity` — Holevo theory bounds classical information over quantum channels.

### Comment

The Holevo bound is essential when evaluating claims that amplitude encoding alone yields exponential accessible classical information.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `706f64fc1aca9d6cd5fff9eae6385a4f79db1efd5031c5e86fbb2dc844c9df51`

---

## `meta:quantum-information:no-cloning` — An Unknown Quantum State Cannot Be Copied Perfectly by a Universal Physical Operation

**Epistemic type:** no-cloning theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_information_theorem`  
**Introduced / developed:** 1982–present  
**Tags:** `no-cloning`, `quantum-information`, `linearity`, `security`

### Argument & interpretation

Linearity of quantum evolution prevents a single unitary or completely positive map from taking every unknown state $|\psi\rangle$ and a blank state to two perfect copies $|\psi\rangle|\psi\rangle$. Orthogonal states can be copied; arbitrary nonorthogonal states cannot.

### Boundary & conditions

- Known states can be prepared repeatedly.
- Approximate, probabilistic, and state-dependent cloning are possible with bounded fidelity.
- The theorem concerns quantum-state copying, not copying classical descriptions or measurement outcomes.

### Application

- quantum cryptography
- error correction
- teleportation
- quantum networks
- security proofs

### Basics

Wootters and Zurek, and independently Dieks, established no-cloning in 1982.

### Paper / work evidence

- **Foundation (1982):** [A single quantum cannot be cloned](https://doi.org/10.1038/299802a0) · `wrk:195807ac3a8a81654bf9`
- **Independent-Proof (1982):** [Communication by EPR devices](https://doi.org/10.1016/0375-9601(82)90084-6) · `wrk:662f12cda07eb236366b`

### Foundation relations

- `motivates` → `meta:quantum-information:quantum-error-correction` — Error correction must encode information without cloning arbitrary states.
- `generalizes` → `meta:quantum-information:no-broadcasting` — No-broadcasting extends the limit to mixed states.

### Comment

No-cloning does not prevent redundancy through encoded entanglement; quantum error correction works by distributing logical information without making independent copies.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `54e7203cf8f891742c265c0adbfc2251d71d4717eb0c5a95a7da326bfc8bb6a8`

---

## `meta:quantum-information:fault-tolerance-threshold` — Arbitrarily Long Quantum Computation Is Possible Below a Noise Threshold with Sufficient Overhead

**Epistemic type:** fault-tolerance threshold theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_computing_result`  
**Introduced / developed:** 1996–present  
**Tags:** `threshold-theorem`, `fault-tolerance`, `logical-error`, `quantum-computing`

### Argument & interpretation

For suitable local stochastic noise models, error-correcting codes, and fault-tolerant gadgets, if physical error rates lie below a threshold then logical error can be reduced arbitrarily by increasing encoding overhead. The threshold theorem converts quantum computation from analog fragility into a digital fault-tolerance problem.

### Boundary & conditions

- Threshold values depend strongly on architecture, noise correlations, leakage, connectivity, decoder, and operations.
- Below-threshold components do not guarantee an end-to-end useful system.
- Overhead may remain economically or physically prohibitive.

### Application

- quantum computer roadmaps
- logical qubits
- architecture comparison
- error budgets
- resource estimation

### Basics

Aharonov and Ben-Or, Knill–Laflamme–Zurek, Kitaev, and others proved threshold results in the late 1990s.

### Paper / work evidence

- **Foundation (1996):** [Fault-Tolerant Quantum Computation with Constant Error](https://arxiv.org/abs/quant-ph/9611025) · `wrk:9b833323659927bc6a91`
- **Independent-Framework (1998):** [Resilient Quantum Computation](https://doi.org/10.1126/science.279.5349.342) · `wrk:3f522cad6b4e736111a1`

### Foundation relations

- `depends_on` → `meta:quantum-information:quantum-error-correction` — Threshold constructions concatenate or scale error-correcting codes.
- `analogous_to` → `meta:engineering-optimization:redundancy-common-cause` — Redundancy and fault isolation convert component error into system reliability.

### Comment

A quoted “threshold” must always identify the complete noise and architecture model; otherwise comparisons are meaningless.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `db3ce2164b1a06d1d0ec4e411147025df49ed46be9e27b79246c552bc1c85c53`

---

## `meta:quantum-information:quantum-speed-limit` — Energy and State Distinguishability Impose a Minimum Time for Quantum Evolution

**Epistemic type:** quantum speed-limit theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_dynamics_result`  
**Introduced / developed:** 1945–present  
**Tags:** `quantum-speed-limit`, `energy-time`, `control`, `dynamics`

### Argument & interpretation

A quantum system cannot evolve between sufficiently distinguishable states arbitrarily fast. Mandelstam–Tamm and Margolus–Levitin bounds relate the minimum evolution time to energy uncertainty or mean energy above the ground state, creating a resource limit for gates, control, and sensing.

### Boundary & conditions

- Bounds may be loose and depend on the distance measure and Hamiltonian assumptions.
- Open systems, time-dependent control, and many-body dynamics require generalized limits.
- Control hardware and error constraints often dominate theoretical speed limits.

### Application

- quantum gates
- optimal control
- battery charging
- metrology
- many-body dynamics

### Basics

Mandelstam and Tamm derived an uncertainty-based bound in 1945; Margolus and Levitin added an average-energy bound in 1998.

### Paper / work evidence

- **Foundation (1998):** [The maximum speed of dynamical evolution](https://doi.org/10.1016/S0375-9601(98)00129-2) · `wrk:d741862d205d2cddc038`
- **Review (2013):** [Quantum speed limits: from Heisenberg’s uncertainty principle to optimal quantum control](https://doi.org/10.1088/1751-8113/46/5/053001) · `wrk:a9fdc8c20b68cd01c1cd`

### Foundation relations

- `refines` → `meta:physics:uncertainty-principle` — Energy uncertainty constrains evolution speed.
- `analogous_to` → `meta:engineering-optimization:pontryagin-maximum` — Quantum control seeks trajectories near dynamical bounds.

### Comment

The speed limit is a lower bound on ideal evolution time, not a practical clock-rate forecast.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `bb427a1681fc60a7521be858ac25056526a94cb8f75d4937da90781411a3623f`

---

## `meta:quantum-information:macroscopic-quantum-tunneling-circuits` — Engineered Electrical Circuits Can Exhibit Macroscopic Quantum Tunneling and Quantized Energy Levels

**Epistemic type:** macroscopic quantum observation  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2025_landmark`  
**Introduced / developed:** 1980s–present  
**Tags:** `josephson-junction`, `macroscopic-quantum`, `superconducting-circuits`, `nobel-2025`

### Argument & interpretation

A superconducting Josephson circuit with a collective macroscopic phase coordinate can escape a metastable potential through quantum tunneling and exhibit discrete energy levels. Carefully engineered circuits can therefore behave as controllable quantum systems despite involving macroscopically many particles.

### Boundary & conditions

- Quantum behavior requires sufficiently low temperature, low noise, and controlled dissipation.
- Macroscopic refers to collective circuit variables, not immunity to decoherence.
- Specific devices have finite anharmonicity, loss, and readout backaction.

### Application

- superconducting qubits
- quantum sensing
- macroscopic quantum tests
- circuit QED
- quantum control

### Basics

Clarke, Devoret, Martinis, and collaborators established macroscopic quantum tunneling and energy quantization in Josephson circuits; Clarke, Devoret, and Martinis received the 2025 physics prize.

### Paper / work evidence

- **Foundation (1985):** [Experimental tests for the quantum behavior of a macroscopic degree of freedom: The phase difference across a Josephson junction](https://doi.org/10.1103/PhysRevLett.55.1543) · `wrk:464e956fada1046ba42f`
- **Recognition (2025):** [The Nobel Prize in Physics 2025](https://www.nobelprize.org/prizes/physics/2025/summary/) · `wrk:a8ca69b0bf51c44360b6`

### Foundation relations

- `depends_on` → `meta:quantum-information:decoherence-pointer-states` — [bounded_by] Environmental coupling limits observable circuit quantum behavior.
- `specializes` → `meta:physics:quantum-superposition` — Circuit collective modes exhibit discrete quantum levels.

### Comment

The result is a foundation for engineered quantum systems, but device-scale claims still require spectroscopy, coherence, and alternative-classical-model controls.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `ca3a37d7bc393fc28999e119aa30a065447ba238edc171544a8f957c985581af`

---

## `meta:quantum-information:quantum-teleportation` — Entanglement Plus Classical Communication Transfers an Unknown Quantum State Without Sending Its Carrier

**Epistemic type:** quantum communication protocol  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2022_landmark`  
**Introduced / developed:** 1993–present  
**Tags:** `quantum-teleportation`, `entanglement`, `quantum-network`, `nobel-2022`

### Argument & interpretation

Given a shared entangled pair, a joint measurement at the sender and a classical message allow the receiver to reconstruct an unknown input state through a conditional local operation. The original state is destroyed, and classical communication preserves causality.

### Boundary & conditions

- Ideal fidelity requires high-quality entanglement, measurements, and feed-forward.
- Teleportation does not move matter and is not instantaneous.
- Loss, decoherence, and finite entanglement reduce fidelity and rate.

### Application

- quantum networks
- repeaters
- distributed quantum computing
- state transfer
- measurement-based computation

### Basics

Bennett and colleagues proposed quantum teleportation in 1993; experimental advances by Zeilinger and others contributed to the 2022 physics prize.

### Paper / work evidence

- **Foundation (1993):** [Teleporting an Unknown Quantum State via Dual Classical and Einstein-Podolsky-Rosen Channels](https://doi.org/10.1103/PhysRevLett.70.1895) · `wrk:a9b217da00568f5082d1`
- **Recognition (2022):** [The Nobel Prize in Physics 2022](https://www.nobelprize.org/prizes/physics/2022/summary/) · `wrk:4f40eec30a2e34035f86`

### Foundation relations

- `depends_on` → `meta:quantum-information:no-cloning` — The input state is destroyed rather than copied.
- `analogous_to` → `meta:quantum-information:bell-nonlocality` — Both use entanglement, but teleportation does not require Bell-inequality violation as an operational step.

### Comment

Teleportation is a resource-conversion protocol. Its cost includes consumed entanglement and classical bits, which must be counted in system claims.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `3af9ae76b4bb8708538f584661ef14735d0daf2ddd3b96e60761d7aae62396e8`

---

## `meta:quantum-information:decoherence-pointer-states` — Environmental Monitoring Selects Robust Pointer States and Suppresses Observable Superpositions

**Epistemic type:** decoherence mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_classical_transition_principle`  
**Introduced / developed:** 1970s–present  
**Tags:** `decoherence`, `pointer-states`, `open-quantum-systems`, `classicality`

### Argument & interpretation

Interaction with uncontrolled environmental degrees of freedom entangles a system with its surroundings, rapidly suppressing interference between states that imprint distinguishable environmental records. The interaction structure selects comparatively stable pointer states and explains effective classicality without modifying unitary quantum theory.

### Boundary & conditions

- Decoherence does not by itself select one unique measurement outcome.
- Rates and pointer bases depend on the coupling and environment.
- Isolation, error correction, and dynamical decoupling can suppress but not universally eliminate decoherence.

### Application

- quantum computing
- measurement theory
- quantum sensing
- open systems
- classical emergence

### Basics

H. Dieter Zeh and Wojciech Zurek developed environmental decoherence and einselection from the 1970s onward.

### Paper / work evidence

- **Foundation (2003):** [Decoherence, einselection, and the quantum origins of the classical](https://doi.org/10.1103/RevModPhys.75.715) · `wrk:44d38c767ff8c7489d23`
- **Textbook (2002):** [The Theory of Open Quantum Systems](https://doi.org/10.1093/acprof:oso/9780199213900.001.0001) · `wrk:01245858032523713640`

### Foundation relations

- `motivates` → `meta:quantum-information:quantum-error-correction` — Error correction protects information against environmental noise.
- `specializes` → `meta:physics:fluctuation-dissipation` — Decoherence is a central open-system mechanism.

### Comment

Decoherence explains loss of accessible interference under an environment model; it should not be overstated as a complete solution to every interpretational question.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `d6540510b18c84a1321b9bd57a92108afaabc5c0adfc7604b719eb9d3af3c9b1`

---

## `meta:quantum-information:entanglement-area-law` — Low-Energy Quantum States Often Have Entanglement Scaling with Boundary Area Rather Than Volume

**Epistemic type:** many-body entanglement principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_many_body_landmark`  
**Introduced / developed:** 1990s–present  
**Tags:** `area-law`, `entanglement`, `tensor-networks`, `many-body`

### Argument & interpretation

For many ground states of local gapped Hamiltonians, entanglement entropy between a region and its complement scales with the boundary area rather than the region volume. This limited entanglement explains why tensor-network representations can efficiently approximate broad classes of low-energy states.

### Boundary & conditions

- Gapless systems can have logarithmic corrections, and higher-dimensional general theorems are limited.
- Excited, thermal, chaotic, or long-range-interacting states may obey volume laws.
- Small entropy does not automatically imply efficient optimization.

### Application

- tensor networks
- quantum simulation
- condensed matter
- holography
- many-body complexity

### Basics

Black-hole entropy and one-dimensional spin-chain results motivated the area-law program; rigorous and numerical work matured in the 2000s.

### Paper / work evidence

- **Foundation (2010):** [Area laws for the entanglement entropy—A review](https://doi.org/10.1103/RevModPhys.82.277) · `wrk:8cca102bcaaae386f44e`
- **Theorem (2013):** [An area law and sub-exponential algorithm for 1D systems](https://doi.org/10.1109/FOCS.2013.85) · `wrk:4b830d1fb68b1080aaf5`

### Foundation relations

- `specializes` → `meta:foundations:parsimony-mdl` — Limited entanglement makes structured state compression possible.

### Comment

Area-law reasoning should preserve Hamiltonian locality, gap, dimension, and state class. Tensor-network success is conditional on these structures.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `73a5a4672599f58ca61e08af14f654d4e001a43082560f8e726362155e054e81`

---

## `meta:quantum-information:no-broadcasting` — Noncommuting Quantum States Cannot Be Broadcast into Marginals That Both Preserve the Input

**Epistemic type:** no-broadcasting theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_information_theorem`  
**Introduced / developed:** 1996–present  
**Tags:** `no-broadcasting`, `mixed-states`, `noncommutativity`, `quantum-information`

### Argument & interpretation

A set of mixed quantum states can be broadcast to two subsystems with each marginal equal to the input state if and only if the states commute. The theorem identifies noncommutativity, rather than only purity, as the obstruction to classical copying of information.

### Boundary & conditions

- A commuting family behaves classically and can be broadcast.
- Approximate and restricted broadcasting may be possible.
- Correlated outputs are allowed; the impossibility concerns exact preservation of both marginals.

### Application

- quantum information
- resource theories
- quantum Darwinism
- cryptography
- measurement theory

### Basics

Barnum, Caves, Fuchs, Jozsa, and Schumacher proved the no-broadcasting theorem in 1996.

### Paper / work evidence

- **Foundation (1996):** [Noncommuting Mixed States Cannot Be Broadcast](https://doi.org/10.1103/PhysRevLett.76.2818) · `wrk:4bd3c231d178a4c0838e`

### Foundation relations

- `generalizes` → `meta:quantum-information:no-cloning` — No-broadcasting covers mixed-state information and identifies commutativity as the boundary.

### Comment

This is a sharper foundation than generic statements that “quantum information cannot be copied.” The commutativity boundary should be retained.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `0c1886c2a08ec5ac454b11274701fec3ca5db6959c15f6aeed88587a69861a95`

---

## `meta:quantum-information:topological-quantum-computation` — Nonlocal Topological Encoding Can Protect Quantum Information from Local Perturbations

**Epistemic type:** topological quantum computation principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `major_modern_quantum_principle`  
**Introduced / developed:** 1997–present  
**Tags:** `topological-quantum-computing`, `anyons`, `surface-code`, `nonlocal-encoding`

### Argument & interpretation

In topologically ordered systems, logical information can be stored in nonlocal degrees of freedom and manipulated through braiding or code deformations. Local perturbations then have limited ability to distinguish or corrupt the encoded state, providing intrinsic error suppression.

### Boundary & conditions

- Protection is finite at nonzero temperature and in finite systems.
- Creating, controlling, and reading suitable anyons or code states remains difficult.
- Topological protection does not eliminate initialization, measurement, leakage, or control errors.

### Application

- quantum computing
- surface codes
- anyon physics
- fault tolerance
- quantum memories

### Basics

Alexei Kitaev developed toric-code and anyonic computation frameworks in the late 1990s; topological codes now dominate many fault-tolerant roadmaps.

### Paper / work evidence

- **Foundation (2003):** [Fault-tolerant quantum computation by anyons](https://doi.org/10.1016/S0003-4916(02)00018-0) · `wrk:42c65ed3e40457f2260e`
- **Review (2009):** [Topological quantum memory](https://doi.org/10.1088/1367-2630/11/3/033039) · `wrk:3b117eb8bd7571659c06`

### Foundation relations

- `specializes` → `meta:quantum-information:quantum-error-correction` — Topological codes implement quantum error correction through geometric locality.
- `depends_on` → `meta:physics:topological-phases` — The computational protection derives from topological order or code topology.

### Comment

“Topological” is not synonymous with error-free. The actual code distance, temperature, decoder, and control stack determine protection.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `51af4acb936af5770858fc0f32806ad683d1c504180662d2f27a0e41c6b8f299`

---

## `meta:quantum-information:quantum-advantage-validation` — Quantum Advantage Requires an End-to-End Task, Verifiable Benchmark, and Classical Baseline Frontier

**Epistemic type:** benchmarking norm  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `recent_industry_consensus_principle`  
**Introduced / developed:** 2019–present  
**Tags:** `quantum-advantage`, `benchmarking`, `classical-baseline`, `verification`

### Argument & interpretation

A claim of quantum computational advantage must define the task, quality criterion, total quantum resources, verification method, and strongest relevant classical algorithms and hardware. Advantage is a moving comparison frontier rather than a permanent property of one experiment.

### Boundary & conditions

- Sampling demonstrations may not transfer to useful applications.
- Classical simulation algorithms can improve after publication.
- Verification can itself become intractable or rely on assumptions.

### Application

- quantum benchmarking
- roadmaps
- algorithm evaluation
- procurement
- research governance

### Basics

Google’s 2019 random-circuit sampling experiment catalyzed modern advantage claims; rapid classical counteranalysis established the need for evolving baselines and transparent resource accounting.

### Paper / work evidence

- **Foundation (2019):** [Quantum supremacy using a programmable superconducting processor](https://doi.org/10.1038/s41586-019-1666-5) · `wrk:8d10fa88d2c7f3564838`
- **Classical-Challenge (2019):** [Leveraging Secondary Storage to Simulate Deep 54-qubit Sycamore Circuits](https://arxiv.org/abs/1910.09534) · `wrk:7e418ffb77af6f4ac399`

### Foundation relations

- `specializes` → `meta:foundations:measurement-validity` — Advantage depends on a valid, nonleaky benchmark.
- `depends_on` → `meta:computer-science:reduction-completeness` — A durable claim needs evidence about classical difficulty.

### Comment

“Quantum supremacy” or “advantage” should never be a standalone status field. Principia should store task, error tolerance, cost, date, and classical baseline version.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `adefa8dcf46cf09e18e3a8dad3dbed2f082ca372e07b3b06f7a416610e732e5b`

---

## `meta:quantum-information:bell-nonlocality` — Quantum Correlations Can Violate Every Local Hidden-Variable Model

**Epistemic type:** Bell theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2022_foundation`  
**Introduced / developed:** 1964–present  
**Tags:** `bell-theorem`, `nonlocality`, `entanglement`, `nobel-2022`

### Argument & interpretation

Any theory satisfying suitable locality and measurement-independence assumptions obeys Bell inequalities. Quantum mechanics predicts and experiments observe violations, ruling out local hidden-variable explanations of the measured correlations while preserving no-signaling.

### Boundary & conditions

- The conclusion depends on explicit assumptions about locality, settings, and causal structure.
- Violation does not permit faster-than-light communication.
- Device imperfections and postselection can open loopholes unless experiments are designed carefully.

### Application

- quantum foundations
- device-independent cryptography
- randomness certification
- quantum networks
- causal inference

### Basics

John Bell proved the theorem in 1964. Aspect, Clauser, and Zeilinger received the 2022 physics prize for experiments with entanglement, Bell violations, and quantum information.

### Paper / work evidence

- **Foundation (1964):** [On the Einstein Podolsky Rosen Paradox](https://cds.cern.ch/record/111654/files/vol1p195-200_001.pdf) · `wrk:6f5e213779629be74e5e`
- **Recognition (2022):** [The Nobel Prize in Physics 2022](https://www.nobelprize.org/prizes/physics/2022/summary/) · `wrk:4f40eec30a2e34035f86`

### Foundation relations

- `depends_on` → `meta:quantum-information:quantum-teleportation` — Teleportation exploits entanglement without violating no-signaling.
- `depends_on` → `meta:statistics-causality:identifiability` — Bell conclusions require a defined causal model.

### Comment

The Principle excludes local hidden-variable models under stated assumptions; it should not be paraphrased as unconstrained metaphysical “instant influence.”

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `40beadbbcedf06ef1bd565c423f7d2f23e8096c34a55e3f0beb79f8a24583c38`

---

## `meta:quantum-information:quantum-error-correction` — Quantum Information Can Be Protected by Encoding Logical States into Entangled Subspaces

**Epistemic type:** quantum error-correction theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_computing_result`  
**Introduced / developed:** 1995–present  
**Tags:** `quantum-error-correction`, `logical-qubits`, `syndrome`, `fault-tolerance`

### Argument & interpretation

A logical quantum state can be encoded across multiple physical systems so that a specified set of errors maps the code space into distinguishable syndromes without revealing the logical amplitudes. Recovery is possible when the Knill–Laflamme conditions hold.

### Boundary & conditions

- Protection covers only the modeled error set and requires sufficiently accurate syndrome extraction.
- Correlated errors, leakage, drift, and decoder latency can violate assumptions.
- Logical advantage requires overhead that may be very large.

### Application

- fault-tolerant computing
- quantum memories
- quantum communication
- sensing
- error mitigation benchmarks

### Basics

Peter Shor introduced the first quantum error-correcting code in 1995; Steane and the Knill–Laflamme conditions generalized the theory.

### Paper / work evidence

- **Foundation (1995):** [Scheme for reducing decoherence in quantum computer memory](https://doi.org/10.1103/PhysRevA.52.R2493) · `wrk:eae4ad955623f364db30`
- **General-Condition (1997):** [A Theory of Quantum Error-Correcting Codes](https://doi.org/10.1103/PhysRevA.55.900) · `wrk:869fbc38ecf84d0f8cf1`

### Foundation relations

- `supports` → `meta:quantum-information:no-cloning` — [consistent_with] Encoding distributes logical information without making independent copies.
- `motivates` → `meta:quantum-information:fault-tolerance-threshold` — Scalable computation requires error correction below a threshold.

### Comment

Physical error suppression is not the same as logical fault tolerance. Reports should include code distance, decoder, noise model, and full overhead.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `236eccd5cafe4656bb3b31cf8d6f8f7151b85abb305ad9e8518a650ce3997313`

---

## `meta:quantum-information:monogamy-entanglement` — Strong Quantum Entanglement Cannot Be Freely Shared Among Many Parties

**Epistemic type:** entanglement monogamy theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `foundational_quantum_information_result`  
**Introduced / developed:** 2000–present  
**Tags:** `entanglement-monogamy`, `multipartite`, `quantum-correlation`, `security`

### Argument & interpretation

For several entanglement measures, strong bipartite entanglement between two systems limits how much either can be entangled with a third. For three qubits, squared concurrence satisfies a monogamy inequality that partitions pairwise and genuinely tripartite correlations.

### Boundary & conditions

- The exact inequality depends on dimension, state class, and entanglement measure.
- Classical correlations are not monogamous in the same way.
- Multipartite entanglement has structures not reducible to pairwise shares.

### Application

- quantum cryptography
- network routing
- many-body physics
- entanglement distribution
- security proofs

### Basics

Coffman, Kundu, and Wootters formalized three-qubit monogamy in 2000; later work generalized and qualified the concept.

### Paper / work evidence

- **Foundation (2000):** [Distributed entanglement](https://doi.org/10.1103/PhysRevA.61.052306) · `wrk:277084bd33cb94d25b04`
- **Review (2014):** [Entanglement monogamy and the sharing of quantum correlations](https://doi.org/10.1103/RevModPhys.86.419) · `wrk:a87b793103cf955bfbaf`

### Foundation relations

- `supports` → `meta:quantum-information:bell-nonlocality` — Monogamous nonclassical correlations underpin device-independent security.

### Comment

Monogamy is a family of measure-dependent constraints, not a single universal scalar conservation law.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `1c3bfeff5297e963ee686481f47ae42cdefa738aa1566ccb3b2a22b400b450f0`

---

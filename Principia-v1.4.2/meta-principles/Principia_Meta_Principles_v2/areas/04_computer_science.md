# Computer Science and Distributed Systems Meta-Principles

> **Area ID:** `computer-science`  
> **Records:** 22  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:computer-science:relational-data-independence` — A Declarative Data Model Separates Logical Queries from Physical Storage

**Epistemic type:** relational model principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `turing_award_landmark`  
**Introduced / developed:** 1970–present  
**Tags:** `relational-model`, `data-independence`, `declarative-query`, `database`

### Argument & interpretation

The relational model represents data as relations and expresses queries declaratively, allowing the database system to choose physical access paths and execution plans. Logical data independence lets applications survive many storage and indexing changes.

### Boundary & conditions

- Schema changes can still break semantics and applications.
- Relational normalization can conflict with latency or distributed denormalization needs.
- Query optimizers rely on estimates that can fail under skew and correlation.

### Application

- databases
- scientific repositories
- knowledge graphs
- data integration
- Principle storage

### Basics

E. F. Codd introduced the relational model in 1970 and received the 1981 Turing Award. SQL systems made declarative querying and physical independence industry standards.

### Paper / work evidence

- **Foundation (1970):** [A Relational Model of Data for Large Shared Data Banks](https://doi.org/10.1145/362384.362685) · `wrk:36e2085b771d6377d7d1`
- **Refinement (1972):** [Relational Completeness of Data Base Sublanguages](https://www.seas.upenn.edu/~zives/03f/cis550/codd.pdf) · `wrk:98655b50548b628aaf04`

### Foundation relations

- `specializes` → `meta:computer-science:information-hiding` — Logical data independence hides volatile physical storage decisions.

### Comment

Principia’s typed edge and Principle tables benefit from relational integrity even when flexible payloads are stored alongside them.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `84e649a7e7613b1b3912f2c1cf4dcfec210d8ffc84ee36b15f64339380fa9484`

---

## `meta:computer-science:zero-knowledge` — A Prover Can Establish a Statement Without Revealing Its Witness

**Epistemic type:** zero-knowledge proof theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `turing_award_landmark`  
**Introduced / developed:** 1985–present  
**Tags:** `zero-knowledge`, `privacy`, `interactive-proofs`, `verification`

### Argument & interpretation

Interactive or noninteractive protocols can convince a verifier that a statement is true while revealing no knowledge beyond validity, formalized by the existence of a simulator producing an indistinguishable transcript. Soundness, completeness, and zero knowledge are separate guarantees.

### Boundary & conditions

- Definitions depend on computational versus statistical indistinguishability and adversarial models.
- Setup assumptions, Fiat–Shamir transforms, and implementation choices affect security.
- A proof establishes the encoded statement, not the truth of off-chain or external data.

### Application

- privacy-preserving verification
- blockchains
- authentication
- secure computation
- auditable model claims

### Basics

Goldwasser, Micali, and Rackoff introduced zero knowledge in the 1980s. The concept transformed cryptography and was recognized in the 2012 Turing Award to Goldwasser and Micali.

### Paper / work evidence

- **Foundation (1989):** [The Knowledge Complexity of Interactive Proof Systems](https://doi.org/10.1137/0218012) · `wrk:9f00fd5a0c134438d392`
- **Construction (1986):** [How to Prove All NP Statements in Zero-Knowledge and a Methodology of Cryptographic Protocol Design](https://doi.org/10.1007/3-540-47721-7_11) · `wrk:83b0a28ba4ded089b880`

### Foundation relations

- `specializes` → `meta:computer-science:computational-security` — Zero knowledge is defined against explicit computational distinguishers.

### Comment

Principia can use zero-knowledge-style attestations for private validation, but must separate proof of computation from evidence quality.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `823c361c7d1e20fb6653039acd5a316118be0b193f217969bce08cd0c8c69d04`

---

## `meta:computer-science:acid-recovery` — Atomicity and Durability Require Explicit Failure-Recovery Protocols

**Epistemic type:** systems design principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `acid`, `recovery`, `durability`, `logging`

### Argument & interpretation

Transactional atomicity ensures all-or-nothing effects; durability requires committed state to survive declared failures. Logs, checkpoints, shadowing, and replication implement these semantics under specific crash models.

### Boundary & conditions

- Power loss, torn writes, correlated failures, and operator error require model-specific safeguards.
- Durability of bytes does not guarantee semantic validity.
- Distributed atomic commit can block under failures.

### Application

- databases
- file systems
- workflow persistence
- provenance stores

### Basics

Database researchers developed transaction and recovery theory in the 1970s; Härder and Reuter summarized ACID properties in 1983.

### Paper / work evidence

- **Foundation (1983):** [Principles of Transaction-Oriented Database Recovery](https://doi.org/10.1145/289.291) · `wrk:9356f0f3de613c6370b2`
- **Foundation (1978):** [Notes on Data Base Operating Systems](https://doi.org/10.1007/3-540-08755-9_9) · `wrk:6746a98dc4af305aa915`

### Comment

A backup that has never been restored is not demonstrated durability. Recovery procedures must be tested.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `75ad45b9dc86c042a469e38b39a3cc38009cbb25da3ab8722bf96d775b5bfd55`

---

## `meta:computer-science:byzantine-threshold` — Byzantine Agreement Requires Redundancy Relative to Faults

**Epistemic type:** fault-tolerance theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `byzantine`, `fault-tolerance`, `quorum`, `redundancy`

### Argument & interpretation

In the classical unauthenticated synchronous setting, Byzantine agreement requires more than $3f$ participants to tolerate $f$ arbitrary faulty processes. Authentication and timing assumptions change the bounds, but robustness always depends on redundancy and trust structure.

### Boundary & conditions

- The $n>3f$ bound is model-specific.
- Correlated common-mode failures can violate assumptions.
- Authentication does not remove availability or censorship risks.

### Application

- distributed systems
- blockchains
- replicated control
- multi-agent systems

### Basics

Lamport, Shostak, and Pease formalized the Byzantine Generals Problem in 1982.

### Paper / work evidence

- **Foundation (1982):** [The Byzantine Generals Problem](https://doi.org/10.1145/357172.357176) · `wrk:0635c89bdded8402ac62`

### Comment

Majority voting is not automatically Byzantine robust. Record adversary capabilities, quorum rules, and network timing.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `15aef198c5f786f043d7b9f7d0b8007bf1e5f87e403374cf6c729a274f3c71a7`

---

## `meta:computer-science:serializability` — Concurrent Transactions Are Correct When Equivalent to a Serial Execution

**Epistemic type:** database theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `serializability`, `transactions`, `concurrency`, `isolation`

### Argument & interpretation

Serializability requires the effect of concurrent transactions to match some serial order. Conflict graphs, locking, timestamp ordering, and optimistic control provide ways to enforce or test this abstraction.

### Boundary & conditions

- Serializability does not itself guarantee real-time order, durability, or application invariants.
- Snapshot isolation can permit write skew.
- Distributed strict isolation can be expensive.

### Application

- databases
- workflow engines
- financial systems
- scientific state stores

### Basics

Database theory formalized serial schedules in the 1970s; Papadimitriou analyzed serializability in 1979.

### Paper / work evidence

- **Foundation (1979):** [The Serializability of Concurrent Database Updates](https://doi.org/10.1145/322154.322158) · `wrk:993da4971853a0090bee`
- **Refinement (1995):** [A Critique of ANSI SQL Isolation Levels](https://doi.org/10.1145/223784.223785) · `wrk:461314c46a31bee4bce4`

### Comment

A transactional claim should specify isolation level and anomalies excluded. “ACID-compliant” is too coarse.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `654d971ce5670587dad5bd59119da09e386ab24661607eaf06e8b3b6335475df`

---

## `meta:computer-science:eventual-consistency` — Convergence Requires Compatible Updates and Delivery Assumptions

**Epistemic type:** distributed consistency principle  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `eventual-consistency`, `replication`, `crdt`, `convergence`

### Argument & interpretation

Eventual consistency promises replica convergence if updates stop and messages are eventually delivered, but it does not specify intermediate reads or conflict semantics. CRDTs and commutative operations can provide strong convergence.

### Boundary & conditions

- Convergence does not ensure application invariants.
- Permanent partitions or lost updates violate delivery assumptions.
- Last-writer-wins can discard legitimate concurrent intent.

### Application

- offline-first software
- replicated databases
- collaborative tools
- edge systems

### Basics

Eventual consistency emerged in distributed databases; Vogels articulated the operational model in 2009 and CRDT theory formalized convergent data types.

### Paper / work evidence

- **Foundation (2009):** [Eventually Consistent](https://doi.org/10.1145/1435417.1435432) · `wrk:8222cb4b880a8b4d51f0`
- **Refinement (2011):** [A Comprehensive Study of Convergent and Commutative Replicated Data Types](https://hal.inria.fr/inria-00555588) · `wrk:6ae46eb8a83ef68c9e99`

### Comment

A new Principle should name read guarantees and conflict behavior. “Eventually consistent” is not a single semantics.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `459f339d7fde01a620a9bb44e500ffb13081bc5037a99b9f12d141fc39f7c5fc`

---

## `meta:computer-science:flp` — Deterministic Consensus Cannot Guarantee Termination in Pure Asynchrony with One Crash

**Epistemic type:** impossibility theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `flp`, `consensus`, `asynchrony`, `impossibility`

### Argument & interpretation

No deterministic protocol can guarantee consensus termination in a fully asynchronous message-passing system if even one process may crash, despite reliable channels. An adversarial schedule can keep the system bivalent indefinitely.

### Boundary & conditions

- The result does not preclude safety, randomization, partial synchrony, or failure detectors.
- It is a worst-case termination result, not a claim that consensus never works.
- Byzantine faults require different bounds.

### Application

- consensus protocols
- blockchains
- distributed coordination
- multi-agent agreement

### Basics

Fischer, Lynch, and Paterson published the theorem in 1985.

### Paper / work evidence

- **Foundation (1985):** [Impossibility of Distributed Consensus with One Faulty Process](https://doi.org/10.1145/3149.214121) · `wrk:61631cadea7ab7219a7e`

### Comment

A consensus claim should state synchrony, fault, and liveness assumptions. Benign benchmark schedules do not prove worst-case termination.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `032ae8266888c7f8b1cf876c77966dd07581159c8ce01c23086bab97b0051e1b`

---

## `meta:computer-science:fully-homomorphic-encryption` — Encrypted Data Can Support General Computation Without Decryption

**Epistemic type:** fully homomorphic encryption construction principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `godel_prize_landmark`  
**Introduced / developed:** 2009–present  
**Tags:** `fhe`, `encrypted-computation`, `lattices`, `privacy`

### Argument & interpretation

A fully homomorphic encryption scheme allows arbitrary circuits to be evaluated on ciphertexts so that decrypting the result yields the computation on plaintexts. Bootstrapping refreshes noisy ciphertexts, turning limited homomorphism into general encrypted computation.

### Boundary & conditions

- Practical cost, ciphertext expansion, noise growth, and key management remain substantial.
- Security depends on lattice or related hardness assumptions and parameters.
- FHE protects data during computation but not necessarily access patterns, outputs, or compromised endpoints.

### Application

- private cloud computation
- genomics
- financial analytics
- secure inference
- cross-organization validation

### Basics

Craig Gentry gave the first plausible FHE construction in 2009. Later lattice-based schemes made the approach more practical; foundational lattice cryptography received the 2022 Gödel Prize.

### Paper / work evidence

- **Foundation (2009):** [Fully Homomorphic Encryption Using Ideal Lattices](https://doi.org/10.1145/1536414.1536440) · `wrk:0d813e7ebea5bad71330`
- **Refinement (2012):** [(Leveled) Fully Homomorphic Encryption without Bootstrapping](https://doi.org/10.1145/2090236.2090262) · `wrk:124619fbcdc92c68b799`

### Foundation relations

- `refines` → `meta:computer-science:public-key-cryptography` — FHE extends public-key encryption with computation on ciphertexts.

### Comment

FHE is a potential future path for private Principle validation, but v1.4 local-first isolation is much simpler and cheaper.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `feaf826f4c623d7086fa0a0f44784045339b525d5492caefb1969546eed47e4d`

---

## `meta:computer-science:model-checking` — Finite-State System Properties Can Be Verified by Exhaustive Symbolic State Exploration

**Epistemic type:** model checking principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `turing_award_landmark`  
**Introduced / developed:** 1981–present  
**Tags:** `model-checking`, `temporal-logic`, `verification`, `counterexample`

### Argument & interpretation

Given a finite transition system and a temporal-logic property, model checking algorithmically determines whether all relevant executions satisfy the property and can return a counterexample trace. Symbolic representations and abstraction mitigate, but do not eliminate, state explosion.

### Boundary & conditions

- The model may omit real behaviors, timing, environment, or faults.
- Infinite-state and probabilistic systems require specialized abstractions.
- Verification proves the formalized property of the formalized model, not overall system safety.

### Application

- hardware verification
- protocols
- safety-critical software
- workflow validation
- scenario invariants

### Basics

Clarke and Emerson, and independently Queille and Sifakis, developed model checking in the early 1980s. Clarke, Emerson, and Sifakis received the 2007 Turing Award.

### Paper / work evidence

- **Foundation (1981):** [Design and Synthesis of Synchronization Skeletons Using Branching Time Temporal Logic](https://doi.org/10.1007/BFb0025774) · `wrk:e5feead0050aa125b58f`
- **Foundation (1982):** [A Computation Tree Logic and Its Applications](https://doi.org/10.1016/0304-0208(82)90029-9) · `wrk:a183c204ef19a5db7c99`

### Foundation relations

- `depends_on` → `meta:computer-science:computability-boundary` — Model checking gains decidability by restricting the modeled state space.

### Comment

Principia can model-check package and Scenario invariants, while keeping empirical scientific validation separate from software-state verification.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `6f5754c995dd0ab4b4f36be7642d875ec8303076e0fe4908e3384301455ad222`

---

## `meta:computer-science:end-to-end` — Functions Requiring Application Semantics Belong at the Endpoints

**Epistemic type:** systems principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `end-to-end`, `systems`, `layers`, `correctness`

### Argument & interpretation

Lower layers can provide partial reliability or performance, but guarantees such as correct file transfer or transaction intent often require application-level verification at endpoints. Intermediate mechanisms are useful when not mistaken for complete guarantees.

### Boundary & conditions

- Security and performance may require enforcement within lower layers.
- Modern systems can have multiple trust endpoints.
- The principle guides placement; it does not prohibit lower-layer functionality.

### Application

- network architecture
- storage systems
- security
- distributed applications

### Basics

Saltzer, Reed, and Clark articulated end-to-end arguments in 1984.

### Paper / work evidence

- **Foundation (1984):** [End-to-End Arguments in System Design](https://doi.org/10.1145/357401.357402) · `wrk:0dbae1e7a796afc617f0`

### Comment

When a lower-layer metric is used as proof of application correctness, ask which semantic failures remain detectable only at the endpoint.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `917004be500e91865b657eea0689a27fe384f4962ac5dd05bd896fe491b29a78`

---

## `meta:computer-science:information-hiding` — Modules Should Hide Decisions Likely to Change

**Epistemic type:** software-design principle  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `modularity`, `information-hiding`, `interfaces`, `maintainability`

### Argument & interpretation

A robust module exposes a stable contract while concealing volatile representations, algorithms, storage, or policy choices. Decomposing by hidden design decisions reduces change propagation and permits independent replacement.

### Boundary & conditions

- Poorly chosen boundaries can increase communication or duplicate logic.
- Performance-critical systems may require controlled abstraction leaks.
- An interface that hides semantics rather than implementation impedes verification.

### Application

- software architecture
- APIs
- microservices
- scientific pipelines

### Basics

David Parnas formulated information hiding as a modularization criterion in 1972.

### Paper / work evidence

- **Foundation (1972):** [On the Criteria To Be Used in Decomposing Systems into Modules](https://doi.org/10.1145/361598.361623) · `wrk:d8642302cfcb432cd7a4`

### Comment

Principia’s backend–frontend boundary should consume stable contracts rather than infer storage semantics or mutate SQLite directly.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `b0ece59e6bc79b732e3499c64914aa36e5c2d7c9467131d75a0e7dcea5fc8995`

---

## `meta:computer-science:calm` — Monotonic Programs Admit Coordination-Free Distributed Evaluation

**Epistemic type:** CALM theorem  
**Principia kind:** `theorem`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `calm`, `monotonicity`, `coordination`, `distributed-computation`

### Argument & interpretation

The CALM principle connects logical monotonicity to coordination: computations whose conclusions only grow as facts arrive can be implemented without global coordination, whereas retractions generally require knowledge that no conflicting fact remains.

### Boundary & conditions

- The theorem depends on formal computation and consistency models.
- Application invariants can introduce nonmonotonicity.
- Operational resource constraints can still require coordination.

### Application

- distributed databases
- stream processing
- knowledge graphs
- incremental reasoning

### Basics

The idea emerged from Bloom and was formalized in the early 2010s.

### Paper / work evidence

- **Foundation (2011):** [Relational Transducers for Declarative Networking](https://doi.org/10.1145/1989284.1989321) · `wrk:cdcaea5baf3fcceadff8`
- **Synthesis (2019):** [Keeping CALM: When Distributed Consistency Is Easy](https://arxiv.org/abs/1901.01930) · `wrk:b56101c0c39d5de7d985`

### Comment

This root is useful for Principles Cloud synchronization: append-only facts distribute more easily than retractions, which require versions and reconciliation.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `d5e80f93f9020a88fefe281d79b37b51e0371b372880051ab62c93905fd03a3b`

---

## `meta:computer-science:cook-levin-np-completeness` — NP-Completeness Transfers Intractability Through Polynomial Reductions

**Epistemic type:** Cook–Levin theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `turing_level_foundation`  
**Introduced / developed:** 1971–1972  
**Tags:** `np-complete`, `reductions`, `complexity`, `sat`

### Argument & interpretation

Boolean satisfiability is NP-complete: every problem whose solution can be verified in polynomial time can be reduced to SAT in polynomial time. Once one complete problem is known, reductions classify broad families of problems as sharing a common worst-case difficulty barrier.

### Boundary & conditions

- NP-completeness is a worst-case statement and does not preclude efficient algorithms on structured instances.
- The conclusion that no polynomial algorithm exists depends on the unproved assumption $P
e NP$.
- Approximation, parameterization, randomization, or average-case structure can change tractability.

### Application

- complexity classification
- algorithm design
- optimization
- cryptography
- scientific workflow planning

### Basics

Stephen Cook and Leonid Levin independently established NP-completeness in 1971; Karp demonstrated its breadth through 21 polynomial reductions in 1972.

### Paper / work evidence

- **Foundation (1971):** [The Complexity of Theorem-Proving Procedures](https://doi.org/10.1145/800157.805047) · `wrk:0e86585c657197c3611e`
- **Refinement (1972):** [Reducibility Among Combinatorial Problems](https://doi.org/10.1007/978-1-4684-2001-2_9) · `wrk:b974f3b056e42e7c26b9`

### Foundation relations

- `specializes` → `meta:computer-science:reduction-completeness` — Cook–Levin is the canonical completeness result.
- `motivates` → `meta:computer-science:locality` — Hardness motivates exploiting instance structure.

### Comment

Principia should use NP-completeness to motivate approximation or structure exploitation, not as a blanket claim that practical instances cannot be solved.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `105c8cbf29099f7ee0cfef605929d2a244089a9faf6632e0df87ab0fdd123492`

---

## `meta:computer-science:public-key-cryptography` — One-Way Asymmetry Enables Secure Communication Without a Pre-Shared Secret

**Epistemic type:** public-key cryptography principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `turing_award_landmark`  
**Introduced / developed:** 1976–present  
**Tags:** `public-key`, `cryptography`, `one-way-functions`, `signatures`

### Argument & interpretation

A public key can enable encryption or verification while a computationally related private key enables decryption or signing. Security comes from an asymmetry between easy forward computation and infeasible inversion or forgery under a specified hardness assumption.

### Boundary & conditions

- Security is computational and assumption-dependent, not information-theoretic.
- Key generation, authentication, randomness, and implementation side channels remain critical.
- Quantum algorithms threaten widely deployed factoring- and discrete-log-based systems.

### Application

- secure communication
- digital signatures
- identity
- software supply chains
- privacy-preserving science

### Basics

Diffie and Hellman introduced public-key distribution concepts in 1976; Rivest, Shamir, and Adleman gave a practical public-key cryptosystem in 1978. The work received major computing awards including the Turing Award.

### Paper / work evidence

- **Foundation (1976):** [New Directions in Cryptography](https://doi.org/10.1109/TIT.1976.1055638) · `wrk:bc9ea42078965c0a28a6`
- **Construction (1978):** [A Method for Obtaining Digital Signatures and Public-Key Cryptosystems](https://doi.org/10.1145/359340.359342) · `wrk:3e57bdbd3ac1161c30f4`

### Foundation relations

- `specializes` → `meta:computer-science:computational-security` — Public-key security is a reduction to computational hardness.

### Comment

A child Principle must name the exact security notion, adversary, and hardness assumption; “encrypted” alone is not an auditable claim.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `cecc9d5ea12200fbc6ad6678138ae4bfe3f15214f3c332479a3fdd533a8076ea`

---

## `meta:computer-science:cap` — Partitions Force a Choice Between Linearizable Consistency and Availability

**Epistemic type:** distributed-systems theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `cap`, `partitions`, `availability`, `linearizability`

### Argument & interpretation

In an asynchronous distributed system that may partition, a service cannot guarantee both availability for every nonfailed request and linearizable consistency. During a partition it must delay or reject some operations, or return responses that are not globally linearizable.

### Boundary & conditions

- CAP concerns partition periods and specific definitions.
- Causal, session, and eventual consistency provide other choices.
- Latency trade-offs occur even without hard partitions.

### Application

- distributed databases
- cloud services
- replicated state
- edge systems

### Basics

Eric Brewer proposed the conjecture in 2000; Gilbert and Lynch proved a formal version in 2002.

### Paper / work evidence

- **Foundation (2002):** [Brewer’s Conjecture and the Feasibility of Consistent, Available, Partition-Tolerant Web Services](https://doi.org/10.1145/564585.564601) · `wrk:a0ade1f23951291d5973`

### Comment

CAP is often misquoted as “choose any two” at all times. Preserve the formal failure and consistency models.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8e3b7d07417c0813c6ffbf2bd777ce857f8851427fe6406c86f9d1d83ba8d70d`

---

## `meta:computer-science:differential-privacy` — Privacy Can Be Bounded by Limiting How Much One Record Changes an Output Distribution

**Epistemic type:** differential privacy definition and composition theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `godel_turing_level_landmark`  
**Introduced / developed:** 2006–present  
**Tags:** `differential-privacy`, `composition`, `privacy-budget`, `randomization`

### Argument & interpretation

A randomized mechanism is $(arepsilon,\delta)$-differentially private when neighboring datasets induce nearly indistinguishable output distributions. The definition gives a worst-case, composable privacy budget and makes the privacy–accuracy trade-off explicit.

### Boundary & conditions

- The guarantee protects participation effects, not all semantic or group privacy.
- Repeated releases consume privacy budget through composition.
- Poorly chosen adjacency, large $arepsilon$, side information, or nonprivate preprocessing can undermine practical protection.

### Application

- statistics
- federated analytics
- machine learning
- public data release
- private scientific collaboration

### Basics

Dwork, McSherry, Nissim, and Smith introduced differential privacy in 2006; the foundational paper received the 2017 Gödel Prize.

### Paper / work evidence

- **Foundation (2006):** [Calibrating Noise to Sensitivity in Private Data Analysis](https://doi.org/10.1007/11681878_14) · `wrk:07712dcb64ca603593c2`
- **Reference (2014):** [The Algorithmic Foundations of Differential Privacy](https://doi.org/10.1561/0400000042) · `wrk:72410913d298da832ce8`

### Foundation relations

- `depends_on` → `meta:information-control-complexity:data-processing` — Post-processing preserves differential privacy.

### Comment

A private system should publish adjacency, budget accounting, and utility loss; the label “differentially private” is incomplete without parameters and composition context.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `9c3c7902692aaee1940d6be77274ad649d86323569978be0d371b7f0d4ab8a11`

---

## `meta:computer-science:locality` — Programs Run Fast When Active Working Sets Fit Near the Processor

**Epistemic type:** empirical systems principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `locality`, `memory-hierarchy`, `working-set`, `performance`

### Argument & interpretation

Temporal locality reuses recently accessed data; spatial locality accesses nearby data. Memory hierarchies exploit both, and performance degrades when the active working set exceeds a cache or memory tier.

### Boundary & conditions

- Irregular graph, sparse, and streaming workloads may have weak locality.
- Prefetching and reordering can change locality.
- Distributed locality includes network topology and data placement.

### Application

- cache design
- databases
- GPU kernels
- distributed ML

### Basics

Peter Denning’s working-set model connected locality to virtual-memory behavior in the late 1960s.

### Paper / work evidence

- **Foundation (1968):** [The Working Set Model for Program Behavior](https://doi.org/10.1145/363095.363141) · `wrk:a658a2d29d85aaf9147b`
- **Refinement (1970):** [Virtual Memory](https://doi.org/10.1145/356571.356573) · `wrk:9386e392aedb98870421`

### Comment

Algorithmic complexity alone can miss dominant movement costs. Efficiency claims should record bytes moved and locality assumptions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `fdd6fbc9c8ba9267d7d4feadcddae9d190dbe844c430b4dc9459b6243409ac59`

---

## `meta:computer-science:pcp-theorem` — Proofs Can Be Encoded So That Few Random Queries Detect Global Error

**Epistemic type:** PCP theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `fields_turing_level_landmark`  
**Introduced / developed:** 1990s  
**Tags:** `pcp`, `local-verification`, `approximation-hardness`, `proofs`

### Argument & interpretation

Every NP statement has a probabilistically checkable proof that a verifier can test using only logarithmic randomness and a constant number of queried bits. Local testability of a redundant proof yields deep hardness-of-approximation consequences.

### Boundary & conditions

- The theorem concerns specially encoded proofs, not ordinary mathematical manuscripts.
- Constants and construction overhead matter in practice.
- Hardness consequences rely on polynomial-time reductions and worst-case assumptions.

### Application

- hardness of approximation
- coding theory
- property testing
- interactive verification
- delegated computation

### Basics

Arora, Safra, Lund, Motwani, Sudan, and Szegedy established the PCP theorem in the early 1990s. Dinur later gave a combinatorial gap-amplification proof.

### Paper / work evidence

- **Foundation (1998):** [Proof Verification and the Hardness of Approximation Problems](https://doi.org/10.1145/278298.278306) · `wrk:378f3f5f9e83c5c49199`
- **Refinement (2007):** [The PCP Theorem by Gap Amplification](https://doi.org/10.1145/1250790.1250791) · `wrk:42aa12c112b8655a94c8`

### Foundation relations

- `refines` → `meta:computer-science:reduction-completeness` — PCP converts complexity completeness into approximation hardness.

### Comment

The meta lesson is that global correctness can sometimes be certified by a small randomized local view, but only after deliberate redundancy and encoding.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `b9e4a947651163af93f1e456674f4ea226f86e50a1d7ef9f4fabbd564897ec79`

---

## `meta:computer-science:reduction-completeness` — Reductions Transfer Difficulty and Guarantees Between Problems

**Epistemic type:** complexity principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `reductions`, `np-completeness`, `complexity`, `hardness`

### Argument & interpretation

A reduction transforms instances of problem $A$ into problem $B$ while preserving answers. If $A$ is hard and reduces efficiently to $B$, then $B$ is at least as hard; completeness organizes broad classes around representative problems.

### Boundary & conditions

- The reduction type determines what transfers.
- Worst-case hardness does not imply every instance is difficult.
- A reduction can introduce impractical constants or destroy domain structure.

### Application

- algorithm design
- NP-completeness
- cryptography
- verification

### Basics

Cook and Levin independently established NP-completeness of satisfiability in the early 1970s; Karp demonstrated polynomial reductions among many combinatorial problems.

### Paper / work evidence

- **Foundation (1971):** [The Complexity of Theorem-Proving Procedures](https://doi.org/10.1145/800157.805047) · `wrk:0e86585c657197c3611e`
- **Expansion (1972):** [Reducibility Among Combinatorial Problems](https://doi.org/10.1007/978-1-4684-2001-2_9) · `wrk:b974f3b056e42e7c26b9`

### Comment

Principia should record the direction and cost of a reduction. Superficial similarity between tasks is not a complexity reduction.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8f7a308ffec6d90fe06f098289b16b0dd85ebf81df1892e6ebf868d9a69c4074`

---

## `meta:computer-science:computational-security` — Security Is a Reduction Against a Stated Adversary and Resource Bound

**Epistemic type:** cryptographic principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `cryptography`, `security-definition`, `adversary`, `reduction`

### Argument & interpretation

Modern cryptography defines security through games: no adversary within a resource class should distinguish, forge, learn, or bias more than a negligible amount. Proofs reduce a successful attack to breaking an assumed-hard primitive.

### Boundary & conditions

- Security is conditional on adversary model, implementation, key management, randomness, and hardness assumptions.
- Side channels and social attacks can bypass a sound reduction.
- Quantum adversaries change which assumptions remain credible.

### Application

- encryption
- authentication
- secure protocols
- privacy-preserving computation

### Basics

Goldwasser and Micali introduced probabilistic encryption and semantic security in the early 1980s; game-based definitions became standard.

### Paper / work evidence

- **Foundation (1984):** [Probabilistic Encryption](https://doi.org/10.1145/800057.808670) · `wrk:0c123a1afd27c9e4bcbd`
- **Refinement (1997):** [A Concrete Security Treatment of Symmetric Encryption](https://doi.org/10.1109/18.572901) · `wrk:cab9b2f1bac013f3b67d`

### Comment

Never label a system simply “secure.” Store the security notion, adversary powers, reduction, and implementation boundary.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `b90a2d5a8bfc8fb9ba8373d8336df2e2bd89a11d33e9f36eee2fc8266d5dfbae`

---

## `meta:computer-science:amdahl-law` — Serial Fractions Limit Parallel Speedup

**Epistemic type:** performance law  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `amdahl`, `parallelism`, `speedup`, `bottleneck`

### Argument & interpretation

If fraction $s$ of a fixed workload is inherently serial, ideal speedup on $N$ processors is bounded by $S(N)=1/(s+(1-s)/N)$. As $N$ grows, the serial bottleneck dominates.

### Boundary & conditions

- The model neglects communication, contention, scheduling, and memory effects.
- Weak scaling changes the workload with processor count.
- Algorithmic redesign can alter the serial fraction.

### Application

- parallel computing
- GPU systems
- distributed training
- workflow optimization

### Basics

Gene Amdahl articulated the law in 1967; later weak-scaling analyses complemented it.

### Paper / work evidence

- **Foundation (1967):** [Validity of the Single Processor Approach to Achieving Large Scale Computing Capabilities](https://doi.org/10.1145/1465482.1465560) · `wrk:3700d39ac08395330d2d`
- **Refinement (1988):** [Reevaluating Amdahl’s Law](https://doi.org/10.1145/42411.42415) · `wrk:0267c00ca74b66be4251`

### Comment

Kernel-only speedups should not be presented as end-to-end system speedups. Workload and synchronization must be stated.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `1cb9b4e5bfa0465cfde05453994688d708be5c0fbe52b4a24adb32a4fe70248b`

---

## `meta:computer-science:computability-boundary` — Some Well-Posed Computational Questions Are Undecidable

**Epistemic type:** computability theorem family  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `computability`, `undecidability`, `algorithms`, `limits`

### Argument & interpretation

A problem can have an unambiguous mathematical answer for each instance yet admit no algorithm that correctly decides every instance. Computability is therefore a prior boundary on software and agent guarantees, distinct from speed or engineering quality.

### Boundary & conditions

- Undecidability applies to unrestricted problem classes; bounded or structured subclasses can be decidable.
- Heuristics, semi-decision procedures, and interactive proofs can remain useful.
- Physical constraints may make only finite instances relevant, but worst-case growth can still matter.

### Application

- program verification
- automated reasoning
- database queries
- AI self-analysis

### Basics

Church and Turing formalized undecidable decision problems in 1936; reductions extended undecidability across programming-language and mathematical domains.

### Paper / work evidence

- **Foundation (1936):** [On Computable Numbers, with an Application to the Entscheidungsproblem](https://doi.org/10.1112/plms/s2-42.1.230) · `wrk:35c23e48ae4ee58c6700`
- **Co-Foundation (1936):** [An Unsolvable Problem of Elementary Number Theory](https://doi.org/10.2307/2371045) · `wrk:c8e305ebf1e720149b2b`

### Comment

A system claiming universal analysis should first be checked against computability limits. Principia should represent a restriction as part of the Principle, not hide it in implementation notes.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `1308773bdc7c8fde48eb6d2d55bcb6cd73980441d8ea8b136193bda2bbf0ae46`

---

# Artificial Intelligence and Machine Learning Meta-Principles

> **Area ID:** `ai-ml`  
> **Records:** 25  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:ai-ml:robustness-accuracy-tradeoff` — Adversarial Robustness Can Conflict with Standard Accuracy

**Epistemic type:** empirical-theoretical tradeoff  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `adversarial-robustness`, `accuracy`, `tradeoff`, `threat-model`

### Argument & interpretation

Robustness to norm-bounded or structured perturbations can require features different from those maximizing ordinary test accuracy. Under some distributions, no classifier simultaneously attains Bayes-optimal standard and robust risk, creating an explicit trade-off.

### Boundary & conditions

- The trade-off depends on threat model, data distribution, representation, and available robust features.
- Improved data or architecture can move the frontier.
- Norm-bounded robustness may not correspond to semantic or physical perturbations.

### Application

- adversarial ML
- safety
- robust perception
- certification

### Basics

Adversarial examples were highlighted in deep networks in 2013–2015. Tsipras and colleagues formalized distributions exhibiting an accuracy–robustness trade-off; certified defenses study provable regions.

### Paper / work evidence

- **Foundation (2015):** [Explaining and Harnessing Adversarial Examples](https://arxiv.org/abs/1412.6572) · `wrk:358d7889bbe40556ccd1`
- **Formalization (2019):** [Robustness May Be at Odds with Accuracy](https://proceedings.mlr.press/v97/tsipras19a.html) · `wrk:3b403da5d74154252360`

### Comment

A robustness claim is meaningless without threat model and attack budget. Principia should represent robustness as a scoped relation, not one global score.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `8852122947fb072dc1d66934a0c5933f225b798fb8f263fbe5838f2b8274c505`

---

## `meta:ai-ml:temporal-difference-learning` — Bootstrapping Predictions from Subsequent Predictions Enables Online Reinforcement Learning

**Epistemic type:** temporal-difference learning principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `turing_2024_landmark`  
**Introduced / developed:** 1980s–present  
**Tags:** `reinforcement-learning`, `temporal-difference`, `bootstrapping`, `turing-2024`

### Argument & interpretation

Temporal-difference learning updates a value estimate using the difference between successive predictions, for example $\delta_t=r_{t+1}+\gamma V(s_{t+1})-V(s_t)$. It combines Monte Carlo experience with dynamic-programming bootstrapping and supports continual learning before an episode ends.

### Boundary & conditions

- Off-policy bootstrapping with function approximation can diverge.
- Reward definitions and state representations determine what is learned.
- Partial observability, delayed rewards, and nonstationarity complicate convergence.

### Application

- reinforcement learning
- adaptive control
- robotics
- multi-agent systems
- online prediction

### Basics

Sutton and Barto developed temporal-difference and actor–critic foundations from the 1980s onward. ACM awarded them the 2024 Turing Award for the foundations of reinforcement learning.

### Paper / work evidence

- **Foundation (1988):** [Learning to Predict by the Methods of Temporal Differences](https://doi.org/10.1007/BF00115009) · `wrk:3ea8bf5eb212035b9525`
- **Recognition (2024):** [2024 ACM A.M. Turing Award](https://awards.acm.org/award_winners/barto_9471663) · `wrk:04e36b926f6e4f0b4354`

### Foundation relations

- `specializes` → `meta:ai-ml:credit-assignment` — TD error assigns delayed outcomes to preceding predictions.
- `depends_on` → `meta:ai-ml:exploration-exploitation` — Accurate value learning still requires adequate exploration.

### Comment

TD learning is a powerful local update rule, but a Principle derived from it must expose reward semantics, policy dependence, and stability assumptions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `c9a6acd87b4ea49479f26e2dc2c24e7d3ea89b0f0880b7066370f1398db646d6`

---

## `meta:ai-ml:compute-optimal-training` — Compute-Optimal Language-Model Training Scales Parameters and Data Together

**Epistemic type:** empirical scaling law  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `recent_industry_landmark`  
**Introduced / developed:** 2022–present  
**Tags:** `chinchilla`, `compute-optimal`, `scaling-laws`, `language-models`

### Argument & interpretation

For transformer language models within the studied regime, a fixed training-compute budget is used more efficiently when model parameters and training tokens are increased together rather than by making the model very large and leaving it undertrained. The Chinchilla study estimated approximately equal scaling exponents for parameters and tokens.

### Boundary & conditions

- The fitted exponents depend on architecture, optimizer, data distribution, loss definition, and parameter counting.
- Inference cost, memory, data scarcity, and downstream utility can shift the practical optimum.
- The law is empirical and should be refit when the regime or modality changes.

### Application

- LLM training plans
- budget allocation
- model sizing
- dataset planning
- inference-cost planning

### Basics

Hoffmann and colleagues trained more than 400 models in 2022 and showed that a 70B model trained on much more data could outperform substantially larger undertrained models at equal compute.

### Paper / work evidence

- **Foundation (2022):** [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556) · `wrk:f584359f7971694d6554`
- **Refinement (2024):** [Reconciling Kaplan and Chinchilla Scaling Laws](https://arxiv.org/abs/2406.12907) · `wrk:188be78b3f47a8a4d92a`

### Foundation relations

- `refines` → `meta:ai-ml:scaling-laws` — Chinchilla specifies a compute-optimal allocation inside the broader scaling regime.
- `specializes` → `meta:ai-ml:compute-data-model-codesign` — The result quantifies one model–data–compute co-design rule.

### Comment

This Principle refines, rather than replaces, general neural scaling laws. Principia should store the fitted regime and not promote the 20-tokens-per-parameter rule as universal.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `b1737926772284ff4630405471884e9494ed38a141d35ce976960cbdf6e1e3c2`

---

## `meta:ai-ml:calibration` — Confidence Scores Must Be Empirically Calibrated

**Epistemic type:** probabilistic prediction principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `calibration`, `confidence`, `selective-prediction`, `uncertainty`

### Argument & interpretation

A model is calibrated when predictions assigned confidence $p$ are correct about fraction $p$ in the relevant reference class. Calibration is separate from accuracy and ranking; post-hoc temperature scaling can improve calibration without changing class decisions.

### Boundary & conditions

- Calibration can fail under distribution shift or subgroup conditioning.
- A constant base-rate predictor can be calibrated but useless.
- Token probabilities or verbal confidence are not automatically calibrated for answer correctness.

### Application

- decision support
- uncertainty estimation
- selective prediction
- LLM reliability

### Basics

Proper scoring rules and forecast verification are older than machine learning. Guo and colleagues documented miscalibration in modern neural networks in 2017.

### Paper / work evidence

- **Foundation (2017):** [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html) · `wrk:8f9820418d8e01ff9a41`
- **Application (2017):** [Selective Classification for Deep Neural Networks](https://proceedings.neurips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html) · `wrk:c65a541a4bd36aa65fea`

### Comment

Principia should display empirical reliability curves or abstention performance rather than model self-assessment alone.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `f8b6576d5a3e943896bd267942f5e2b2003bb048c133d25e8aa9df0d668a8231`

---

## `meta:ai-ml:lottery-ticket` — Dense Networks Can Contain Sparse Trainable Subnetworks with Competitive Accuracy

**Epistemic type:** lottery ticket hypothesis  
**Principia kind:** `hypothesis`  
**Maturity:** `supported` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `modern_influential_result`  
**Introduced / developed:** 2018–present  
**Tags:** `lottery-ticket`, `sparsity`, `pruning`, `overparameterization`

### Argument & interpretation

A randomly initialized dense neural network can contain a sparse subnetwork that, when trained with a suitable initialization or rewind point, reaches accuracy comparable to the original network in a similar number of updates. The result suggests that overparameterization partly supplies favorable trainable subnetworks.

### Boundary & conditions

- Finding the ticket can require expensive iterative pruning.
- Tickets may not transfer across datasets, architectures, or random initializations.
- The strongest original claim is empirical and has important scale-dependent qualifications.

### Application

- network pruning
- sparse training
- model compression
- optimization analysis
- continual adaptation

### Basics

Frankle and Carbin introduced the Lottery Ticket Hypothesis at ICLR 2019; later work studied rewinding, stability, transfer, and large-scale limitations.

### Paper / work evidence

- **Foundation (2019):** [The Lottery Ticket Hypothesis: Finding Sparse, Trainable Neural Networks](https://openreview.net/forum?id=rJl-b3RcF7) · `wrk:499fa36b9dc3e4658850`
- **Refinement (2019):** [Stabilizing the Lottery Ticket Hypothesis](https://arxiv.org/abs/1903.01611) · `wrk:a2898be8d602683b3275`

### Foundation relations

- `analogous_to` → `meta:ai-ml:implicit-regularization` — Optimization and pruning select special solutions among many possible subnetworks.

### Comment

Treat “winning tickets” as a family of sparsity phenomena, not proof that every model contains a readily discoverable universal sparse core.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `8051c4920185120420c432bc783d6870a26046f49600b3b446c8ae0b59ad5df7`

---

## `meta:ai-ml:distribution-shift` — Empirical Risk Minimization Guarantees Only the Training Distribution

**Epistemic type:** generalization boundary  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `distribution-shift`, `ood`, `deployment`, `domain-adaptation`

### Argument & interpretation

Minimizing average loss on samples from distribution $P_{train}$ directly targets risk under that distribution. Performance under $P_{test}\neq P_{train}$ requires assumptions about covariate, label, concept, causal, or support shift; without restrictions, out-of-distribution generalization is impossible.

### Boundary & conditions

- Some shifts are correctable with reweighting or invariant mechanisms.
- Test sets drawn from the same pipeline can underestimate deployment shift.
- Robust optimization can trade average accuracy for worst-case protection but depends on the uncertainty set.

### Application

- deployment
- domain adaptation
- continual learning
- scientific transfer
- safety

### Basics

Dataset shift was studied in statistics and pattern recognition; domain-adaptation theory and modern OOD benchmarks made assumptions and impossibility results explicit.

### Paper / work evidence

- **Foundation (2009):** [Dataset Shift in Machine Learning](https://mitpress.mit.edu/9780262170055/dataset-shift-in-machine-learning/) · `wrk:e7c973bf2a59449c48c4`
- **Evaluation (2021):** [In Search of Lost Domain Generalization](https://arxiv.org/abs/2007.01434) · `wrk:2633c3fe7f4d3c70aa75`

### Comment

Any ‘general’ AI Principle should name its environment family. Principia should not infer robustness from IID benchmark performance.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `c16fe2788800624436eb50ce968983f4fa7b34803c9c417217f87defc60c802c`

---

## `meta:ai-ml:energy-based-associative-learning` — Energy Landscapes Can Store Patterns and Learn Structured Probability Distributions

**Epistemic type:** energy-based learning principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2024_landmark`  
**Introduced / developed:** 1982–1985  
**Tags:** `hopfield`, `boltzmann-machine`, `energy-based`, `nobel-2024`

### Argument & interpretation

Hopfield networks encode memories as attractors of an energy function, while Boltzmann machines learn probability distributions by adjusting symmetric interactions to lower the energy of observed configurations. The common Principle is that global computation can emerge from local updates on an energy landscape.

### Boundary & conditions

- Symmetric energy-based models can be difficult to train and mix slowly.
- Associative capacity is finite and degrades with correlated patterns or noise.
- Modern neural networks often use non-equilibrium or asymmetric dynamics outside this framework.

### Application

- associative memory
- energy-based models
- optimization
- generative learning
- neuroscience-inspired AI

### Basics

Hopfield’s 1982 model connected neural memory to statistical physics. Hinton and collaborators developed Boltzmann machines in the mid-1980s; the work was recognized by the 2024 Nobel Prize in Physics.

### Paper / work evidence

- **Foundation (1982):** [Neural networks and physical systems with emergent collective computational abilities](https://doi.org/10.1073/pnas.79.8.2554) · `wrk:6189a22217a53185f090`
- **Foundation (1985):** [A Learning Algorithm for Boltzmann Machines](https://doi.org/10.1207/s15516709cog0901_7) · `wrk:22cff5e4c3ae52c8c34c`
- **Recognition (2024):** [Nobel Prize in Physics 2024](https://www.nobelprize.org/prizes/physics/2024/summary/) · `wrk:58eac9b605944345fd56`

### Foundation relations

- `specializes` → `meta:neuroscience-cognition:attractor-dynamics` — Hopfield memory is an attractor-network implementation.
- `analogous_to` → `meta:physics:free-energy-minimization` — Learning uses an engineered energy function rather than thermodynamic equilibrium directly.

### Comment

The award establishes historical influence, not universal superiority of energy-based models. Child Principles should specify energy, dynamics, and convergence conditions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `b972cd393afaa609bbc225f113db7143ddf129924d1ca158233a6a504daf12c4`

---

## `meta:ai-ml:bitter-lesson` — General Methods That Exploit Growing Computation Tend to Outlast Hand-Coded Domain Structure

**Epistemic type:** industry heuristic  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `medium` · **Review:** `curated_draft`  
**Significance:** `influential_industry_consensus`  
**Introduced / developed:** 2019–present  
**Tags:** `bitter-lesson`, `compute`, `general-methods`, `research-strategy`

### Argument & interpretation

Across several AI subfields, methods that scale search and learning with computation have repeatedly displaced systems built around extensive human-engineered representations. The durable design lesson is to encode domain structure only where it complements, rather than blocks, scalable learning and search.

### Boundary & conditions

- The claim is historical and strategic, not a theorem.
- Data, compute, safety, and physical constraints can make domain knowledge indispensable.
- General methods can inherit hidden human structure through objectives, datasets, architectures, and evaluation.

### Application

- AI research strategy
- architecture design
- robotics
- planning
- scientific agents

### Basics

Richard Sutton articulated “The Bitter Lesson” in 2019 based on the history of chess, Go, speech recognition, and computer vision. It has become a widely cited AI research heuristic.

### Paper / work evidence

- **Foundation (2019):** [The Bitter Lesson](https://www.incompleteideas.net/IncIdeas/BitterLesson.html) · `wrk:24e47b2ccf1324a3a393`
- **Illustration (2017):** [Mastering the game of Go without human knowledge](https://doi.org/10.1038/nature24270) · `wrk:0fdaeecd546407421d8b`

### Foundation relations

- `contradicts` → `meta:ai-ml:inductive-bias` — The Bitter Lesson warns against rigid handcrafted bias, while learning still requires some inductive bias.
- `depends_on` → `meta:ai-ml:compute-data-model-codesign` — General methods benefit only when scalable compute and data are available.

### Comment

The heuristic should not be used to dismiss scientific priors automatically. Principia can represent it as a strategic default whose boundary is the value and cost of explicit structure.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `32e65d7a8dc08faf62d77227fd5b16ba338a03807bcf220253c51a06e66de95b`

---

## `meta:ai-ml:grokking` — Generalization Can Emerge Long After Memorization Under Continued Optimization

**Epistemic type:** delayed-generalization observation  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `recent_influential_observation`  
**Introduced / developed:** 2021–present  
**Tags:** `grokking`, `delayed-generalization`, `training-dynamics`, `memorization`

### Argument & interpretation

In some algorithmic and structured tasks, a network first reaches near-zero training error by memorization and only much later transitions to a simpler rule that generalizes. Weight decay, data fraction, representation structure, and optimization timescale influence this delayed generalization or “grokking.”

### Boundary & conditions

- The phenomenon is not universal and is easiest to observe in controlled tasks.
- Delayed improvement can be hidden or altered by early stopping, data scale, or optimizer choice.
- Mechanistic explanations remain active research and may differ across settings.

### Application

- training dynamics
- algorithmic reasoning
- mechanistic interpretability
- curriculum design
- regularization

### Basics

Power and colleagues named the phenomenon in 2021/2022 while training transformers on modular arithmetic. Later work connected it to representation circuits, regularization, and phase-like transitions.

### Paper / work evidence

- **Foundation (2022):** [Grokking: Generalization Beyond Overfitting on Small Algorithmic Datasets](https://arxiv.org/abs/2201.02177) · `wrk:428f0fe6025e9a0184e2`
- **Refinement (2023):** [Progress Measures for Grokking via Mechanistic Interpretability](https://arxiv.org/abs/2301.05217) · `wrk:33dbb509485a8edab435`

### Foundation relations

- `analogous_to` → `meta:ai-ml:double-descent` — Both show non-classical generalization behavior after interpolation.
- `depends_on` → `meta:ai-ml:implicit-regularization` — Optimization bias can favor a later simpler solution.

### Comment

Grokking should be treated as a conditional training-dynamics Principle, not evidence that arbitrary overfit models will eventually become general.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `58c511976b9cf5b03a798ca2052c9fd05c203f260a321bf6fce19717e56b8a9b`

---

## `meta:ai-ml:capacity-generalization` — Generalization Depends on Capacity Relative to Data and Margin

**Epistemic type:** statistical learning theorem family  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `pac`, `vc-dimension`, `capacity`, `sample-complexity`

### Argument & interpretation

PAC and VC theory bound generalization error using sample size, hypothesis-class capacity, confidence, and empirical fit. A schematic bound has form $R(h)\lesssim \hat R(h)+O(\!\sqrt{(C+\log(1/\delta))/n})$, though modern overparameterized systems require data-dependent notions such as margin, norm, stability, or compression.

### Boundary & conditions

- Worst-case bounds can be numerically loose.
- Parameter count alone is not an adequate capacity measure for modern networks.
- IID assumptions and fixed hypothesis classes may fail under adaptive data collection.

### Application

- model selection
- sample complexity
- benchmark interpretation
- active learning

### Basics

Vapnik and Chervonenkis introduced capacity-based uniform convergence in the 1960s and 1970s; Valiant formulated PAC learning in 1984.

### Paper / work evidence

- **Foundation (1971):** [On the Uniform Convergence of Relative Frequencies of Events to Their Probabilities](https://doi.org/10.1137/1116025) · `wrk:609622be1e350cee529c`
- **Refinement (1984):** [A Theory of the Learnable](https://doi.org/10.1145/1968.1972) · `wrk:67d229aa2f6fccced6c4`

### Comment

A paper-level Principle about generalization should state which complexity measure and sampling assumptions apply rather than cite ‘more data’ abstractly.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `d252300c2e6263eb76fd7b2ad1cec369f1f4c828d482da57aa17c186629f34c5`

---

## `meta:ai-ml:inductive-bias` — Generalization Requires Inductive Bias

**Epistemic type:** learning-theoretic proposition  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `inductive-bias`, `generalization`, `priors`, `architecture`

### Argument & interpretation

Finite training data do not determine behavior on unseen inputs. A learner generalizes only by preferring some functions, representations, or update paths over others through architecture, regularization, data augmentation, pretraining, priors, or optimization. The relevant question is not whether bias exists, but whether it matches the target environment.

### Boundary & conditions

- A bias beneficial in one task family can be harmful under another distribution.
- Large data can reduce but not eliminate assumptions about sampling, representation, and loss.
- Implicit biases may be difficult to state and can change with optimizer or parameterization.

### Application

- architecture design
- transfer learning
- scientific machine learning
- foundation models
- few-shot learning

### Basics

Inductive bias is implicit in classical statistical learning and was emphasized in machine learning by Mitchell and others. No-Free-Lunch results formalized why unrestricted universal superiority is impossible.

### Paper / work evidence

- **Foundation (1980):** [The Need for Biases in Learning Generalizations](https://www.cs.cmu.edu/~tom/pubs/NeedForBias_1980.pdf) · `wrk:d1e218ab20bd32127caf`
- **Formal Boundary (1997):** [No Free Lunch Theorems for Optimization](https://doi.org/10.1109/4235.585893) · `wrk:185fdd60d1f95b046875`

### Comment

New AI Principles should expose the task family they favor. Describing a method as ‘general’ without its bias and environment is scientifically incomplete.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `e1d182b6b06a48b0963a8a39d27486f74aca1748f0c75293605fb9bed4406925`

---

## `meta:ai-ml:test-time-compute` — Inference-Time Search Can Trade Additional Compute for Better Answers

**Epistemic type:** recent empirical scaling principle  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `context-dependent` · **Review:** `curated_draft`  
**Significance:** `recent_frontier`  
**Introduced / developed:** 2024–present  
**Tags:** `test-time-compute`, `search`, `verification`, `reasoning`

### Argument & interpretation

For tasks where candidate solutions can be generated, evaluated, or revised, allocating more inference-time computation through sampling, search, verification, or iterative refinement can improve performance and sometimes outperform parameter scaling at a fixed resource level. Gains depend on the quality of the proposal distribution and verifier.

### Boundary & conditions

- More tokens do not guarantee better reasoning and can amplify correlated errors.
- The optimal allocation varies by problem difficulty, model, verifier, latency, and budget.
- Benchmark gains may rely on answer checkers unavailable in open-ended settings.

### Application

- reasoning models
- agent search
- best-of-N
- self-consistency
- adaptive inference

### Basics

A broad 2024 research line quantified test-time compute allocation for language-model reasoning and renewed interest in inference-time scaling as a distinct axis from pretraining scale.

### Paper / work evidence

- **Foundation (2024):** [Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314) · `wrk:43b26221a80785504dc6`
- **Support (2023):** [Let’s Verify Step by Step](https://arxiv.org/abs/2305.20050) · `wrk:4515be36a52f7b8bec1d`

### Foundation relations

- `specializes` → `meta:ai-ml:exploration-exploitation` — Inference-time search allocates compute between exploration and exploitation.
- `depends_on` → `meta:computer-science:amdahl-law` — Serial verification and generation costs bound practical speedup.

### Comment

Principia should express this as a conditional compute–accuracy trade-off, not a law that longer chains are intrinsically more truthful.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `7695bdacf100bd18330e045043a019c5005d6950665e22236ee199c04fc7d715`

---

## `meta:ai-ml:neural-tangent-kernel` — Infinite-Width Networks Approach Kernel-Like Lazy Training Dynamics

**Epistemic type:** neural tangent kernel limit theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `modern_theoretical_landmark`  
**Introduced / developed:** 2018–present  
**Tags:** `ntk`, `infinite-width`, `kernel`, `lazy-training`

### Argument & interpretation

Under suitable parameterization and infinite-width limits, gradient training of a neural network can be approximated by kernel regression with a nearly fixed neural tangent kernel. This supplies analyzable convergence and generalization predictions for a lazy regime in which features change little.

### Boundary & conditions

- Finite networks can enter rich feature-learning regimes outside the NTK approximation.
- The limit depends on parameterization, width, initialization, and training time.
- Kernel equivalence does not explain all representation learning in practical deep networks.

### Application

- deep-learning theory
- optimization
- generalization
- initialization
- architecture analysis

### Basics

Jacot, Gabriel, and Hongler introduced the NTK in 2018. Subsequent theory clarified convergence, finite-width corrections, and the boundary between lazy and feature-learning regimes.

### Paper / work evidence

- **Foundation (2018):** [Neural Tangent Kernel: Convergence and Generalization in Neural Networks](https://arxiv.org/abs/1806.07572) · `wrk:46a84ee101e69ce7ccd9`
- **Refinement (2019):** [On Lazy Training in Differentiable Programming](https://arxiv.org/abs/1812.07956) · `wrk:70a371d5e4f38b7cc55f`

### Foundation relations

- `refines` → `meta:ai-ml:capacity-generalization` — NTK provides one data-dependent capacity and dynamics model.
- `depends_on` → `meta:ai-ml:implicit-regularization` — Kernel gradient dynamics impose a particular solution bias.

### Comment

Principia should link NTK-based child claims only when the training regime is demonstrably close to the relevant width and movement assumptions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `0c40df58c875821afd54e45c642fe5d462276d5ef84f1a20e718c59f93d2bb9a`

---

## `meta:ai-ml:double-descent` — Interpolation Can Enter a Second Generalization Regime

**Epistemic type:** empirical-theoretical observation  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `double-descent`, `interpolation`, `overparameterization`, `risk`

### Argument & interpretation

As model capacity crosses the interpolation threshold, test risk can peak and then decrease again, producing a double-descent curve. Overparameterization can enable solutions selected by optimization bias that fit training data yet remain simple in a norm, margin, or representation sense.

### Boundary & conditions

- The shape depends on noise, regularization, parameterization, optimizer, and data geometry.
- Double descent does not imply that larger models always improve.
- Interpolation can amplify label noise, spurious features, or distribution shift.

### Application

- deep learning scaling
- model selection
- interpolation
- kernel methods

### Basics

Belkin and collaborators named and synthesized the modern double-descent phenomenon in 2019, connecting classical interpolation results with deep learning observations.

### Paper / work evidence

- **Foundation (2019):** [Reconciling Modern Machine-Learning Practice and the Classical Bias–Variance Trade-Off](https://doi.org/10.1073/pnas.1903070116) · `wrk:1d7bb976c324f58f9da7`
- **Empirical Refinement (2019):** [Deep Double Descent](https://arxiv.org/abs/1912.02292) · `wrk:558dd1bfd7bb40821240`

### Comment

This principle refines rather than refutes bias–variance reasoning. New claims should locate the interpolation threshold and compare compute- and data-matched alternatives.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `2e5e062a453b67bf8c03068cfb128e0379a374412ff9806998e6c251fb51e923`

---

## `meta:ai-ml:exploration-exploitation` — Learning Agents Must Trade Immediate Reward Against Information Gain

**Epistemic type:** sequential decision principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `exploration`, `exploitation`, `bandits`, `active-learning`

### Argument & interpretation

In unknown environments, selecting the currently best action can prevent discovery of better alternatives, while excessive exploration sacrifices reward. Bandit and reinforcement-learning methods balance exploitation and uncertainty reduction using optimism, posterior sampling, or explicit information value.

### Boundary & conditions

- Optimal trade-offs depend on horizon, stationarity, feedback delay, and safety constraints.
- Exploration can be unethical or dangerous in high-stakes systems.
- Nonstationary and strategic environments require continual adaptation.

### Application

- reinforcement learning
- active experimentation
- adaptive trials
- scientific discovery agents

### Basics

The multi-armed bandit formalized the dilemma in twentieth-century sequential analysis. Dynamic programming, Gittins indices, UCB, and Thompson sampling provided principled strategies.

### Paper / work evidence

- **Foundation (1985):** [Asymptotically Efficient Adaptive Allocation Rules](https://doi.org/10.2307/1427277) · `wrk:89d411f7bd3438734deb`
- **Refinement (2002):** [Finite-Time Analysis of the Multiarmed Bandit Problem](https://doi.org/10.1023/A:1013689704352) · `wrk:7ffac633a51da59cd74e`

### Comment

Principia should treat literature search, experiment choice, and model calls as budgeted actions. ‘Try more ideas’ is not a strategy unless information value is modeled.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `02b6f76c37a678a814d6f08b49268135a36c3527571a5a87beea9f0d531d9748`

---

## `meta:ai-ml:credit-assignment` — Learning Requires Assigning Outcomes to Responsible Internal Decisions

**Epistemic type:** computational principle  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `credit-assignment`, `backpropagation`, `gradients`, `reinforcement-learning`

### Argument & interpretation

In layered or sequential systems, a global loss must be attributed to parameters and earlier actions. Backpropagation applies the chain rule to compute gradients efficiently; temporal-difference and policy-gradient methods address delayed rewards. Credit assignment determines what is learned from success or failure.

### Boundary & conditions

- Gradient credit requires differentiability or estimators and can suffer vanishing, explosion, or high variance.
- Correlated internal activations do not uniquely identify causal responsibility.
- Local learning rules and biological mechanisms may differ from exact backpropagation.

### Application

- deep learning
- reinforcement learning
- multi-agent systems
- neuroscience-inspired AI

### Basics

Reverse-mode differentiation has roots in control and numerical analysis. Rumelhart, Hinton, and Williams popularized backpropagation for neural networks in 1986; reinforcement learning developed complementary temporal methods.

### Paper / work evidence

- **Foundation (1986):** [Learning Representations by Back-Propagating Errors](https://doi.org/10.1038/323533a0) · `wrk:3bb577bb6aca043541d6`
- **Sequential Refinement (2000):** [Policy Gradient Methods for Reinforcement Learning with Function Approximation](https://proceedings.neurips.cc/paper/1999/hash/464d828b85b0bed98e80ade0a5c43b0f-Abstract.html) · `wrk:aedcf3ed76a8ffe7218a`

### Comment

A paper-level Principle should distinguish optimization credit from causal explanation. A gradient says how the implemented loss changes locally, not why a feature is scientifically responsible.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `9718a654b1b85c37d6d2f49d43fa4adbd35f130c471fe51ec495d38787fa757c`

---

## `meta:ai-ml:data-quality-ceiling` — Model Performance Is Bounded by the Information and Biases in Its Data

**Epistemic type:** empirical principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `data-quality`, `sampling-bias`, `labels`, `coverage`

### Argument & interpretation

Learning systems cannot reliably recover distinctions absent from observations, and they inherit label error, selection bias, temporal leakage, coverage gaps, and social or measurement biases. More parameters or optimization cannot create missing counterfactual evidence.

### Boundary & conditions

- Strong priors, simulations, transfer, or active data collection can supplement a weak dataset.
- Noisy labels may still permit learning when noise is structured or redundant.
- Data quality is task-dependent; one dataset can be poor for causality yet useful for prediction.

### Application

- dataset design
- foundation models
- medical AI
- industrial ML
- fairness

### Basics

Statistical sampling theory long established dependence on data design. Dataset documentation, datasheets, and data-centric AI made source and governance constraints explicit for modern ML.

### Paper / work evidence

- **Foundation (2021):** [Datasheets for Datasets](https://doi.org/10.1145/3458723) · `wrk:a5cb0f50facb0fb93974`
- **Application (2021):** [Data Cascades in High-Stakes AI](https://doi.org/10.1145/3411764.3445518) · `wrk:d563731311ad382303a2`

### Comment

Principia should link model claims to dataset generation and exclusions. A larger model does not erase an unobserved population or an invalid endpoint.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `ab4bef05ade63fb3bddfdfc90fe1c4873f5339a537a519937d2d3016d3bc7d5a`

---

## `meta:ai-ml:compute-data-model-codesign` — Model, Data, and Compute Must Be Co-Designed Under a Budget

**Epistemic type:** engineering observation  
**Principia kind:** `heuristic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `compute`, `data`, `model-size`, `codesign`

### Argument & interpretation

For a fixed training or inference budget, performance depends on how capacity, data quantity and quality, optimization steps, precision, and deployment cost are allocated. Increasing one dimension while starving another can waste compute or induce overfitting.

### Boundary & conditions

- Optimal allocation is workload- and hardware-dependent.
- Training-optimal scale may be inference-inefficient.
- Capabilities and risks do not necessarily scale smoothly with loss.

### Application

- LLM training
- edge AI
- model compression
- system architecture
- research planning

### Basics

Scaling-law work quantified model/data/compute frontiers; systems research added memory, communication, and inference constraints. Compute-optimal prescriptions have evolved as regimes changed.

### Paper / work evidence

- **Foundation (2022):** [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556) · `wrk:f584359f7971694d6554`
- **Foundation (2017):** [Deep Learning Scaling Is Predictable, Empirically](https://arxiv.org/abs/1712.00409) · `wrk:8e23965bc20565d301ef`

### Comment

Principia should store the budget definition behind an efficiency claim. Token count, FLOPs, latency, energy, memory, and monetary cost are not interchangeable.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `5f5a617722a09d1a10ac8d52b24949c9e3f3d17d9b112dd7d9a42ab31ac00d7c`

---

## `meta:ai-ml:no-free-lunch` — No Learning or Search Algorithm Dominates Over Unrestricted Problem Classes

**Epistemic type:** no-free-lunch theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `no-free-lunch`, `optimization`, `task-distribution`, `algorithm-selection`

### Argument & interpretation

Averaged uniformly over all target functions or optimization problems under the theorem's symmetry conditions, algorithms have equal expected performance. Superior performance therefore reflects alignment with a nonuniform problem distribution or structural assumptions.

### Boundary & conditions

- The uniform averaging and closure assumptions are strong; real-world tasks are highly nonuniform.
- NFL does not imply that algorithm comparison is meaningless within a defined domain.
- Practical gains should be interpreted as evidence of useful bias, not contradiction of the theorem.

### Application

- algorithm selection
- AutoML
- optimization
- benchmark design
- meta-learning

### Basics

Wolpert and Macready developed No-Free-Lunch theorems in the 1990s for search, optimization, and inference. Later work clarified alternative problem measures and continuous settings.

### Paper / work evidence

- **Foundation (1997):** [No Free Lunch Theorems for Optimization](https://doi.org/10.1109/4235.585893) · `wrk:185fdd60d1f95b046875`
- **Refinement (2017):** [A Probabilistic Reformulation of No Free Lunch](https://doi.org/10.1162/evco_a_00196) · `wrk:2d8bfe36f68113366144`

### Comment

The theorem is frequently overgeneralized. Principia should link it as a boundary on universal claims while preserving evidence that a method matches a real task distribution.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `e387a261fb83445ad496f2f351dea17724bf02ea4f5217ba154fa70bded838d4`

---

## `meta:ai-ml:implicit-regularization` — Optimization Selects Among Many Interpolating Solutions

**Epistemic type:** optimization principle  
**Principia kind:** `mechanistic`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `implicit-bias`, `optimization`, `margin`, `regularization`

### Argument & interpretation

When many parameter settings fit the training data, initialization, optimizer, step size, parameterization, and training schedule select a particular solution. Gradient methods can favor max-margin or low-norm solutions in some regimes, acting as implicit regularizers without an explicit penalty.

### Boundary & conditions

- Known characterizations often assume linear, separable, homogeneous, or simplified models.
- The implicit bias can change under reparameterization and adaptive optimizers.
- Low norm in parameter space need not imply causal or distributional robustness.

### Application

- deep learning theory
- optimizer design
- generalization
- fine-tuning

### Basics

Work on boosting, matrix factorization, and separable linear models developed formal cases. Soudry and colleagues showed max-margin convergence of gradient descent for separable logistic regression.

### Paper / work evidence

- **Foundation (2018):** [The Implicit Bias of Gradient Descent on Separable Data](https://jmlr.org/papers/v19/18-188.html) · `wrk:5f0f6e86fea275b1b266`
- **Application (2017):** [Implicit Regularization in Matrix Factorization](https://proceedings.neurips.cc/paper/2017/hash/58191d2a914c6dae66371c9dcdc91b41-Abstract.html) · `wrk:22fe680b8a5893c8f6e5`

### Comment

Principia should treat training procedure as part of the model. Two systems with identical architectures can embody different Principles because their optimization paths differ.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `c89d3d4f526c0eb686223c84a4e57a52060dd61692eae830533803d620168d03`

---

## `meta:ai-ml:scaling-laws` — Performance Often Follows Predictable Power Laws Within a Regime

**Epistemic type:** empirical scaling observation  
**Principia kind:** `empirical`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `scaling-laws`, `compute`, `data`, `power-law`

### Argument & interpretation

For fixed data distributions, architectures, and training recipes, loss frequently follows approximate power laws in model size, dataset size, or compute until bottlenecks or regime changes dominate. Scaling laws support budget allocation and extrapolation, but the exponents are empirical properties of a training family.

### Boundary & conditions

- Power laws need not extrapolate across architecture, data quality, modality, or evaluation changes.
- Benchmark saturation and capability thresholds can hide smooth loss scaling.
- Compute-optimal allocation changes when data reuse, inference cost, or downstream utility is included.

### Application

- foundation models
- compute planning
- dataset design
- model-family comparison

### Basics

Kaplan and colleagues quantified neural-language-model scaling in 2020. Hoffmann and colleagues revised compute-optimal data/model allocation in 2022; subsequent work expanded to multimodal and downstream regimes.

### Paper / work evidence

- **Foundation (2020):** [Scaling Laws for Neural Language Models](https://arxiv.org/abs/2001.08361) · `wrk:ea280ac070a227a4b9dd`
- **Refinement (2022):** [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556) · `wrk:f584359f7971694d6554`

### Comment

Scaling is not a substitute for mechanism. Principia should store the fitted range, metric, uncertainty, and training family before using a scaling Principle to forecast future systems.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `116d9419cfae135f5708682114a888b9b4b153f3fb742a4c2edbacc08def2ac3`

---

## `meta:ai-ml:bias-variance` — Prediction Error Trades Approximation Bias Against Estimation Variance

**Epistemic type:** bias-variance decomposition  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `bias`, `variance`, `model-complexity`, `generalization`

### Argument & interpretation

For squared error under a fixed data-generating process, expected prediction error decomposes into irreducible noise, squared bias, and variance. More flexible models can reduce approximation bias while becoming more sensitive to the sample, although regularization and modern interpolation complicate the classical monotone picture.

### Boundary & conditions

- The exact decomposition depends on loss and target.
- Double descent shows that capacity–risk curves need not be U-shaped.
- Dataset shift and optimization error add terms outside the elementary decomposition.

### Application

- model complexity
- ensembles
- regularization
- data collection
- uncertainty

### Basics

The decomposition is classical in statistics; Geman, Bienenstock, and Doursat popularized it in neural-network analysis in 1992.

### Paper / work evidence

- **Foundation (1992):** [Neural Networks and the Bias/Variance Dilemma](https://doi.org/10.1162/neco.1992.4.1.1) · `wrk:7dbe1277ffbd081591bb`
- **Refinement (2019):** [Reconciling Modern Machine-Learning Practice and the Classical Bias–Variance Trade-Off](https://doi.org/10.1073/pnas.1903070116) · `wrk:1d7bb976c324f58f9da7`

### Comment

Use bias–variance as a diagnostic lens, not a universal curve. Principia should connect gains to whether they reduce approximation, estimation, optimization, or noise error.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `a64f8bbc54c9ed3c42ab3eb0b7dad21135e7c7acce8d9ddcec3b285fa09f6752`

---

## `meta:ai-ml:spurious-correlation` — Predictive Features Can Exploit Environment-Specific Shortcuts

**Epistemic type:** empirical principle  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `spurious-correlation`, `shortcut-learning`, `invariance`, `environments`

### Argument & interpretation

A high-capacity learner may use features correlated with the label in training but unrelated to the stable mechanism. Shortcut features can outperform causal or semantic features in-sample and fail when environments change. Multiple environments or interventions can reveal unstable correlations.

### Boundary & conditions

- Causal features are not always directly observable or sufficient for prediction.
- Invariant-risk objectives can fail or identify trivial solutions under weak environment diversity.
- Some shortcuts remain stable and useful within a narrow deployment scope.

### Application

- robust vision
- medical AI
- NLP
- scientific prediction
- fairness

### Basics

Work on dataset bias, domain generalization, and shortcut learning accumulated across the 2010s. Invariant Risk Minimization proposed a formal environment-based objective; later studies exposed limitations.

### Paper / work evidence

- **Foundation (2020):** [Shortcut Learning in Deep Neural Networks](https://doi.org/10.1038/s42256-020-00257-z) · `wrk:61fedbceefe65fdea72a`
- **Boundary (2021):** [Does Invariant Risk Minimization Capture Invariance?](https://proceedings.mlr.press/v130/kamath21a.html) · `wrk:e560622292ce3a586913`

### Comment

Principia should treat environment labels and counterexamples as first-class evidence. A relation that disappears after a background or site change is a scoped heuristic, not a universal mechanism.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `f3aaecef17c0c3bf87c6e253a5abd923c3d71539da26c9203ac1e51d8de0c589`

---

## `meta:ai-ml:unsupervised-identifiability` — Unsupervised Latent Factors Are Not Identifiable Without Bias or Supervision

**Epistemic type:** impossibility theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `identifiability`, `disentanglement`, `latent-variables`, `unsupervised-learning`

### Argument & interpretation

From observations alone, many invertible transformations of a latent representation can explain the same data distribution. Disentangled or causally meaningful factors therefore require inductive biases, grouped observations, interventions, temporal structure, weak supervision, or other constraints.

### Boundary & conditions

- Specific nonlinear ICA models become identifiable under auxiliary variables or temporal/nonstationary assumptions.
- Human-interpretable factors may not be unique even when predictive structure is stable.
- Evaluation metrics can favor arbitrary coordinate conventions.

### Application

- representation learning
- causal discovery
- generative models
- scientific latent variables

### Basics

Non-identifiability is classical in latent-variable models. Locatello and colleagues formalized an impossibility result for unsupervised disentanglement in 2019; nonlinear ICA work identified sufficient auxiliary assumptions.

### Paper / work evidence

- **Foundation (2019):** [Challenging Common Assumptions in the Unsupervised Learning of Disentangled Representations](https://proceedings.mlr.press/v97/locatello19a.html) · `wrk:943ccd37ee169d13b0df`
- **Constructive Boundary (2019):** [Nonlinear ICA Using Auxiliary Variables and Generalized Contrastive Learning](https://proceedings.mlr.press/v89/hyvarinen19a.html) · `wrk:37630ed4a295b4f9a213`

### Comment

Principia should not label a latent dimension as a scientific mechanism solely because it is visually interpretable. The identifying assumptions must be linked.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `e771b6538983aa522c80782ebb0bd45f7b01aef518a6ca8dc6f2a6797bac0c9e`

---

## `meta:ai-ml:information-bottleneck` — Useful Representations Preserve Task Information While Discarding Nuisance Detail

**Epistemic type:** information-bottleneck principle  
**Principia kind:** `theorem`  
**Maturity:** `supported` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `information-bottleneck`, `representation`, `compression`, `invariance`

### Argument & interpretation

The information bottleneck seeks a representation $Z$ that compresses input $X$ while preserving information about target $Y$, often written as minimizing $I(X;Z)-\beta I(Z;Y)$. Minimal sufficient representations can promote invariance and reduce nuisance dependence.

### Boundary & conditions

- Mutual information can be difficult or ill-defined for deterministic continuous networks.
- Compression is not universally necessary for generalization.
- The chosen target can encode spurious or harmful objectives.

### Application

- representation learning
- scientific compression
- robust features
- communication-efficient agents

### Basics

Tishby, Pereira, and Bialek formulated the information bottleneck in the late 1990s. Later work connected minimality and invariance to deep representations, while debates clarified limits of the neural interpretation.

### Paper / work evidence

- **Foundation (1999):** [The Information Bottleneck Method](https://arxiv.org/abs/physics/0004057) · `wrk:fe6bbb5ac84a4764d02e`
- **Refinement (2018):** [Emergence of Invariance and Disentanglement in Deep Representations](https://jmlr.org/papers/v19/17-646.html) · `wrk:77f4e8dec1f83c055a24`

### Comment

This is directly relevant to Principle Capsules: compression should preserve boundary, evidence, and testability—not only task labels.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `c6b99bef19a805bd941572de520f8309531e89ad7d0128f6d2294ebb4124072a`

---

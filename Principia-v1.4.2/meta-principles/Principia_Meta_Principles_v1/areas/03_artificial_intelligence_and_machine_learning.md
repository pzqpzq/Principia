# Artificial Intelligence and Machine Learning: Meta-Principles

This file contains 17 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `ai-ml`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:ai-ml:inductive-bias — Generalization Requires Inductive Bias

- **Epistemic type:** `learning-theoretic proposition`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `inductive-bias`, `generalization`, `priors`, `architecture`

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

- **Foundation:** [The Need for Biases in Learning Generalizations](https://www.cs.cmu.edu/~tom/pubs/NeedForBias_1980.pdf) (1980)
- **Formal boundary:** [No Free Lunch Theorems for Optimization](https://doi.org/10.1109/4235.585893) (1997)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

New AI Principles should expose the task family they favor. Describing a method as ‘general’ without its bias and environment is scientifically incomplete.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `1f9d7d49d4ee11f787eb63ee9078b4a6c36783f1f28a523f35c2027f7a206c6f`</sub>

---

## meta:ai-ml:no-free-lunch — No Learning or Search Algorithm Dominates Over Unrestricted Problem Classes

- **Epistemic type:** `no-free-lunch theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `no-free-lunch`, `optimization`, `task-distribution`, `algorithm-selection`

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

- **Foundation:** [No Free Lunch Theorems for Optimization](https://doi.org/10.1109/4235.585893) (1997)
- **Refinement:** [A Probabilistic Reformulation of No Free Lunch](https://doi.org/10.1162/evco_a_00196) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

The theorem is frequently overgeneralized. Principia should link it as a boundary on universal claims while preserving evidence that a method matches a real task distribution.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b000d966bef330e64c742222daa3bee43f885a8f695d4788cd32753700490824`</sub>

---

## meta:ai-ml:capacity-generalization — Generalization Depends on Capacity Relative to Data and Margin

- **Epistemic type:** `statistical learning theorem family`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `pac`, `vc-dimension`, `capacity`, `sample-complexity`

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

- **Foundation:** [On the Uniform Convergence of Relative Frequencies of Events to Their Probabilities](https://doi.org/10.1137/1116025) (1971)
- **Refinement:** [A Theory of the Learnable](https://doi.org/10.1145/1968.1972) (1984)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

A paper-level Principle about generalization should state which complexity measure and sampling assumptions apply rather than cite ‘more data’ abstractly.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `fb3221a07e17ca2442ef4bfb998a0d293a8c0adea3dababa49cf0a6c034208ef`</sub>

---

## meta:ai-ml:bias-variance — Prediction Error Trades Approximation Bias Against Estimation Variance

- **Epistemic type:** `bias-variance decomposition`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `bias`, `variance`, `model-complexity`, `generalization`

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

- **Foundation:** [Neural Networks and the Bias/Variance Dilemma](https://doi.org/10.1162/neco.1992.4.1.1) (1992)
- **Refinement:** [Reconciling Modern Machine-Learning Practice and the Classical Bias–Variance Trade-Off](https://doi.org/10.1073/pnas.1903070116) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Use bias–variance as a diagnostic lens, not a universal curve. Principia should connect gains to whether they reduce approximation, estimation, optimization, or noise error.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `f43a1187ffc8d7e5e5af7fbe4046528bc27e68c9ab608d8e1bc04a0bb9a89af3`</sub>

---

## meta:ai-ml:double-descent — Interpolation Can Enter a Second Generalization Regime

- **Epistemic type:** `empirical-theoretical observation`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `double-descent`, `interpolation`, `overparameterization`, `risk`

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

- **Foundation:** [Reconciling Modern Machine-Learning Practice and the Classical Bias–Variance Trade-Off](https://doi.org/10.1073/pnas.1903070116) (2019)
- **Empirical refinement:** [Deep Double Descent](https://arxiv.org/abs/1912.02292) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

This principle refines rather than refutes bias–variance reasoning. New claims should locate the interpolation threshold and compare compute- and data-matched alternatives.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `98adde9052408288ee68a0228b70d214c59241457e5c73c5dd8cca20d2736be1`</sub>

---

## meta:ai-ml:implicit-regularization — Optimization Selects Among Many Interpolating Solutions

- **Epistemic type:** `optimization principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `implicit-bias`, `optimization`, `margin`, `regularization`

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

- **Foundation:** [The Implicit Bias of Gradient Descent on Separable Data](https://jmlr.org/papers/v19/18-188.html) (2018)
- **Application:** [Implicit Regularization in Matrix Factorization](https://proceedings.neurips.cc/paper/2017/hash/58191d2a914c6dae66371c9dcdc91b41-Abstract.html) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should treat training procedure as part of the model. Two systems with identical architectures can embody different Principles because their optimization paths differ.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `5e27aaf9a31fc39c78d2beb7e3be551103cae5f5302325f321a491cc1e3ef7cf`</sub>

---

## meta:ai-ml:scaling-laws — Performance Often Follows Predictable Power Laws Within a Regime

- **Epistemic type:** `empirical scaling observation`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `scaling-laws`, `compute`, `data`, `power-law`

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

- **Foundation:** [Scaling Laws for Neural Language Models](https://arxiv.org/abs/2001.08361) (2020)
- **Refinement:** [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556) (2022)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Scaling is not a substitute for mechanism. Principia should store the fitted range, metric, uncertainty, and training family before using a scaling Principle to forecast future systems.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c9c601252e00d4abf14a522587ce73b1f279fcaf22a6aa45f63064d55e806d87`</sub>

---

## meta:ai-ml:distribution-shift — Empirical Risk Minimization Guarantees Only the Training Distribution

- **Epistemic type:** `generalization boundary`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `distribution-shift`, `ood`, `deployment`, `domain-adaptation`

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

- **Foundation:** [Dataset Shift in Machine Learning](https://mitpress.mit.edu/9780262170055/dataset-shift-in-machine-learning/) (2009)
- **Evaluation:** [In Search of Lost Domain Generalization](https://arxiv.org/abs/2007.01434) (2021)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Any ‘general’ AI Principle should name its environment family. Principia should not infer robustness from IID benchmark performance.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `d1989bdf5b915581d953d1e8e41a53ffefe89ec6eb92578402bba42bcf01816d`</sub>

---

## meta:ai-ml:spurious-correlation — Predictive Features Can Exploit Environment-Specific Shortcuts

- **Epistemic type:** `empirical principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `spurious-correlation`, `shortcut-learning`, `invariance`, `environments`

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

- **Foundation:** [Shortcut Learning in Deep Neural Networks](https://doi.org/10.1038/s42256-020-00257-z) (2020)
- **Boundary:** [Does Invariant Risk Minimization Capture Invariance?](https://proceedings.mlr.press/v130/kamath21a.html) (2021)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should treat environment labels and counterexamples as first-class evidence. A relation that disappears after a background or site change is a scoped heuristic, not a universal mechanism.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `0dae2f6f37c88633de2fccacfaad6121e9841204b79ce596f6c855146608814e`</sub>

---

## meta:ai-ml:information-bottleneck — Useful Representations Preserve Task Information While Discarding Nuisance Detail

- **Epistemic type:** `information-bottleneck principle`
- **Principia kind:** `theorem`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `information-bottleneck`, `representation`, `compression`, `invariance`

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

- **Foundation:** [The Information Bottleneck Method](https://arxiv.org/abs/physics/0004057) (1999)
- **Refinement:** [Emergence of Invariance and Disentanglement in Deep Representations](https://jmlr.org/papers/v19/17-646.html) (2018)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

This is directly relevant to Principle Capsules: compression should preserve boundary, evidence, and testability—not only task labels.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `bf3ef3f6e3d65f1c1d8db73850caad494bf0af2feee78be86cd16570d6db73fe`</sub>

---

## meta:ai-ml:unsupervised-identifiability — Unsupervised Latent Factors Are Not Identifiable Without Bias or Supervision

- **Epistemic type:** `impossibility theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `identifiability`, `disentanglement`, `latent-variables`, `unsupervised-learning`

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

- **Foundation:** [Challenging Common Assumptions in the Unsupervised Learning of Disentangled Representations](https://proceedings.mlr.press/v97/locatello19a.html) (2019)
- **Constructive boundary:** [Nonlinear ICA Using Auxiliary Variables and Generalized Contrastive Learning](https://proceedings.mlr.press/v89/hyvarinen19a.html) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should not label a latent dimension as a scientific mechanism solely because it is visually interpretable. The identifying assumptions must be linked.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `210d432c3e50b06e304845406b4b0063b131fc484c593ab0c7d0baf54f929cc9`</sub>

---

## meta:ai-ml:calibration — Confidence Scores Must Be Empirically Calibrated

- **Epistemic type:** `probabilistic prediction principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `calibration`, `confidence`, `selective-prediction`, `uncertainty`

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

- **Foundation:** [On Calibration of Modern Neural Networks](https://proceedings.mlr.press/v70/guo17a.html) (2017)
- **Application:** [Selective Classification for Deep Neural Networks](https://proceedings.neurips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should display empirical reliability curves or abstention performance rather than model self-assessment alone.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `d24941efdbd01769a47a38bce0f13fb4257cc4251d7ff1cbc84269ec901c25e5`</sub>

---

## meta:ai-ml:robustness-accuracy-tradeoff — Adversarial Robustness Can Conflict with Standard Accuracy

- **Epistemic type:** `empirical-theoretical tradeoff`
- **Principia kind:** `empirical`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `adversarial-robustness`, `accuracy`, `tradeoff`, `threat-model`

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

- **Foundation:** [Explaining and Harnessing Adversarial Examples](https://arxiv.org/abs/1412.6572) (2015)
- **Formalization:** [Robustness May Be at Odds with Accuracy](https://proceedings.mlr.press/v97/tsipras19a.html) (2019)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

A robustness claim is meaningless without threat model and attack budget. Principia should represent robustness as a scoped relation, not one global score.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `7d2d0c59afb544dd30c13f9fcc09629f09b7ffc2431dd71320c545d2e7e658e9`</sub>

---

## meta:ai-ml:exploration-exploitation — Learning Agents Must Trade Immediate Reward Against Information Gain

- **Epistemic type:** `sequential decision principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `exploration`, `exploitation`, `bandits`, `active-learning`

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

- **Foundation:** [Asymptotically Efficient Adaptive Allocation Rules](https://doi.org/10.2307/1427277) (1985)
- **Refinement:** [Finite-Time Analysis of the Multiarmed Bandit Problem](https://doi.org/10.1023/A:1013689704352) (2002)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should treat literature search, experiment choice, and model calls as budgeted actions. ‘Try more ideas’ is not a strategy unless information value is modeled.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3e6e37cc74f6721189c0283f890f69e0b6899a22f5cc903ed59979f0a8d03bdd`</sub>

---

## meta:ai-ml:credit-assignment — Learning Requires Assigning Outcomes to Responsible Internal Decisions

- **Epistemic type:** `computational principle`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `credit-assignment`, `backpropagation`, `gradients`, `reinforcement-learning`

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

- **Foundation:** [Learning Representations by Back-Propagating Errors](https://doi.org/10.1038/323533a0) (1986)
- **Sequential refinement:** [Policy Gradient Methods for Reinforcement Learning with Function Approximation](https://proceedings.neurips.cc/paper/1999/hash/464d828b85b0bed98e80ade0a5c43b0f-Abstract.html) (2000)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

A paper-level Principle should distinguish optimization credit from causal explanation. A gradient says how the implemented loss changes locally, not why a feature is scientifically responsible.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `77f64d45653058694bc17ed2e97ffa7c9236be2dc385fc4ae33aa930e9ab4645`</sub>

---

## meta:ai-ml:data-quality-ceiling — Model Performance Is Bounded by the Information and Biases in Its Data

- **Epistemic type:** `empirical principle`
- **Principia kind:** `empirical`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `data-quality`, `sampling-bias`, `labels`, `coverage`

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

- **Foundation:** [Datasheets for Datasets](https://doi.org/10.1145/3458723) (2021)
- **Application:** [Data Cascades in High-Stakes AI](https://doi.org/10.1145/3411764.3445518) (2021)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should link model claims to dataset generation and exclusions. A larger model does not erase an unobserved population or an invalid endpoint.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `3c4c7cbff94c6f8b524bc9918c74b4c8a5b7a7e29fd37a89088681eeb81e6afe`</sub>

---

## meta:ai-ml:compute-data-model-codesign — Model, Data, and Compute Must Be Co-Designed Under a Budget

- **Epistemic type:** `engineering observation`
- **Principia kind:** `heuristic`
- **Maturity:** `supported`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `compute`, `data`, `model-size`, `codesign`

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

- **Foundation:** [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556) (2022)
- **Foundation:** [Deep Learning Scaling Is Predictable, Empirically](https://arxiv.org/abs/1712.00409) (2017)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which inductive bias, data assumption, or environment restriction makes the new method effective?
- Does the reported gain survive distribution, budget, and evaluation changes?

### Comment

Principia should store the budget definition behind an efficiency claim. Token count, FLOPs, latency, energy, memory, and monetary cost are not interchangeable.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `5a172e1d1fe8780f9936de9b83b3e53c5a744339edbe61cfaa63c4dc8fca463e`</sub>


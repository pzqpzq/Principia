# Economics and Game Theory: Meta-Principles

This file contains 19 curated-draft Meta-Principles intended to anchor more specific Principles in the Principia Global Cloud. They are compact reasoning foundations, not automatic truth certificates. Each entry states its scope, failure conditions, evidence, and recommended relation to future child Principles.

**Area:** `economics-game-theory`  
**Corpus version:** `meta-principles-v1`  
**Compiled:** `2026-08-21T00:00:00Z`  
**Generation trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1`

---

## meta:economics-game-theory:scarcity-opportunity-cost — Scarcity Makes Every Choice an Opportunity-Cost Trade-off

- **Epistemic type:** `foundational economic proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `scarcity`, `opportunity-cost`, `allocation`, `trade-off`

### Argument & interpretation

When resources, time, attention, or feasible actions are limited, choosing one allocation excludes alternatives. The economically relevant cost of an action is therefore the value of the best forgone feasible alternative, not merely its accounting expenditure. Any claimed improvement should state what scarce resource is reallocated and what competing use is displaced.

### Boundary & conditions

- Opportunity cost is defined relative to a feasible choice set and the decision maker’s objective.
- When resources are non-rival, abundant, or unconstrained, the trade-off may be negligible.
- Externalities and distributional effects can make private opportunity cost differ from social opportunity cost.

### Application

- resource allocation
- research budgeting
- compute allocation
- health policy
- operations

### Basics

The idea is implicit in classical economics and became central to marginalist and modern choice theory. Robbins’s 1932 definition of economics emphasized scarce means with alternative uses; later welfare and optimization theory formalized feasible-set trade-offs.

### Paper / work evidence

- **Foundation:** [An Essay on the Nature and Significance of Economic Science](https://mises.org/library/book/essay-nature-and-significance-economic-science) (1932)
- **Formalization:** [The Foundations of Welfare Economics](https://doi.org/10.2307/1906922) (1939)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Opportunity cost is often invoked rhetorically without identifying the counterfactual alternative. In Principia, a child Principle should name the budget, the excluded alternative, and the decision horizon.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `6d8e7b1424af18137ae4783db3f66a8a9eb4f09f062e4bbc39f62969c8128db9`</sub>

---

## meta:economics-game-theory:comparative-advantage — Comparative Advantage Depends on Relative, Not Absolute, Costs

- **Epistemic type:** `theoretical economic principle`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `comparative-advantage`, `specialization`, `exchange`, `relative-cost`

### Argument & interpretation

Specialization and exchange can create gains when agents, firms, or countries differ in relative opportunity costs, even when one party is absolutely more productive in every activity. The allocation logic compares ratios of trade-offs rather than raw productivity levels.

### Boundary & conditions

- Gains require feasible exchange and prices or transfers that make participation worthwhile.
- Transport costs, market power, adjustment costs, strategic dependencies, and externalities can erase or reverse gains.
- Static comparative advantage need not justify permanent specialization when learning, innovation, or resilience are endogenous.

### Application

- international trade
- task allocation
- multi-agent systems
- supply chains
- organizational design

### Basics

Ricardo articulated comparative advantage in 1817. Later general-equilibrium and Heckscher–Ohlin models extended the logic to multiple goods, factors, and countries.

### Paper / work evidence

- **Foundation:** [On the Principles of Political Economy and Taxation](https://oll.libertyfund.org/titles/ricardo-on-the-principles-of-political-economy-and-taxation) (1817)
- **Formalization:** [The Pure Theory of International Trade](https://doi.org/10.2307/1905748) (1932)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

The principle is structurally useful beyond trade, but analogies to agent specialization require explicit communication, coordination, and failure costs. It should not be used to ignore distributional consequences.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `21ae493aa15efae28c3cf978f4c36db0ce4984803b543466834a4e850987a4d1`</sub>

---

## meta:economics-game-theory:marginal-optimization — Optimal Choices Equate Marginal Benefit and Marginal Cost at an Interior Solution

- **Epistemic type:** `optimization proposition`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `marginalism`, `optimization`, `shadow-price`, `first-order-condition`

### Argument & interpretation

For a smooth interior optimum, a decision variable should be adjusted until the incremental benefit of another unit equals its incremental opportunity cost. In constrained form, shadow prices convert scarce resources into marginal costs, producing first-order optimality conditions.

### Boundary & conditions

- The rule is local and requires differentiability or a valid generalized derivative.
- Corner solutions, indivisibilities, nonconvexities, strategic interactions, and multiple equilibria can invalidate the simple equality.
- Marginal equality does not guarantee global optimality.

### Application

- pricing
- production
- experimental design
- compute scaling
- policy optimization

### Basics

Marginal reasoning emerged in nineteenth-century economics through Jevons, Menger, Walras, and Marshall and was later unified with constrained optimization and Lagrange multipliers.

### Paper / work evidence

- **Foundation:** [Theory of Political Economy](https://oll.libertyfund.org/titles/jevons-the-theory-of-political-economy) (1871)
- **Formalization:** [The Foundations of Economic Analysis](https://www.hup.harvard.edu/books/9780674313033) (1947)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

A reported optimum should include the feasible set, the objective, and evidence that the candidate is not merely a local stationary point.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `daa823aacca16c79e3eafa2d9cccd107c53153b4cb9b1a935fa47d8e10adc4eb`</sub>

---

## meta:economics-game-theory:competitive-equilibrium — Competitive Equilibrium Coordinates Decentralized Choices Under Strong Institutional Assumptions

- **Epistemic type:** `equilibrium existence theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `general-equilibrium`, `prices`, `decentralization`, `fixed-point`

### Argument & interpretation

In an idealized economy with complete markets, suitable preferences and technologies, and price-taking agents, a price vector can coordinate individually optimal plans so aggregate demand equals aggregate supply. The result shows how decentralized optimization may be mutually consistent; it does not show that real markets automatically meet the required assumptions.

### Boundary & conditions

- Existence relies on continuity, convexity or related regularity, and appropriate endowments.
- Market power, incomplete markets, externalities, asymmetric information, increasing returns, or nonconvex production can defeat the conclusion.
- Equilibrium may be nonunique, unstable, or computationally difficult to reach.

### Application

- market design
- resource allocation
- energy markets
- network economics
- multi-agent coordination

### Basics

Walras introduced general equilibrium; Arrow and Debreu established a modern existence theorem in 1954 using fixed-point methods.

### Paper / work evidence

- **Foundation:** [Existence of an Equilibrium for a Competitive Economy](https://doi.org/10.2307/1907353) (1954)
- **Precursor:** [A Social Equilibrium Existence Theorem](https://doi.org/10.1073/pnas.38.10.886) (1952)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Equilibrium is a consistency concept, not a welfare or fairness certificate. Principia should separate existence, uniqueness, stability, computability, and desirability.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `954f883042a6afb0fa44b63b572b7c6f5cb752fe837b0c4b4574b0844da5908b`</sub>

---

## meta:economics-game-theory:nash-equilibrium — Nash Equilibrium Is Mutual Best Response, Not Automatic Optimality

- **Epistemic type:** `equilibrium existence theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `nash-equilibrium`, `best-response`, `strategic-interaction`, `game-theory`

### Argument & interpretation

A strategy profile is a Nash equilibrium when no agent can improve its payoff by unilateral deviation. Under finite games, mixed-strategy equilibria exist. The concept predicts strategic consistency given beliefs about others, but it does not imply efficiency, fairness, uniqueness, stability, or empirical selection.

### Boundary & conditions

- The equilibrium depends on the game, information, timing, payoff model, and solution concept.
- Multiple equilibria require an equilibrium-selection mechanism.
- Bounded rationality, learning dynamics, collusion, or coalition deviations may make Nash predictions unreliable.

### Application

- multi-agent systems
- auctions
- security
- network protocols
- political economy

### Basics

Nash proved equilibrium existence for finite noncooperative games in 1950–1951, extending earlier minimax work for zero-sum games.

### Paper / work evidence

- **Foundation:** [Equilibrium Points in N-Person Games](https://doi.org/10.1073/pnas.36.1.48) (1950)
- **Full formulation:** [Non-Cooperative Games](https://doi.org/10.2307/1969529) (1951)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

A new Principle invoking equilibrium should state the deviation class and why agents can find or learn the equilibrium. Nash equilibrium is often mistaken for a socially desirable outcome.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `181aaacbc378ed6ca2e288d923e14d0d818b759928a0c2100919d962e69e1ee4`</sub>

---

## meta:economics-game-theory:pareto-efficiency-welfare — Pareto Efficiency Separates Feasibility from Distributional Judgment

- **Epistemic type:** `welfare theorem and criterion`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `pareto-efficiency`, `welfare`, `distribution`, `feasibility`

### Argument & interpretation

An allocation is Pareto efficient when no feasible change can improve at least one party without worsening another. Under ideal competitive assumptions, the welfare theorems connect competitive equilibria and Pareto efficiency. The criterion rules out avoidable waste but is silent about fairness, rights, initial endowments, and interpersonal welfare comparisons.

### Boundary & conditions

- Efficiency is relative to the specified feasible set and preferences.
- Externalities, public goods, incomplete markets, nonconvexities, and information constraints break welfare-theorem conditions.
- Many radically unequal allocations are Pareto efficient.

### Application

- multi-objective optimization
- policy analysis
- mechanism design
- fairness
- resource allocation

### Basics

Pareto developed the efficiency concept; twentieth-century welfare economics and Arrow–Debreu theory established formal welfare theorems.

### Paper / work evidence

- **Foundation:** [The Foundations of Welfare Economics](https://doi.org/10.2307/1906922) (1939)
- **Extension:** [Some Aspects of the Welfare Economics of Public Finance](https://doi.org/10.2307/1884512) (1952)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Principia should not equate “Pareto efficient” with “best.” A child Principle must state whose utility, constraints, and distributional criteria are excluded.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `70d8afd99ef7873a8357366c1a237e9a27a0730e30750287e87913259c207cf6`</sub>

---

## meta:economics-game-theory:transaction-costs-institutions — Institutions Arise Partly to Reduce Transaction and Coordination Costs

- **Epistemic type:** `institutional economic proposition`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `transaction-costs`, `institutions`, `governance`, `coordination`

### Argument & interpretation

Using markets, firms, contracts, standards, or platforms incurs search, bargaining, monitoring, enforcement, and adaptation costs. Organizational boundaries and governance structures can therefore be interpreted as responses to comparative transaction costs rather than production technology alone.

### Boundary & conditions

- Transaction costs are difficult to measure and can be endogenous to institutions.
- Power, law, culture, capability accumulation, and path dependence also shape organizational form.
- Lower transaction cost does not guarantee fairness or social desirability.

### Application

- firm boundaries
- platform design
- open-source governance
- supply chains
- multi-agent organization

### Basics

Coase’s 1937 theory of the firm and 1960 analysis of social cost founded transaction-cost reasoning; Williamson later developed comparative governance analysis.

### Paper / work evidence

- **Foundation:** [The Nature of the Firm](https://doi.org/10.1111/j.1468-0335.1937.tb00002.x) (1937)
- **Foundation:** [The Problem of Social Cost](https://doi.org/10.1086/466560) (1960)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

The principle should motivate measurable coordination mechanisms rather than serve as a post hoc story explaining any institution.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `c4e0bd9e9fd8e0fa80c5a94dc7e60136145cf417c99ccc5b025108be58fa8694`</sub>

---

## meta:economics-game-theory:externalities-public-goods — Unpriced External Effects Separate Private and Social Optima

- **Epistemic type:** `welfare-economic proposition`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `externality`, `public-good`, `free-riding`, `social-cost`

### Argument & interpretation

When an action changes others’ welfare without a corresponding price or contract, private marginal incentives diverge from social marginal effects. Public goods additionally create non-rival or non-excludable benefits, producing free-riding and underprovision under ordinary private incentives.

### Boundary & conditions

- The magnitude and sign of external effects depend on system boundaries and counterfactuals.
- Coasian bargaining requires sufficiently defined rights and low transaction costs.
- Government intervention can itself be costly, captured, or information-limited.

### Application

- environmental policy
- cybersecurity
- public health
- scientific infrastructure
- platform governance

### Basics

Pigou formalized corrective taxes; Coase emphasized reciprocal effects and transaction costs; Samuelson provided a formal theory of public expenditure and public goods.

### Paper / work evidence

- **Foundation:** [The Pure Theory of Public Expenditure](https://doi.org/10.2307/1925895) (1954)
- **Institutional boundary:** [The Problem of Social Cost](https://doi.org/10.1086/466560) (1960)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

A child Principle should identify who bears the external effect, whether exclusion is feasible, and whether the proposed remedy creates new distortions.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `b318863b6bb9d6bb8bdb85be3b0f10a441d7809641b60e0c886d62fd2f2f13ba`</sub>

---

## meta:economics-game-theory:commons-governance — Common-Pool Resources Require Governance Matched to Excludability and Rivalry

- **Epistemic type:** `institutional observation`
- **Principia kind:** `empirical`
- **Maturity:** `replicated`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `commons`, `governance`, `collective-action`, `institutions`

### Argument & interpretation

Resources that are costly to exclude users from yet depleted by use invite overappropriation when individual benefits are immediate and collective costs diffuse. Durable governance can emerge through monitoring, graduated sanctions, local rule-making, nested institutions, or property arrangements; privatization and centralized control are not the only possibilities.

### Boundary & conditions

- Outcomes depend on group size, resource dynamics, trust, monitoring cost, mobility, and external pressures.
- Hardin’s open-access model does not describe all commons.
- Locally successful institutions may not scale or transfer without modification.

### Application

- natural-resource management
- shared compute
- open-source maintenance
- data commons
- public infrastructure

### Basics

Hardin popularized the tragedy model in 1968. Ostrom’s comparative field research documented conditions under which communities sustainably govern common-pool resources.

### Paper / work evidence

- **Foundation:** [The Tragedy of the Commons](https://doi.org/10.1126/science.162.3859.1243) (1968)
- **Empirical refinement:** [Governing the Commons](https://doi.org/10.1017/CBO9780511807763) (1990)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

The principle is frequently oversimplified. Principia should distinguish open access from governed commons and record the institutional conditions supporting success.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `65058627a79e808b696b771ff65e9f3413ceaaac41e436013b1a7646f335edb1`</sub>

---

## meta:economics-game-theory:adverse-selection — Private Information Can Drive High-Quality Participants from a Market

- **Epistemic type:** `information-economic mechanism`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `adverse-selection`, `asymmetric-information`, `market-unravelling`, `selection-bias`

### Argument & interpretation

When one side privately knows quality or risk and prices cannot condition on that information, average-price offers can be unattractive to high-quality types. Their exit worsens the remaining pool, potentially causing market unraveling or missing trade.

### Boundary & conditions

- The result depends on information asymmetry, pooling prices, and inability to credibly signal or screen.
- Reputation, warranties, certification, repeated interaction, or regulation can mitigate selection.
- Not every low-volume market reflects adverse selection.

### Application

- insurance
- labor markets
- online platforms
- scientific peer review
- data marketplaces

### Basics

Akerlof’s 1970 “lemons” model crystallized adverse selection; subsequent insurance and contract theory generalized it.

### Paper / work evidence

- **Foundation:** [The Market for Lemons: Quality Uncertainty and the Market Mechanism](https://doi.org/10.2307/1879431) (1970)
- **Extension:** [Equilibrium in Competitive Insurance Markets](https://doi.org/10.2307/1885326) (1976)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Selection mechanisms can mimic treatment effects or performance differences. New Principles based on observed participants should ask which types were excluded before measurement.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `9a8d2ebb65dc135c09ee5efcd2e317448cd37f1ac80fb1953b4c0102b739210d`</sub>

---

## meta:economics-game-theory:signaling-screening — Costly Signals and Screens Can Separate Hidden Types Only Under Incentive Compatibility

- **Epistemic type:** `information-economic proposition`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `signaling`, `screening`, `incentive-compatibility`, `hidden-type`

### Argument & interpretation

An observable action can communicate hidden type when different types face sufficiently different costs or benefits from producing it. Conversely, an uninformed principal can design a menu that induces self-selection. Separation requires incentive-compatible behavior, not merely correlation between signal and type.

### Boundary & conditions

- Cheap or easily imitated signals may pool rather than separate.
- Equilibria can be multiple and socially wasteful.
- Signals may change meaning after institutions, technologies, or beliefs change.

### Application

- education
- credentialing
- AI evaluation
- security protocols
- contract design

### Basics

Spence formalized job-market signaling in 1973; screening and mechanism-design theories generalized type-revelation through contracts.

### Paper / work evidence

- **Foundation:** [Job Market Signaling](https://doi.org/10.2307/1882010) (1973)
- **Screening extension:** [Competitive Insurance Markets and the Theory of Screening Equilibria](https://doi.org/10.2307/1885326) (1976)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

A benchmark score or certificate should not automatically be interpreted as latent capability. Its cost structure and manipulability determine whether it is informative.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `f1674838ac013a055efd440e211dafb30484c61567e233391c4fe7947125f860`</sub>

---

## meta:economics-game-theory:principal-agent-moral-hazard — Delegation Creates Moral Hazard When Actions Are Hidden and Objectives Differ

- **Epistemic type:** `contract-theoretic mechanism`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `principal-agent`, `moral-hazard`, `contracts`, `monitoring`

### Argument & interpretation

A principal delegating work to an agent cannot generally condition rewards on hidden effort or all relevant actions. When the agent’s objective differs from the principal’s, contracts must trade incentive strength against risk sharing, measurement noise, gaming, and monitoring cost.

### Boundary & conditions

- The result changes when effort is observable, objectives are aligned, or repeated reputation disciplines behavior.
- Performance measures can induce multitask distortion and Goodhart effects.
- High-powered incentives may shift risk to parties least able to bear it.

### Application

- organizational design
- AI-agent oversight
- employment contracts
- healthcare payment
- platform moderation

### Basics

Principal–agent and moral-hazard models were developed in the 1970s by Mirrlees, Holmström, and others. Holmström formalized informativeness and team moral hazard.

### Paper / work evidence

- **Foundation:** [Moral Hazard and Observability](https://doi.org/10.2307/3003320) (1979)
- **Extension:** [Moral Hazard in Teams](https://doi.org/10.2307/1912702) (1982)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Agentic AI systems make hidden-action problems concrete. More monitoring is not automatically optimal if it displaces useful autonomy or encourages metric gaming.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `522f9fcf4b84c87e2012a34e8bff8af34b235c2b7de3a3a4df3944c7c76924eb`</sub>

---

## meta:economics-game-theory:revelation-principle — Mechanism Search Can Often Be Reduced to Truthful Direct Mechanisms

- **Epistemic type:** `mechanism-design theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `mechanism-design`, `revelation`, `truthfulness`, `incentives`

### Argument & interpretation

For a specified equilibrium concept, any outcome implementable by some indirect mechanism can often be replicated by a direct mechanism in which agents report private information and truthful reporting is an equilibrium. This converts a broad institutional design problem into incentive constraints over reports.

### Boundary & conditions

- The theorem is relative to an equilibrium concept and informational environment.
- It does not imply truthfulness is unique, obvious, robust to bounded rationality, or easy to implement.
- Communication, privacy, computation, and dynamic participation constraints can make direct mechanisms impractical.

### Application

- auctions
- matching
- resource allocation
- federated systems
- AI mechanism design

### Basics

The revelation principle emerged from work by Gibbard, Green and Laffont, Myerson, and others in the 1970s–1980s and became foundational to mechanism design.

### Paper / work evidence

- **Foundation:** [Incentive Compatibility and the Bargaining Problem](https://doi.org/10.2307/1910155) (1979)
- **Canonical application:** [Optimal Auction Design](https://doi.org/10.1287/moor.6.1.58) (1981)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

The principle is a search-space reduction, not a guarantee that the optimal mechanism is socially acceptable or behaviorally credible.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `57ace0dd8c7729a8996ef7f03d02aca2e3595593ac0f05a49440379788c9c8fc`</sub>

---

## meta:economics-game-theory:arrow-impossibility — No Aggregation Rule Satisfies All Classical Fairness Axioms on Unrestricted Preferences

- **Epistemic type:** `social-choice impossibility theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `arrow-impossibility`, `social-choice`, `aggregation`, `fairness`

### Argument & interpretation

With at least three alternatives and an unrestricted domain of ordinal preferences, no social welfare function can simultaneously satisfy a standard set of conditions including unrestricted domain, Pareto responsiveness, independence of irrelevant alternatives, and non-dictatorship. Collective choice therefore requires relaxing an axiom, restricting preferences, adding interpersonal information, or changing the output object.

### Boundary & conditions

- The conclusion depends exactly on the stated axioms and ordinal aggregation framework.
- Domain restrictions such as single-peaked preferences can restore possibility.
- Randomization, cardinal utilities, deliberation, or incomplete social rankings change the problem.

### Application

- voting
- multi-agent aggregation
- benchmark ranking
- collective decision systems
- AI governance

### Basics

Arrow’s 1951 monograph established the theorem and initiated modern axiomatic social choice.

### Paper / work evidence

- **Foundation:** [Social Choice and Individual Values](https://yalebooks.yale.edu/book/9780300179316/social-choice-and-individual-values/) (1951)
- **Precursor:** [A Difficulty in the Concept of Social Welfare](https://doi.org/10.1086/256963) (1950)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Impossibility theorems diagnose incompatible desiderata; they do not say collective choice is pointless. Principia should link every proposed aggregation rule to the axiom it sacrifices.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `72a3f07d06cc82c1b153c68c29138bacd5a38322fe34c4ff21d696f87ab9d344`</sub>

---

## meta:economics-game-theory:bilateral-trade-impossibility — Private Information Can Make Efficient Bilateral Trade Incompatible with Incentives and Budget Balance

- **Epistemic type:** `mechanism-design impossibility theorem`
- **Principia kind:** `theorem`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `bilateral-trade`, `impossibility`, `private-information`, `budget-balance`

### Argument & interpretation

When a privately informed buyer and seller have overlapping value distributions, no mechanism can generally be simultaneously Bayesian incentive compatible, individually rational, budget balanced, and ex post efficient. Some mutually beneficial trades must be foregone or subsidized.

### Boundary & conditions

- The theorem assumes a particular bilateral private-values environment and regularity conditions.
- Repeated interaction, intermediaries, subsidies, correlated information, or relaxed efficiency can change feasibility.
- It does not imply all markets are inefficient.

### Application

- marketplaces
- data exchange
- federated collaboration
- procurement
- platform design

### Basics

Myerson and Satterthwaite proved the result in 1983, establishing a central boundary for mechanism design under two-sided private information.

### Paper / work evidence

- **Foundation:** [Efficient Mechanisms for Bilateral Trading](https://doi.org/10.1016/0022-0531(83)90048-0) (1983)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

The theorem is useful for evaluating unrealistic platform claims that promise perfect efficiency, voluntary participation, truthful revelation, and no subsidy simultaneously.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `a27237a90cbcf05b6afff4e5ffd6de92e36fe396083d8ff54beceb74e9b547c3`</sub>

---

## meta:economics-game-theory:lucas-critique — Policy Changes Alter the Behavioral Rules Used to Predict Their Effects

- **Epistemic type:** `macro-causal proposition`
- **Principia kind:** `mechanistic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `lucas-critique`, `policy`, `invariance`, `adaptation`

### Argument & interpretation

Empirical relationships estimated under one policy regime need not remain invariant when policy changes the incentives, information, expectations, and constraints generating behavior. Reliable counterfactual policy analysis therefore seeks structural parameters or explicitly models adaptation rather than extrapolating reduced-form correlations unchanged.

### Boundary & conditions

- Not every predictive relationship changes materially with policy.
- Structural models can be misspecified and are not automatically invariant.
- The critique is strongest for interventions that alter expectations or strategic behavior.

### Application

- policy evaluation
- market regulation
- AI deployment
- organizational intervention
- causal transport

### Basics

Lucas formulated the critique in 1976 against policy evaluation based on historical macroeconomic equations. It influenced rational-expectations and structural econometrics.

### Paper / work evidence

- **Foundation:** [Econometric Policy Evaluation: A Critique](https://doi.org/10.1016/S0167-2231(76)80003-6) (1976)
- **Causal refinement:** [Causality: Models, Reasoning, and Inference](https://www.cambridge.org/core/books/causality/B0046844FAE10CBF274D4ACBDAEB5F5B) (2009)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

This is a domain-specific version of intervention-induced distribution shift. A new Principle used for policy must identify which data-generating mechanisms are expected to remain stable.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `d3ad64d9d4f9b81ae28bbdc6d76e1155375026e4681cd31dc7c3d6057750c4f1`</sub>

---

## meta:economics-game-theory:path-dependence-increasing-returns — Increasing Returns Can Lock Systems into Path-Dependent Outcomes

- **Epistemic type:** `dynamic economic mechanism`
- **Principia kind:** `mechanistic`
- **Maturity:** `replicated`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `path-dependence`, `increasing-returns`, `lock-in`, `network-effects`

### Argument & interpretation

When adoption raises future payoff through learning, network effects, coordination, complementarity, or switching costs, early random or historical events can select one among multiple persistent outcomes. The eventual state may be locally stable without being globally efficient.

### Boundary & conditions

- Path dependence requires a reinforcing mechanism, not merely temporal sequence.
- Strong shocks, interoperability, multihoming, or declining returns can reverse lock-in.
- Historical narratives must distinguish causal increasing returns from retrospective storytelling.

### Application

- technology standards
- platforms
- industrial geography
- scientific paradigms
- organizational routines

### Basics

David and Arthur developed modern path-dependence and increasing-returns models in the 1980s–1990s, building on earlier cumulative-causation ideas.

### Paper / work evidence

- **Foundation:** [Competing Technologies, Increasing Returns, and Lock-In by Historical Events](https://doi.org/10.1111/j.1467-9701.1989.tb00652.x) (1989)
- **Historical application:** [Clio and the Economics of QWERTY](https://doi.org/10.2307/1805621) (1985)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Lock-in claims are controversial when alternatives were not truly feasible or when performance differences are ignored. The reinforcing mechanism should be directly tested.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `33446671267463b195c1f231feb92472d1e46fe86f0984d1d3f8a9ca3c627e12`</sub>

---

## meta:economics-game-theory:bounded-rationality — Rational Choice Is Constrained by Information, Computation, and Search

- **Epistemic type:** `behavioral and computational proposition`
- **Principia kind:** `heuristic`
- **Maturity:** `established`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `bounded-rationality`, `satisficing`, `heuristics`, `computation`

### Argument & interpretation

Decision makers optimize only within limits imposed by attention, information, representation, computation, time, and organizational procedure. They may satisfice, use heuristics, or optimize a simplified internal model. Institutions and interfaces therefore shape outcomes by changing the effective decision problem.

### Boundary & conditions

- A bounded model must specify which resource is limited and which heuristic follows.
- Observed deviations from an ideal model do not uniquely identify a cognitive mechanism.
- Expertise, tools, incentives, and repeated feedback can alter bounds.

### Application

- behavioral economics
- human–AI interaction
- agent design
- organizational behavior
- mechanism robustness

### Basics

Simon introduced satisficing and bounded rationality in the 1940s–1950s. Later behavioral economics and computational rationality developed empirical and formal variants.

### Paper / work evidence

- **Foundation:** [A Behavioral Model of Rational Choice](https://doi.org/10.2307/1884852) (1955)
- **Extension:** [Rational Choice and the Structure of the Environment](https://doi.org/10.1037/h0042769) (1956)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Labeling behavior “irrational” is less informative than modeling the resource constraint and representation. The same principle applies to LLM and multi-agent reasoning budgets.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `ac0d25f9303178a652f352c0f065da066f8098a2db89b9c9e2885b97976bf4c9`</sub>

---

## meta:economics-game-theory:reference-dependence-loss-aversion — Choices Can Depend on Reference Points and Asymmetric Valuation of Gains and Losses

- **Epistemic type:** `behavioral observation`
- **Principia kind:** `empirical`
- **Maturity:** `replicated`
- **Stability:** `high`
- **Review status:** `curated_draft`
- **Tags:** `prospect-theory`, `reference-dependence`, `loss-aversion`, `framing`

### Argument & interpretation

Observed choice often depends on outcomes relative to a reference point rather than final wealth alone, with losses frequently weighted more strongly than comparable gains. Probability weighting and framing can further violate expected-utility predictions.

### Boundary & conditions

- Effect sizes vary across domain, stakes, experience, elicitation, and reference-point definition.
- Some apparent loss aversion can arise from expectations, attention, or experimental design.
- The model is descriptive and does not determine normative welfare by itself.

### Application

- risk communication
- product design
- policy framing
- behavioral finance
- medical decisions

### Basics

Kahneman and Tversky introduced prospect theory in 1979; cumulative prospect theory and reference-dependent preference models later refined it.

### Paper / work evidence

- **Foundation:** [Prospect Theory: An Analysis of Decision under Risk](https://doi.org/10.2307/1914185) (1979)
- **Refinement:** [Advances in Prospect Theory: Cumulative Representation of Uncertainty](https://doi.org/10.1007/BF00122574) (1992)

### Link to more specific Principles

- **Recommended child relation(s):** `specializes`, `depends_on`
- Which assumptions, incentives, constraints, or information structure make the new Principle an instance of this Meta-Principle?
- Would the conclusion survive a change in agents, institutions, equilibrium concept, or resource constraints?

### Comment

Behavioral regularities should not be treated as universal constants. A Principle should record how the reference point was established and whether choices were incentivized.

<sub>Trace: `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · Version: `1` · Content digest: `e0e551c55fa3d28b99bd9344ac6e072b18204da9849c6968a44c37b633c4dd47`</sub>


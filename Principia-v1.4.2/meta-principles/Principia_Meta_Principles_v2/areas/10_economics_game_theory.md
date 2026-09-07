# Economics and Game Theory Meta-Principles

> **Area ID:** `economics-game-theory`  
> **Records:** 27  
> **Status:** Curated draft for domain-expert review; not automatically promoted to reviewed Global Capsules.

These records are broad roots for linking more specific paper-derived Principles. Award recognition and industry adoption are recorded as significance metadata; they do not alter epistemic type or remove boundary conditions.

## `meta:economics-game-theory:revenue-equivalence-optimal-auctions` — Auction Revenue Depends on Allocation and Information Structure More Than Surface Format

**Epistemic type:** auction-theory theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_foundation`  
**Introduced / developed:** 1961–present  
**Tags:** `auction-theory`, `revenue-equivalence`, `mechanism-design`, `myerson`

### Argument & interpretation

Under independent private values, risk neutrality, symmetric bidders, and standard participation conditions, auction mechanisms that allocate the object to the highest type and give the lowest type the same expected utility generate the same expected revenue. Optimal-auction theory modifies allocation or reserve rules when those assumptions fail or distributions differ.

### Boundary & conditions

- Affiliation, common values, asymmetry, risk aversion, budgets, and dynamic entry break equivalence.
- Revenue optimality may conflict with efficiency, fairness, simplicity, or robustness.
- Distributional misspecification can make theoretically optimal mechanisms fragile.

### Application

- auctions
- ad markets
- spectrum allocation
- procurement
- platform design

### Basics

Vickrey established truthful second-price auctions in 1961; Myerson derived optimal auction design in 1981. Vickrey received the 1996 economics prize; Myerson shared the 2007 prize.

### Paper / work evidence

- **Foundation (1961):** [Counterspeculation, Auctions, and Competitive Sealed Tenders](https://doi.org/10.1111/j.1540-6261.1961.tb02789.x) · `wrk:82ecfbef1aba430240e4`
- **Formalization (1981):** [Optimal Auction Design](https://doi.org/10.1287/moor.6.1.58) · `wrk:d92a2964dd2ee2a1fb84`
- **Recognition (2007):** [The Sveriges Riksbank Prize in Economic Sciences 2007](https://www.nobelprize.org/prizes/economic-sciences/2007/summary/) · `wrk:f13fbb322a4a9d7cf1fa`

### Foundation relations

- `specializes` → `meta:economics-game-theory:revelation-principle` — Auction design is a canonical mechanism-design problem.
- `depends_on` → `meta:economics-game-theory:adverse-selection` — Revenue and incentives depend on private information structure.

### Comment

This Principle should anchor auction claims to explicit bidder information and behavioral assumptions rather than to a preferred bidding format.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `35bddbb1dfa4c707281ba594906110c9f453f5e7b76209bbf038a22800c60635`

---

## `meta:economics-game-theory:reference-dependence-loss-aversion` — Choices Can Depend on Reference Points and Asymmetric Valuation of Gains and Losses

**Epistemic type:** behavioral observation  
**Principia kind:** `empirical`  
**Maturity:** `replicated` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `prospect-theory`, `reference-dependence`, `loss-aversion`, `framing`

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

- **Foundation (1979):** [Prospect Theory: An Analysis of Decision under Risk](https://doi.org/10.2307/1914185) · `wrk:0136258fe8c8997d123e`
- **Refinement (1992):** [Advances in Prospect Theory: Cumulative Representation of Uncertainty](https://doi.org/10.1007/BF00122574) · `wrk:47a96962ebd105bea999`

### Comment

Behavioral regularities should not be treated as universal constants. A Principle should record how the reference point was established and whether choices were incentivized.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `32c1e9f5f3eee111fd7cb4fd8c0ccd46fe682902e36df76c41e051706bbdb9d1`

---

## `meta:economics-game-theory:commons-governance` — Common-Pool Resources Require Governance Matched to Excludability and Rivalry

**Epistemic type:** institutional observation  
**Principia kind:** `empirical`  
**Maturity:** `replicated` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `commons`, `governance`, `collective-action`, `institutions`

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

- **Foundation (1968):** [The Tragedy of the Commons](https://doi.org/10.1126/science.162.3859.1243) · `wrk:f47c153a89aabb6826df`
- **Empirical Refinement (1990):** [Governing the Commons](https://doi.org/10.1017/CBO9780511807763) · `wrk:70cdebe14e4d38f35c9e`

### Comment

The principle is frequently oversimplified. Principia should distinguish open access from governed commons and record the institutional conditions supporting success.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `4fa9f10c44c2ae67cf1d0879034cfc80758387b197d8fbcc8dfabf943f9fed6c`

---

## `meta:economics-game-theory:comparative-advantage` — Comparative Advantage Depends on Relative, Not Absolute, Costs

**Epistemic type:** theoretical economic principle  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `comparative-advantage`, `specialization`, `exchange`, `relative-cost`

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

- **Foundation (1817):** [On the Principles of Political Economy and Taxation](https://oll.libertyfund.org/titles/ricardo-on-the-principles-of-political-economy-and-taxation) · `wrk:527a218dda32ce668452`
- **Formalization (1932):** [The Pure Theory of International Trade](https://doi.org/10.2307/1905748) · `wrk:1bf4aaa73d3005a59f7c`

### Comment

The principle is structurally useful beyond trade, but analogies to agent specialization require explicit communication, coordination, and failure costs. It should not be used to ignore distributional consequences.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `26ecc52b2e2256a7ef3b47646a52be5c8cfdb15a68931adaeed2bda397dfdeb6`

---

## `meta:economics-game-theory:competitive-equilibrium` — Competitive Equilibrium Coordinates Decentralized Choices Under Strong Institutional Assumptions

**Epistemic type:** equilibrium existence theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `general-equilibrium`, `prices`, `decentralization`, `fixed-point`

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

- **Foundation (1954):** [Existence of an Equilibrium for a Competitive Economy](https://doi.org/10.2307/1907353) · `wrk:58f6587bc1c9044d0bf6`
- **Precursor (1952):** [A Social Equilibrium Existence Theorem](https://doi.org/10.1073/pnas.38.10.886) · `wrk:ad69bd54c5b36526262d`

### Comment

Equilibrium is a consistency concept, not a welfare or fairness certificate. Principia should separate existence, uniqueness, stability, computability, and desirability.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `755a6a8545091659625d34e91fa18358a8617b8b724adb76dfbd6a809cd3084d`

---

## `meta:economics-game-theory:signaling-screening` — Costly Signals and Screens Can Separate Hidden Types Only Under Incentive Compatibility

**Epistemic type:** information-economic proposition  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `signaling`, `screening`, `incentive-compatibility`, `hidden-type`

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

- **Foundation (1973):** [Job Market Signaling](https://doi.org/10.2307/1882010) · `wrk:2baaf3a927441d3604dc`
- **Screening Extension (1976):** [Competitive Insurance Markets and the Theory of Screening Equilibria](https://doi.org/10.2307/1885326) · `wrk:a04536ce0a6a32df0875`

### Comment

A benchmark score or certificate should not automatically be interpreted as latent capability. Its cost structure and manipulability determine whether it is informative.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `1d5572a47eefed2f087bd0be744f539ce7a490340c46a13107aa79c908d0e188`

---

## `meta:economics-game-theory:stable-matching-deferred-acceptance` — Deferred Acceptance Produces a Stable Matching Under Declared Preferences

**Epistemic type:** matching theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_foundation`  
**Introduced / developed:** 1962–present  
**Tags:** `stable-matching`, `deferred-acceptance`, `market-design`, `nobel-2012`

### Argument & interpretation

In a two-sided matching market with ordinal preferences, deferred acceptance terminates at a stable matching with no unmatched pair that prefers each other to assigned partners. The outcome is optimal for the proposing side within the lattice of stable matchings and has favorable incentive properties for proposers.

### Boundary & conditions

- Results depend on preference structure, substitutability, capacities, and market rules.
- Strategy-proofness is generally one-sided, not universal.
- Stability can conflict with distributional or diversity objectives.

### Application

- school choice
- medical matching
- labor markets
- kidney exchange components
- resource assignment

### Basics

David Gale and Lloyd Shapley introduced deferred acceptance in 1962; Alvin Roth developed its empirical and market-design applications. Shapley and Roth received the 2012 economics prize.

### Paper / work evidence

- **Foundation (1962):** [College Admissions and the Stability of Marriage](https://doi.org/10.2307/2312726) · `wrk:92b07241891fd1fd67e7`
- **Recognition (2012):** [The Sveriges Riksbank Prize in Economic Sciences 2012](https://www.nobelprize.org/prizes/economic-sciences/2012/summary/) · `wrk:d45b0351e770db528dcd`

### Foundation relations

- `specializes` → `meta:economics-game-theory:revelation-principle` — Deferred acceptance is a mechanism with provable stability and incentive properties.

### Comment

A stable algorithm is not automatically a legitimate allocation rule. Priorities, preference construction, and policy constraints remain explicit design choices.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `d2e92e0432e98363f27ad25f28f28016600745933c0701eb8cd0ca471a576670`

---

## `meta:economics-game-theory:principal-agent-moral-hazard` — Delegation Creates Moral Hazard When Actions Are Hidden and Objectives Differ

**Epistemic type:** contract-theoretic mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `principal-agent`, `moral-hazard`, `contracts`, `monitoring`

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

- **Foundation (1979):** [Moral Hazard and Observability](https://doi.org/10.2307/3003320) · `wrk:20c508d3e2eb38a8dff6`
- **Extension (1982):** [Moral Hazard in Teams](https://doi.org/10.2307/1912702) · `wrk:efce48ddcab526bfb33f`

### Comment

Agentic AI systems make hidden-action problems concrete. More monitoring is not automatically optimal if it displaces useful autonomy or encourages metric gaming.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `a2d6f72ed9dda886eaaee63fdebaaef8eea2d26ef6dca99eca58b244a169a99c`

---

## `meta:economics-game-theory:black-scholes-merton` — Dynamic Replication Implies an Arbitrage-Free Price for Idealized Options

**Epistemic type:** option-pricing theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_foundation`  
**Introduced / developed:** 1973–present  
**Tags:** `black-scholes`, `option-pricing`, `replication`, `no-arbitrage`

### Argument & interpretation

Under continuous trading, frictionless markets, a lognormal underlying process with specified volatility, and the ability to hedge continuously, a derivative can be replicated by the underlying and a risk-free asset. No-arbitrage then determines its price through a partial differential equation and risk-neutral expectation.

### Boundary & conditions

- Volatility is not constant and returns have jumps, skew, and heavy tails.
- Trading is discrete and costly, and liquidity can disappear.
- Model risk and counterparty risk are outside the idealized replication result.

### Application

- derivatives
- risk management
- hedging
- financial engineering
- real options

### Basics

Fischer Black and Myron Scholes published the option-pricing model in 1973; Robert Merton generalized the continuous-time framework. Scholes and Merton received the 1997 economics prize.

### Paper / work evidence

- **Foundation (1973):** [The Pricing of Options and Corporate Liabilities](https://doi.org/10.1086/260062) · `wrk:0cc6d95f7aa27c39c5e1`
- **Extension (1973):** [Theory of Rational Option Pricing](https://doi.org/10.2307/3003143) · `wrk:9f1f2189e96b8379663e`
- **Recognition (1997):** [The Sveriges Riksbank Prize in Economic Sciences 1997](https://www.nobelprize.org/prizes/economic-sciences/1997/summary/) · `wrk:605286d728aef7e1cc94`

### Foundation relations

- `specializes` → `meta:economics-game-theory:competitive-equilibrium` — Dynamic replication implements the no-arbitrage Principle for options.

### Comment

This is a conditional theorem, not an empirical claim that market prices obey a lognormal model. Real use requires stress testing model and hedging errors.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `6f9ea8bcdf8810df3504b9cd84995ab1f01b37f3af5227b0628e5d01f4d6dd9f`

---

## `meta:economics-game-theory:institutions-prosperity` — Inclusive Constraints on Power and Secure Economic Institutions Support Long-Run Prosperity

**Epistemic type:** institutional-development proposition  
**Principia kind:** `empirical`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2024_landmark`  
**Introduced / developed:** 2001–present  
**Tags:** `institutions`, `prosperity`, `development`, `nobel-2024`

### Argument & interpretation

Persistent differences in prosperity are partly explained by institutions governing property, participation, public capacity, and constraints on elite extraction. Historical shocks can create institutional paths that persist, but effects operate through context-specific political and economic mechanisms.

### Boundary & conditions

- Institutional measures are multidimensional and endogenous.
- Historical instruments and colonial comparisons have contested exclusion restrictions.
- Culture, geography, state capacity, conflict, and global integration interact with institutions.

### Application

- development economics
- political economy
- governance
- state capacity
- institutional reform

### Basics

Acemoglu, Johnson, and Robinson developed influential empirical and historical accounts in the 2000s. The 2024 economics prize recognized Acemoglu, Johnson, and Robinson for studies of how institutions form and affect prosperity.

### Paper / work evidence

- **Foundation (2001):** [The Colonial Origins of Comparative Development](https://doi.org/10.1257/aer.91.5.1369) · `wrk:5df0f5314508cfe1847c`
- **Recognition (2024):** [The Sveriges Riksbank Prize in Economic Sciences 2024](https://www.nobelprize.org/prizes/economic-sciences/2024/summary/) · `wrk:26d5842ef81794735272`

### Foundation relations

- `specializes` → `meta:economics-game-theory:path-dependence-increasing-returns` — Historical institutional choices can persist and shape later outcomes.
- `depends_on` → `meta:foundations:transportability` — Institutional conclusions require careful cross-context transport.

### Comment

This should ground institutional reasoning without collapsing complex histories into a single institutional score or universal reform recipe.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `ef2d5b97366e81fd7a601f0968a1d3365e2aae3ff3e2f189a76a427e86a8e696`

---

## `meta:economics-game-theory:path-dependence-increasing-returns` — Increasing Returns Can Lock Systems into Path-Dependent Outcomes

**Epistemic type:** dynamic economic mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `replicated` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `path-dependence`, `increasing-returns`, `lock-in`, `network-effects`

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

- **Foundation (1989):** [Competing Technologies, Increasing Returns, and Lock-In by Historical Events](https://doi.org/10.1111/j.1467-9701.1989.tb00652.x) · `wrk:679ea3934f7cce54586e`
- **Historical Application (1985):** [Clio and the Economics of QWERTY](https://doi.org/10.2307/1805621) · `wrk:a56ba76b4e71acdea986`

### Comment

Lock-in claims are controversial when alternatives were not truly feasible or when performance differences are ignored. The reinforcing mechanism should be directly tested.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `7d529f626e3d05d3bb16aba27377060cdbf53855c16777d0fe62656e459ea778`

---

## `meta:economics-game-theory:transaction-costs-institutions` — Institutions Arise Partly to Reduce Transaction and Coordination Costs

**Epistemic type:** institutional economic proposition  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `transaction-costs`, `institutions`, `governance`, `coordination`

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

- **Foundation (1937):** [The Nature of the Firm](https://doi.org/10.1111/j.1468-0335.1937.tb00002.x) · `wrk:cafbc4fdffb425433402`
- **Foundation (1960):** [The Problem of Social Cost](https://doi.org/10.1086/466560) · `wrk:c3b68718dcb133fddbb5`

### Comment

The principle should motivate measurable coordination mechanisms rather than serve as a post hoc story explaining any institution.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `2e62f303763c1218935a592366f202b71546950a57357424ddd5989ea8ba9640`

---

## `meta:economics-game-theory:revelation-principle` — Mechanism Search Can Often Be Reduced to Truthful Direct Mechanisms

**Epistemic type:** mechanism-design theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `mechanism-design`, `revelation`, `truthfulness`, `incentives`

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

- **Foundation (1979):** [Incentive Compatibility and the Bargaining Problem](https://doi.org/10.2307/1910155) · `wrk:cc19a35388662eaedac9`
- **Canonical Application (1981):** [Optimal Auction Design](https://doi.org/10.1287/moor.6.1.58) · `wrk:d92a2964dd2ee2a1fb84`

### Comment

The principle is a search-space reduction, not a guarantee that the optimal mechanism is socially acceptable or behaviorally credible.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `349f6a8531580b284475d173ac46965e18c45df38fcc9916465a9af769a101a8`

---

## `meta:economics-game-theory:nash-equilibrium` — Nash Equilibrium Is Mutual Best Response, Not Automatic Optimality

**Epistemic type:** equilibrium existence theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `nash-equilibrium`, `best-response`, `strategic-interaction`, `game-theory`

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

- **Foundation (1950):** [Equilibrium Points in N-Person Games](https://doi.org/10.1073/pnas.36.1.48) · `wrk:6a8692844cb3dd2bd262`
- **Full Formulation (1951):** [Non-Cooperative Games](https://doi.org/10.2307/1969529) · `wrk:260957703685c21181b9`

### Comment

A new Principle invoking equilibrium should state the deviation class and why agents can find or learn the equilibrium. Nash equilibrium is often mistaken for a socially desirable outcome.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `da592a54002b502dea3d436e72e8de2598f4c4d965b383d6b0764f6ca40679d5`

---

## `meta:economics-game-theory:arrow-impossibility` — No Aggregation Rule Satisfies All Classical Fairness Axioms on Unrestricted Preferences

**Epistemic type:** social-choice impossibility theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `arrow-impossibility`, `social-choice`, `aggregation`, `fairness`

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

- **Foundation (1951):** [Social Choice and Individual Values](https://yalebooks.yale.edu/book/9780300179316/social-choice-and-individual-values/) · `wrk:58f3bdcbf164923df6ef`
- **Precursor (1950):** [A Difficulty in the Concept of Social Welfare](https://doi.org/10.1086/256963) · `wrk:46c737d18cfef2ca7e35`

### Comment

Impossibility theorems diagnose incompatible desiderata; they do not say collective choice is pointless. Principia should link every proposed aggregation rule to the axiom it sacrifices.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `d15112267bd40ae330d7dca26645ebad91802db3ea0b668549ce16d0b33ca614`

---

## `meta:economics-game-theory:marginal-optimization` — Optimal Choices Equate Marginal Benefit and Marginal Cost at an Interior Solution

**Epistemic type:** optimization proposition  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `marginalism`, `optimization`, `shadow-price`, `first-order-condition`

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

- **Foundation (1871):** [Theory of Political Economy](https://oll.libertyfund.org/titles/jevons-the-theory-of-political-economy) · `wrk:7f50df653582cd3aeb8c`
- **Formalization (1947):** [The Foundations of Economic Analysis](https://www.hup.harvard.edu/books/9780674313033) · `wrk:16764cb048d5bb7ef304`

### Comment

A reported optimum should include the feasible set, the objective, and evidence that the candidate is not merely a local stationary point.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `9c60fd6f0643a4b5f85afe5b65fb1b1a687b59eec062bf23a424feff26482902`

---

## `meta:economics-game-theory:pareto-efficiency-welfare` — Pareto Efficiency Separates Feasibility from Distributional Judgment

**Epistemic type:** welfare theorem and criterion  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `pareto-efficiency`, `welfare`, `distribution`, `feasibility`

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

- **Foundation (1939):** [The Foundations of Welfare Economics](https://doi.org/10.2307/1906922) · `wrk:b865073b44371dc1c34b`
- **Extension (1952):** [Some Aspects of the Welfare Economics of Public Finance](https://doi.org/10.2307/1884512) · `wrk:22fd53a3df63a422748c`

### Comment

Principia should not equate “Pareto efficient” with “best.” A child Principle must state whose utility, constraints, and distributional criteria are excluded.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `7ef9426f20b130f89dd1f2ab1925b7615af1a3f9e634c88ce085f057a5eb886f`

---

## `meta:economics-game-theory:lucas-critique` — Policy Changes Alter the Behavioral Rules Used to Predict Their Effects

**Epistemic type:** macro-causal proposition  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `lucas-critique`, `policy`, `invariance`, `adaptation`

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

- **Foundation (1976):** [Econometric Policy Evaluation: A Critique](https://doi.org/10.1016/S0167-2231(76)80003-6) · `wrk:7df9f50d91634a4eabf8`
- **Causal Refinement (2009):** [Causality: Models, Reasoning, and Inference](https://www.cambridge.org/core/books/causality/B0046844FAE10CBF274D4ACBDAEB5F5B) · `wrk:dc38af75cb042722e7db`

### Comment

This is a domain-specific version of intervention-induced distribution shift. A new Principle used for policy must identify which data-generating mechanisms are expected to remain stable.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `b09322d7087365b2cec6d7677c41088a98c2759ef82fe842372cdcc4c647c4c6`

---

## `meta:economics-game-theory:efficient-markets` — Prices Reflect Available Information to the Extent That Information Is Costly to Exploit

**Epistemic type:** efficient-markets hypothesis  
**Principia kind:** `hypothesis`  
**Maturity:** `contested` · **Stability:** `contested` · **Review:** `curated_draft`  
**Significance:** `nobel_level_influential_hypothesis`  
**Introduced / developed:** 1965–present  
**Tags:** `efficient-markets`, `asset-pricing`, `information`, `limits-to-arbitrage`

### Argument & interpretation

In competitive markets, predictable profit opportunities based on public information tend to be traded away, so prices incorporate available information conditional on information and trading costs. Stronger forms concern broader information sets and require stronger assumptions.

### Boundary & conditions

- Efficiency is relative to an information set, model of expected returns, costs, and institutional frictions.
- Bubbles, limits to arbitrage, behavioral biases, and slow diffusion can create persistent departures.
- Failure to forecast prices is not sufficient proof of efficiency.

### Application

- asset pricing
- portfolio management
- forecast evaluation
- market design
- information economics

### Basics

Eugene Fama formalized efficient-market categories in the 1960s and synthesized evidence in 1970; he shared the 2013 economics prize.

### Paper / work evidence

- **Foundation (1970):** [Efficient Capital Markets: A Review of Theory and Empirical Work](https://doi.org/10.2307/2325486) · `wrk:19f7b547f1b6207d7a90`
- **Recognition (2013):** [The Sveriges Riksbank Prize in Economic Sciences 2013](https://www.nobelprize.org/prizes/economic-sciences/2013/summary/) · `wrk:613e8c1ee26d0a14cd6e`

### Foundation relations

- `depends_on` → `meta:economics-game-theory:adverse-selection` — Information acquisition and asymmetry determine which efficiency form is plausible.
- `contradicts` → `meta:socio-technical-systems:information-cascades` — Herding can create correlated errors not eliminated immediately by prices.

### Comment

Treat efficiency as a joint hypothesis about prices and an expected-return model. It should not be converted into a blanket claim that markets are always correct.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `83eb1eebeb6a5ddcc054b0f2f9dc4c436eaf539e489dcd0e74eab6beb25042cb`

---

## `meta:economics-game-theory:adverse-selection` — Private Information Can Drive High-Quality Participants from a Market

**Epistemic type:** information-economic mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `adverse-selection`, `asymmetric-information`, `market-unravelling`, `selection-bias`

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

- **Foundation (1970):** [The Market for Lemons: Quality Uncertainty and the Market Mechanism](https://doi.org/10.2307/1879431) · `wrk:2e4c862daab6a08a5845`
- **Extension (1976):** [Equilibrium in Competitive Insurance Markets](https://doi.org/10.2307/1885326) · `wrk:ba3357b1b62fb593084b`

### Comment

Selection mechanisms can mimic treatment effects or performance differences. New Principles based on observed participants should ask which types were excluded before measurement.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `5fa26bf67450822e1374d19b0c82ba0ec34efc9b7fe2d03a340f0754f897a9b1`

---

## `meta:economics-game-theory:bilateral-trade-impossibility` — Private Information Can Make Efficient Bilateral Trade Incompatible with Incentives and Budget Balance

**Epistemic type:** mechanism-design impossibility theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `bilateral-trade`, `impossibility`, `private-information`, `budget-balance`

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

- **Foundation (1983):** [Efficient Mechanisms for Bilateral Trading](https://doi.org/10.1016/0022-0531(83)90048-0) · `wrk:1e937d8cf09a8ed7fb1a`

### Comment

The theorem is useful for evaluating unrealistic platform claims that promise perfect efficiency, voluntary participation, truthful revelation, and no subsidy simultaneously.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `3f050c36382195dac6b49f36cbaa1b34842f015c93340a3bb12f8a71c84f17ab`

---

## `meta:economics-game-theory:bounded-rationality` — Rational Choice Is Constrained by Information, Computation, and Search

**Epistemic type:** behavioral and computational proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `bounded-rationality`, `satisficing`, `heuristics`, `computation`

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

- **Foundation (1955):** [A Behavioral Model of Rational Choice](https://doi.org/10.2307/1884852) · `wrk:988801abe2b703df04b4`
- **Extension (1956):** [Rational Choice and the Structure of the Environment](https://doi.org/10.1037/h0042769) · `wrk:c8627d3b5cfe0260f53c`

### Comment

Labeling behavior “irrational” is less informative than modeling the resource constraint and representation. The same principle applies to LLM and multi-agent reasoning budgets.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `5ca7d152543492ab54c8e1d71f724b88f118354276317ead75519740d750a4c6`

---

## `meta:economics-game-theory:scarcity-opportunity-cost` — Scarcity Makes Every Choice an Opportunity-Cost Trade-off

**Epistemic type:** foundational economic proposition  
**Principia kind:** `heuristic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `scarcity`, `opportunity-cost`, `allocation`, `trade-off`

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

- **Foundation (1932):** [An Essay on the Nature and Significance of Economic Science](https://mises.org/library/book/essay-nature-and-significance-economic-science) · `wrk:326a7952db219f74b793`
- **Formalization (1939):** [The Foundations of Welfare Economics](https://doi.org/10.2307/1906922) · `wrk:b865073b44371dc1c34b`

### Comment

Opportunity cost is often invoked rhetorically without identifying the counterfactual alternative. In Principia, a child Principle should name the budget, the excluded alternative, and the decision horizon.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `835357f52982472017f2f8a3258b280820f603e7b9cf4c32b5030c6fbe29d7d6`

---

## `meta:economics-game-theory:creative-destruction-growth` — Sustained Growth Can Arise from Innovation that Replaces Existing Technologies

**Epistemic type:** endogenous-growth mechanism  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_2025_landmark`  
**Introduced / developed:** 1992–present  
**Tags:** `creative-destruction`, `innovation`, `growth`, `nobel-2025`

### Argument & interpretation

Firms invest in quality-improving innovations because temporary rents reward successful entry. Each innovation raises productivity while displacing incumbent products and firms; repeated creative destruction can generate sustained endogenous growth when institutions preserve entry, knowledge accumulation, and incentives.

### Boundary & conditions

- Market power can both fund innovation and block future entry.
- Adjustment imposes losses on workers, firms, and regions.
- Growth depends on finance, skills, competition, knowledge spillovers, and political institutions.

### Application

- innovation policy
- industrial organization
- productivity
- technology transitions
- competition policy

### Basics

Aghion and Howitt formalized Schumpeterian creative destruction in 1992. The 2025 economics prize recognized Aghion and Howitt for this theory and Joel Mokyr for the prerequisites of sustained technological growth.

### Paper / work evidence

- **Foundation (1992):** [A Model of Growth Through Creative Destruction](https://doi.org/10.2307/2951599) · `wrk:5fcb540658bd3c4af769`
- **Recognition (2025):** [The Sveriges Riksbank Prize in Economic Sciences 2025](https://www.nobelprize.org/prizes/economic-sciences/2025/summary/) · `wrk:23495ae57fda4032ed0e`

### Foundation relations

- `generalizes` → `meta:socio-technical-systems:technology-s-curves` — Innovation waves replace incumbent trajectories.
- `refines` → `meta:economics-game-theory:transaction-costs-institutions` — Competition and temporary rents jointly shape innovation incentives.

### Comment

The Principle does not imply that all disruption is socially beneficial; transition costs, concentration, and institutional capture are essential boundary nodes.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `438b389a2174e49120332794b689c49a8c0289b35235c8cc657b5c0887cd30a3`

---

## `meta:economics-game-theory:modigliani-miller` — Under Frictionless Markets, Capital Structure Does Not Change Total Firm Value

**Epistemic type:** corporate-finance theorem  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_foundation`  
**Introduced / developed:** 1958–present  
**Tags:** `modigliani-miller`, `capital-structure`, `irrelevance`, `finance`

### Argument & interpretation

With perfect capital markets, no taxes, no bankruptcy or agency costs, symmetric information, and equivalent borrowing opportunities, changing the mix of debt and equity reallocates risk and returns but does not create aggregate firm value. Financing matters through deviations from those assumptions.

### Boundary & conditions

- Taxes, distress, agency conflicts, asymmetric information, regulation, and market segmentation break irrelevance.
- The theorem concerns value, not liquidity, control, or stakeholder distribution.
- Dynamic financing constraints and incomplete contracts require richer models.

### Application

- corporate finance
- capital structure
- project finance
- banking
- valuation

### Basics

Franco Modigliani and Merton Miller published the theorem in 1958; both later received the economics prize for foundational finance work.

### Paper / work evidence

- **Foundation (1958):** [The Cost of Capital, Corporation Finance and the Theory of Investment](https://doi.org/10.2307/2975974) · `wrk:f02f608091012dd1a573`
- **Recognition (1985):** [The Sveriges Riksbank Prize in Economic Sciences 1985](https://www.nobelprize.org/prizes/economic-sciences/1985/summary/) · `wrk:45ef3100b29bd95967d3`

### Foundation relations

- `analogous_to` → `meta:economics-game-theory:competitive-equilibrium` — Both use frictionless replication arguments to derive invariance.
- `specializes` → `meta:foundations:boundary-first-generalization` — The theorem’s usefulness lies in making boundary violations explicit.

### Comment

Irrelevance theorems are highly valuable Meta-Principles because the empirically important mechanisms are exactly the assumption violations.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `2fe1e1d32a1df408f54669485a6bf52c411b90598483792c32272f99d06d8ef6`

---

## `meta:economics-game-theory:externalities-public-goods` — Unpriced External Effects Separate Private and Social Optima

**Epistemic type:** welfare-economic proposition  
**Principia kind:** `mechanistic`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `canonical_foundation_v1`  
**Introduced / developed:** See Basics  
**Tags:** `externality`, `public-good`, `free-riding`, `social-cost`

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

- **Foundation (1954):** [The Pure Theory of Public Expenditure](https://doi.org/10.2307/1925895) · `wrk:7d24512c2f757fd421d0`
- **Institutional Boundary (1960):** [The Problem of Social Cost](https://doi.org/10.1086/466560) · `wrk:c3b68718dcb133fddbb5`

### Comment

A child Principle should identify who bears the external effect, whether exclusion is feasible, and whether the proposed remedy creates new distortions.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v1` · **Version:** 1 · **Digest:** `974f73c75f4555d5b36c9f93fe2d82383137d229cb5c07ff136d8e22df7433a0`

---

## `meta:economics-game-theory:coase-theorem` — When Property Rights Are Clear and Transaction Costs Vanish, Bargaining Can Internalize Externalities

**Epistemic type:** institutional proposition  
**Principia kind:** `theorem`  
**Maturity:** `established` · **Stability:** `high` · **Review:** `curated_draft`  
**Significance:** `nobel_level_foundation`  
**Introduced / developed:** 1960–present  
**Tags:** `coase`, `transaction-costs`, `property-rights`, `externalities`

### Argument & interpretation

If rights are well defined, information is adequate, bargaining is costless, and agreements are enforceable, affected parties can negotiate an efficient allocation regardless of the initial assignment of rights. Initial rights still determine distribution, and real institutions matter because transaction costs are rarely zero.

### Boundary & conditions

- The benchmark assumes negligible search, bargaining, enforcement, and strategic costs.
- Many parties, asymmetric information, wealth constraints, and nonconvexities can prevent efficient bargaining.
- Efficiency does not imply fairness or political legitimacy.

### Application

- externalities
- law and economics
- environmental policy
- platform governance
- contract design

### Basics

Ronald Coase developed the argument in “The Problem of Social Cost” (1960) and received the 1991 economics prize for transaction-cost and property-rights analysis.

### Paper / work evidence

- **Foundation (1960):** [The Problem of Social Cost](https://doi.org/10.1086/466560) · `wrk:c3b68718dcb133fddbb5`
- **Recognition (1991):** [The Sveriges Riksbank Prize in Economic Sciences 1991](https://www.nobelprize.org/prizes/economic-sciences/1991/summary/) · `wrk:2226ebab79d956943bbc`

### Foundation relations

- `refines` → `meta:economics-game-theory:externalities-public-goods` — The benchmark specifies conditions under which externalities can be privately internalized.
- `motivates` → `meta:economics-game-theory:revelation-principle` — When bargaining conditions fail, institutions and mechanisms must substitute.

### Comment

The theorem is best treated as a diagnostic benchmark: it directs attention to the concrete transaction costs that make institutions necessary.

**Trace:** `trace:2026-08-21:gpt-5.6-pro:meta-principles-v2-expansion` · **Version:** 1 · **Digest:** `d59cfb3f0360bd852bf708a01826871fdc7c4b1b20b5633f500607995baf19fa`

---

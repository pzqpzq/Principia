# Reviewer guide

This document is outside scenario inputs. The corpus has no hidden answer key and no required number of positive discoveries.

## Inspect the scientific unit first

Start with each task card, source inventory and native-format evidence. Verify the input/output distinction: a calculated friction coefficient, fitted toughness, reconstructed temperature, inferred flux, standard-score transformation or imputed series is not an independent measurement of its own inputs. Confirm group identifiers before assessing a held-out result. Insufficient independent groups can justify abstention or a narrower within-system claim.

Prior publications, source figure tables and supplied fitted models are disclosed evidence. A system must say whether a relationship is reproduction, a supported extension, or a novelty candidate. Deposit recency alone does not imply that measurements are recent or unexplored.

## Possible equation families

These are prompts for reviewer scrutiny, not target answers or guarantees:

| Scientific setting | Families worth comparing when supported | Common false positives |
|---|---|---|
| Device reliability and semiconductor transport | Stateful response models, activation-temperature terms, dose/history-dependent degradation, saturation | Reusing a source fit, confusing simulated potentials with measured response, treating sweep rows as devices |
| Rheology, friction, mechanics and fatigue | Dimensionally valid constitutive laws, relaxation spectra, rate/temperature dependence, survival with censoring | Ignoring apparatus compliance, response-derived descriptors, discarded failed specimens |
| Flow, waves and energy systems | Conservation with independently measured terms, response/lag models, nondimensional regime relations | Accounting identities, interpolated outputs counted as extra sensors, virtual turbine power as replication |
| Biological kinetics and bioprocesses | Coupled rate equations, saturating response, substrate interactions, donor/batch random effects | Technical replicates as biological replication, aligned data and raw data double-counted, model-derived flux as ground truth |
| Neuroscience and biomedical sensing | Condition-dependent transfer functions, temporal response models, interpretable sensor-error laws | Cells/events/pixels as independent animals, illustrative movies as replicate evidence, clinical claims from one subject |
| Ecology, ocean and atmosphere | Bounded environmental response, hysteresis/lag, profiles and spatial correlation with group uncertainty | Sensor QC ignored, seasonal confounding, mathematical identities among derived weather variables |
| Social and behavioral studies | Hierarchical response models, dynamic choice/contribution models, weighted associations | Payoff identities, interacting players split between train/test, unweighted population claims, causal language without identification |
| Computer/network experiments | Workload-dependent cost and loss dynamics, constrained queueing/latency, failure-aware runtime models | Mean-imputed rows treated as observed, target throughput substituted for achieved throughput, successful-run selection |
| Exact mathematics and optimization | Independent certificate/proof checks, structural bounds, instance-based counterexamples | Treating generated objects as noisy physical experiments, checking only successful certificates, supplied formula renamed as discovery |

For every proposed equation, ask whether an equally simple established model fits as well, whether units and scales are coherent, and whether a falsifying condition was actually withheld. A flexible surrogate can predict well without yielding an interpretable principle; a compact expression can be false outside its narrow support. Report both aspects separately.

## Cases requiring particular care

- 03, 07, 08, 20, 45, 46, 49, 58, 63, 65, 68 and 69 have explicit single-system/event or sparse-population constraints.
- 28, 29, 51, 52, 59, 65 and 70 include computational/model-derived or unresolved auxiliary products alongside measurements. Their exact roles must be identified before use.
- 39 requires PIAAC design weights and plausible-value treatment. Cases 14, 15 and 42 also require survey-design-aware inference.
- 71 contains original and author-aligned representations. 75 has only four donor groups. 77 and 93 contain many cellular events within few independent samples.
- 79 has known treatment confounding. 83 confounds species and recording season. 91 preserves three invalid-clock runs and their author-imputed alternatives.
- 60 needs a compatible native reader or the supplied bounded MAT inspection method; authenticated source bytes alone do not prove compatibility with a particular application.
- 84 contains surface mechanics, not the associated cellular-response experiment. 97 contains videos and figure-source DAT tables rather than a verified complete raw trajectory table.
- 05 and 98 are exact computational mathematics cases. Omitted oversized packages cannot support claims about complete excluded certificate/object collections.

Use the case cards for the full limitations, dates, source processing, permitted interpretations and grouping design. This guide supplies no ground-truth coefficients or expected discoveries.

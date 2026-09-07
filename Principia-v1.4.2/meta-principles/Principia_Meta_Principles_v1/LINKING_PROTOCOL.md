# Linking Protocol for New Principles

This protocol turns the Meta-Principles corpus into a reasoning foundation for newly extracted Principles. It is designed for Principia agents and human curators. A link is an explicit scientific claim about dependence or scope; it is not merely semantic similarity.

## 1. Normalize the new Principle

Before retrieval, represent the new Principle as:

```yaml
claim: the relationship being asserted
claim_class: empirical_association | causal_mechanism | design_rule_or_intervention | boundary_or_tradeoff | formal_proposition
subject_system: system or population
input_or_driver: cause, intervention, assumption, or design choice
outcome: response or consequence
direction: increase, decrease, bound, equivalence, threshold, impossibility, etc.
conditions: conditions required by the source
boundary: known exclusions and failure regimes
evidence: exact supporting records
testability: observation or intervention that could weaken the claim
```

Do not link an incomplete paper summary. If the driver, outcome, scope, or evidence cannot be recovered, quarantine the candidate before Meta-Principle grounding.

## 2. Retrieve candidate roots

Retrieve 5–12 candidates using three independent channels:

1. **Area and tag retrieval** — direct domain roots such as `ai-ml`, `physics`, or `medicine-epidemiology`.
2. **Argument retrieval** — lexical or embedding similarity over `argument`, `boundary`, and `applications`.
3. **Structural retrieval** — search by claim class and scientific role: conservation, identifiability, trade-off, feedback, equilibrium, selection, scale, information, optimization, measurement, or causal design.

At least one candidate should come from `foundations`, `mathematics-logic`, `statistics-causality`, or `information-control-complexity`. This prevents a chain composed only of neighboring paper-level claims.

## 3. Assign relation direction

Use the narrowest defensible relation:

| Relation | Test |
| --- | --- |
| `specializes` | The new Principle is a scoped instance of the Meta-Principle and inherits its logic under additional conditions. |
| `depends_on` | The new Principle requires the theorem, assumption, measurement condition, or limit expressed by the Meta-Principle. |
| `refines` | The new Principle sharpens a mechanism, boundary, quantitative law, or applicability condition. |
| `motivates` | The Meta-Principle explains why the new method, experiment, or safeguard is needed, but is not a premise of its truth. |
| `generalizes` | The new Principle truly covers the Meta-Principle as a special case; use rarely and require strong review. |
| `analogous_to` | The structures are similar, but validity does not transfer without new evidence. |
| `supports` | Independent evidence or formal reasoning directly increases support for the target. |
| `contradicts` | The new evidence conflicts with the target within overlapping scope; differing scopes alone are not contradiction. |

Semantic similarity alone should normally produce `analogous_to` or no relation—not `supports`.

## 4. Check boundary inheritance

For every proposed parent, compare:

```text
parent conditions ∩ new conditions
parent exclusions ∩ new scope
measurement definitions
scale and timescale
population or environment
intervention and comparator
resource and information assumptions
```

A `specializes` or `depends_on` link fails when the new claim violates a parent exclusion. In that case, either narrow the new claim, select a different root, or create a reviewed `contradicts` relation.

## 5. Build a short reasoning chain

Prefer 2–4 high-information roots rather than a dense cloud of weak links:

```text
new paper-level Principle
    ├── domain mechanism or law
    ├── statistical / causal requirement
    ├── cross-domain constraint or trade-off
    └── optional formal theorem or information bound
```

A strong chain typically contains:

- one **mechanism or structural root**;
- one **epistemic root** covering evidence, measurement, causality, or uncertainty;
- one **boundary root** covering scale, transport, resource limits, or trade-offs when material.

## 6. Run reasonableness gates

A proposed chain passes only when:

1. **Claim coverage:** the parents explain a material part of the new claim, not only shared vocabulary.
2. **Directionality:** each edge has a stated direction and rationale.
3. **Scope compatibility:** no parent boundary is silently violated.
4. **Evidence independence:** parent and child support are not circular restatements of the same extraction.
5. **No theorem laundering:** an empirical claim does not become certain merely because it is linked to a theorem.
6. **Conflict visibility:** credible contradictory roots or evidence remain visible.
7. **Minimality:** removing a parent would remove a distinct explanatory or validity constraint.
8. **Testability:** the chain identifies at least one condition under which the child should weaken or fail.

## Recommended output

```json
{
  "new_principle_id": "candidate:...",
  "root_links": [
    {
      "meta_id": "meta:...",
      "relation_type": "specializes",
      "rationale": "...",
      "inherited_conditions": ["..."],
      "boundary_conflicts": [],
      "evidence_independent": true
    }
  ],
  "chain_status": "grounded | partial | conflicting | ungrounded",
  "unresolved_questions": ["..."],
  "recommended_test": "..."
}
```

`grounded` means the reasoning chain is explicit and scope-compatible. It does not certify that the child Principle is empirically true.

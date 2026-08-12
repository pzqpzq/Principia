# Trustworthy generation and mathematics

Principia v1.3.3 treats evidence identity, live-model provenance, and
mathematical syntax as release gates rather than presentation details.

## Canonical evidence registry

The generation prompt is built from a minimal registry. A selectable record
contains only:

```text
work_id
work_title
kind
record_id
record_type
title
grounded text
```

It does not contain model names, generator mode, candidate/evolution trace,
warnings, token usage, provider configuration, or progress metadata. These
fields remain operational metadata and cannot become scientific evidence.

Every generated reference must resolve exactly to the tuple
`(work_id, kind, record_id)`. Principia hydrates `title`, `record_type`, and
quoted text from the canonical selected record; it does not trust a
model-generated excerpt. The public helpers are:

```python
registry = pc.canonical_evidence_registry(evidence)
issues = pc.validate_evidence_references(raw_references, evidence)
if issues:
    raise ValueError(issues)
hydrated = pc.hydrate_evidence_references(raw_references, evidence)
```

`Idea.evidence_work_ids` is derived from references actually cited by the final
Idea Card. The broader selected-work set remains in generation metadata. A
standalone `ValidationPlan` consumes the same hydrated references, so its kind,
record ID, text, and work ID cannot drift from the idea.

## No generator-as-evidence contamination

SciDialect-Evo, candidate IDs, selection labels, model names, and prompt
strategy are allowed in trace and mode metadata. They are rejected as proposal
content or scientific evidence unless the selected research record itself
supports the term. Legitimate source phrases—such as “learned machine
dialects”—remain valid when they come from the corpus.

If generator-only terminology leaks into scientific content, Principia makes
one evidence-grounded repair call. Persistent contamination fails generation;
there is no word-replacement sanitizer that could conceal the defect.

Comparison receives a content-level projection of the generated idea and only
canonical prior-idea records. Mode, trace, model configuration, and usage do not
enter the comparison prompt.

## No production templates

`model="auto"` requires a callable configured provider. Principia fails before
persisting an extraction or idea if credentials or the provider endpoint are
unavailable. It does not replace live output with a fixed title, stock evidence
gate, injected equation, unrelated benchmark, or canned methodology.

Incomplete, off-domain, ungrounded, or structurally invalid live output gets
one repair call grounded in the same evidence. If required defects remain, the
stage fails without saving the invalid record.

Explicit `model="mock"` is retained for deterministic tests only. Mock records
carry `execution_origin="mock_fixture"` and cannot pass live-showcase QA.

## Strict SciDialect-Evo

Strict `scidialect-evo` has three observable stages:

1. Generate exactly three candidates with IDs and four scored criteria, each
   with a concise rationale.
2. Critique and evolve exactly the strongest two candidates, recording the
   changes without hidden chain-of-thought.
3. Select one evolved candidate ID with a rationale and produce the final Idea
   Card.

`SciDialectConfig(allow_degraded_fallback=False)` is the live default. Degraded
mode is explicit opt-in and may reuse only real LLM output. It never manufactures
a template candidate, evolution, or final card.

## Untrusted source data

Retrieved pages and local documents are quoted research data. Every LLM stage
is instructed to ignore embedded commands, role changes, tool requests, and
format overrides. Prompt-injection tests cover extraction, consolidation,
generation, and comparison. Portable local identifiers are supplied when
needed; absolute paths are not.

## Mathematical syntax

All mathematical content passes through one shared tokenizer and validator.
Inline mathematics uses exactly `$...$`; display equations use exactly
`$$...$$`. Supported Unicode notation is normalized to LaTeX commands, for
example:

| Input | Canonical LaTeX |
| --- | --- |
| `σ`, `α`, `τ` | `\sigma`, `\alpha`, `\tau` |
| `≤` | `\le` |
| `·` | `\cdot` |
| `Var` in an operator position | `\operatorname{Var}` |

The validator rejects nested or unbalanced math delimiters, unmatched braces,
control characters, code fences inside math, bare `==`, malformed commands,
and unsafe JSON backslashes. `pylatexenc` parses each retained formula.

Every subscript and superscript uses an explicit braced group, including a
single character or digit. For example, write $R_{cf}$, $f_{0}$, and
$x^{2}$. Unbraced inputs such as `R_cf`, `f_0`, and `x^2` are rejected as
noncanonical. Repeated scripts such as `L_depth_order` are not guessed into a
meaning: they require an evidence-grounded rewrite such as
$\mathcal{L}_{\mathrm{depth\text{-}order}}$.

For example, the inline variance expression
$\operatorname{Var}(X) \le \sigma^{2}$ and the display equation

$$
\tau = \frac{Q}{\pi f_{0}}
$$

use the required delimiters and balanced commands.

Invalid generated mathematics receives one evidence-grounded repair. If it is
still invalid, generation fails; Principia does not inject a substitute
formula. Release QA also compiles every retained formula with strict KaTeX,
including Idea Cards, validation plans, README showcases, and notebooks.

## Validation plans

`build_validation_plan(...)` creates the public `ValidationPlan` model from an
existing result without an additional provider call. Its JSON and Markdown
forms share a schema version, idea ID/title, goal, thesis, validation protocol,
comparators/baselines, metrics, risks, assumptions, canonical evidence
references, model/mode, and timestamps.

`Workspace.project(...)` writes matching `validation_plan.json` and
`validation_plan.md` files beside the Idea Card in `outputs/<idea_id>/`, while
the works and features remain shared in `workspace/`. The backward-compatible
legacy export writes the same two files in its canonical, per-idea, and latest
locations. Release tests verify JSON/Markdown parity and portable paths.

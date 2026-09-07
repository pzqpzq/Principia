# Principia Meta-Principles Corpus v1

A cross-disciplinary foundation layer for the Principia Principles Cloud. The corpus contains **232 Meta-Principles across 14 areas**, supported by **412 unique public works** and **147 curated relation seeds**.

## Purpose

Specific Principles extracted from papers are often too local to expose their deepest assumptions. This corpus supplies stable parent concepts—limits, invariances, causal requirements, trade-offs, conservation laws, selection mechanisms, information bounds, and proof constraints—so that a new Principle can be attached to a more fundamental reasoning chain.

The corpus follows the Principles Cloud product model: Global knowledge is provenance-linked and versioned; Local knowledge can specialize it without private-data upload; Scenario overlays can temporarily challenge or modify relations without mutating canonical records. This is aligned with the v1.4 design contract.

## Contents

- `areas/`: one human-readable Markdown file per area.
- `data/meta_principles.jsonl`: one complete machine-readable record per line.
- `data/works.jsonl`: deduplicated public work registry.
- `data/relations.jsonl`: curated cross-principle relation seeds.
- `schema/meta_principle_v1.schema.json`: JSON Schema.
- `CATALOG.json`: counts, paths, and tags.
- `IMPORT_GUIDE.md`: mapping into the current Principia v1.4 domain models.
- `QA_REPORT.md`: validation results and limitations.
- `GENERATION_TRACE.json`: corpus-level provenance.

## Area index

| Area | Meta-Principles | Evidence links | File |
| --- | ---: | ---: | --- |
| Cross-Domain Scientific Reasoning | 21 | 42 | [`00_cross_domain_scientific_reasoning.md`](areas/00_cross_domain_scientific_reasoning.md) |
| Mathematics and Logic | 16 | 30 | [`01_mathematics_and_logic.md`](areas/01_mathematics_and_logic.md) |
| Statistics and Causal Inference | 17 | 33 | [`02_statistics_and_causal_inference.md`](areas/02_statistics_and_causal_inference.md) |
| Artificial Intelligence and Machine Learning | 17 | 34 | [`03_artificial_intelligence_and_machine_learning.md`](areas/03_artificial_intelligence_and_machine_learning.md) |
| Computer Science and Distributed Systems | 14 | 23 | [`04_computer_science_and_distributed_systems.md`](areas/04_computer_science_and_distributed_systems.md) |
| Physics | 14 | 28 | [`05_physics.md`](areas/05_physics.md) |
| Chemistry and Materials Science | 15 | 30 | [`06_chemistry_and_materials_science.md`](areas/06_chemistry_and_materials_science.md) |
| Biology, Evolution, and Ecology | 16 | 32 | [`07_biology_evolution_and_ecology.md`](areas/07_biology_evolution_and_ecology.md) |
| Neuroscience and Cognition | 15 | 29 | [`08_neuroscience_and_cognition.md`](areas/08_neuroscience_and_cognition.md) |
| Information, Control, and Complex Systems | 16 | 31 | [`09_information_control_and_complex_systems.md`](areas/09_information_control_and_complex_systems.md) |
| Economics and Game Theory | 19 | 37 | [`10_economics_and_game_theory.md`](areas/10_economics_and_game_theory.md) |
| Medicine and Epidemiology | 17 | 34 | [`11_medicine_and_epidemiology.md`](areas/11_medicine_and_epidemiology.md) |
| Earth and Climate Science | 17 | 34 | [`12_earth_and_climate_science.md`](areas/12_earth_and_climate_science.md) |
| Engineering and Optimization | 18 | 35 | [`13_engineering_and_optimization.md`](areas/13_engineering_and_optimization.md) |

## Epistemic policy

All records ship as `curated_draft`. Formal theorems and historically established laws may carry `maturity: established`, but this does not bypass Principia review. No numeric quality score is fabricated. Promotion into a reviewed Global package should require domain-expert review, source-link verification, relation validation, and compatibility checks with the current package schema.

## Linking a new Principle

For a new Principle $p$, retrieve candidate Meta-Principles $m_i$ by area, tags, and lexical/semantic similarity, then classify the relation direction. Common patterns are:

- `p specializes m`: $p$ is a scoped realization of a broad Meta-Principle.
- `p depends_on m`: $p$ requires a limit, assumption, or theorem expressed by $m$.
- `m motivates p`: $m$ explains why the method or experiment represented by $p$ is needed.
- `p refines m`: $p$ sharpens the boundary, mechanism, or quantitative form of $m$.
- `p contradicts m`: $p$ supplies credible evidence against the stated scope of $m$.
- `p analogous_to m`: the structural similarity is useful, but transfer is not assumed.

The linking questions inside every entry are intended as a deterministic first-pass checklist for agents and curators.

## Recommended entry points

- Start with [`COVERAGE_MATRIX.md`](COVERAGE_MATRIX.md) to select an Area.
- Use [`LINKING_PROTOCOL.md`](LINKING_PROTOCOL.md) when grounding a newly extracted Principle.
- Inspect [`FOUNDATION_MAP.md`](FOUNDATION_MAP.md) for cross-area roots and relation hubs.
- Use [`data/principia_candidate_projection.jsonl`](data/principia_candidate_projection.jsonl) for the closest projection to current v1.4 `CandidatePrinciple` contracts.
- Run [`REVIEW_CHECKLIST.md`](REVIEW_CHECKLIST.md) before Global package publication.

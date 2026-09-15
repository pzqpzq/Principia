# Changelog

## 0.1.1 — download compatibility, 2026-09-15

- Download selected LFS payloads during sparse checkout. This avoids the whole-tree blob scan performed by `git lfs pull` with some older Git versions in partial clones.
- Correct the PowerShell ordering so skip-smudge is cleared before selecting cases.
- Preserve all scientific source assets, case revisions and the published 0.1.0 tag; this is a documentation and distribution patch.
- The repository also excludes benchmark tags from the legacy v1.3 workflow. The initial tag exposed that workflow's missing historical application directory; the independent benchmark integrity workflow passed.

## 0.1.0 — public release, 2026-09-15

- Publish the 100 owner-accepted scenarios under `ASD-benchmarks/`, with all 1,685 scientific assets unchanged from the accepted candidate.
- Add a public overview, selective Git LFS download instructions, contributor guidance and publication integrity checks.
- Finalize curator documentation and tooling terms; retain source-specific rights and attribution.
- Update publication metadata and the release inventory. The original acquisition reports remain evidence of the checks performed; their historical byte totals may differ from the public documentation edition.
- No discoveries, system rankings or new scientific validation are introduced by publication.

## 0.1.0-rc.1 — local candidate, 2026-09-15

- Add 50 independently sourced scenarios, IDs 51–100, preserving native files and source-defined selections.
- Preserve the earlier 50 local folders; substitute a licensed graph-certificate dataset in benchmark slot 05, revision 2, while retaining the original GEO folder outside the release.
- Record access-driven substitutions for planned additions 86, 93 and 99.
- Add a uniform catalog, 100 task cards, asset/license/acquisition manifests, evaluation protocol, reviewer guide, output schema, integrity/replay tooling and an explicit release allowlist.
- Separate corpus acceptance, native-reader coverage, application compatibility and scientific validation. No discovery run, comparison, leaderboard or public release is included.

The unified history also retains five substitutions made during the earlier 21–50 acquisition (29, 30, 31, 36, 49), distinctly labeled as previous work. During this expansion, 86, 93 and 99 use reserves; slot 05 has a licensed release replacement; 19 has a coherent archive-selection revision. Original local folders 01–50 are unchanged.

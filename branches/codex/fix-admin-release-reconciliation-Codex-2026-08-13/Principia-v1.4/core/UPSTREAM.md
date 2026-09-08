# Upstream Integration Record

This release tree is a framework-only derivative of the `Principia-v1.3/`
subdirectory at upstream commit
`11a03027855de9e25951cc012fd03730cf4a4ab7`. That commit contains merged pull
request #8, which introduced the broader semantic retrieval implementation that
v1.3.3 hardens and extends. The Jul16 private-corpus, canonical-evidence,
strict-math, controllable-pipeline, project-layout, and showcase revisions remain part of the
same local 1.3.3 release candidate; they do not change the upstream seed or
claim a new upstream commit.

The files in this release directory are licensed under the MIT License in
[`LICENSE`](LICENSE). The Apache-2.0 license at the root of the upstream
multi-project repository applies to that repository root; it does not replace
the framework subproject's own MIT license.

The local release workflow never publishes automatically. GitHub and PyPI
publication require an explicit maintainer action after acceptance; the
published artifacts can therefore be traced to the checks and hashes recorded
in `RELEASE_QA.md`.

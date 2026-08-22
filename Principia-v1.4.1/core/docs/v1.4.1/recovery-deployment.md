# Recovery and deployment

Cloud sync builds beside the active cache. A corrupt full or delta asset fails
closed and leaves the active pointer unchanged. One previous verified snapshot is
always retained for one-click rollback; the cache keeps at most five generations.

The `Global Cloud validation` workflow is a required PR check. After a reviewed PR
auto-merges, `Publish Global Cloud release` validates canonical records again,
reuses vectors by content digest, embeds changed records under the pinned 1,024-D
Qwen contract, uploads a full snapshot and optional delta, redownloads them, checks
`SHA256SUMS`, and only then deploys Pages controls. Configure the repository secret
`PRINCIPIA_EMBEDDING_API_KEY` and enable GitHub Pages through Actions. Branch
protection should require Global Cloud validation and normal CI before auto-merge.

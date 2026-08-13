# Local Literature Discovery

Local Literature Discovery turns selected documents in a visible private folder
into evidence-linked, unassessed Candidate Principles:

```text
choose/create folder → index documents → exact selection
                     → extraction → evidence checks → Principles Explorer

optional: research question → metadata search → selection → safe acquisition
                                                     ↘ chosen private folder
```

The workflow is deliberately not generic chat. Every displayed Candidate is a
typed scientific claim with a bounded scope, a canonical Work reference, an
exact evidence excerpt, a SHA-256 trace, and an explicit `unassessed` label.

## Use it in the product UI

1. Start Principia and open **Local Discovery**.
2. Choose, connect, or create a private folder. Its exact path, document counts,
   availability, and **Open Folder** action remain visible.
3. Index the folder and select all, the filtered documents, or an exact subset.
4. Optionally enter a research focus, then check the provider, model, egress
   disclosure, and run limits. Area is not an extraction input.
5. Extract reusable findings from exactly the selected documents. Progress,
   retries, token usage, held-back counts, and partial results survive refresh.
6. Inspect exact evidence or choose **Open in Principles Explorer**.

If the folder needs papers, open **Find public literature**. Search is metadata
only. Review and edit the usable set, then acquire permitted representations into
the chosen folder. Acquisition never starts extraction or makes an LLM call.

## What gets downloaded

Principia downloads full text only from a recorded source-specific open-access
location. It validates HTTPS redirects, rejects private-network destinations,
streams with byte limits, checks MIME type, and rejects encrypted PDFs. Crossref
and Semantic Scholar links are metadata hints, not proof of download rights.

When no verified open-access full text is available, a permitted public abstract
is used. A title-only record is not extractable. The UI and dataset manifest
distinguish `full_text`, `abstract`, and failed acquisition states.

Each acquired document gets one readable directory under the selected folder's
`papers/` tree. It contains one content representation (`paper.pdf`,
`full-text.txt`, or `abstract.txt`) plus `normalized.txt` and `metadata.json`.
The UI reports each representation separately, so “37 documents” never implies
“37 PDFs.” See [storage and portability](storage-and-portability.md).

## Model policies

- `no_llm` acquires and indexes permitted material but never fabricates prose.
- `local` requires a loopback OpenAI-compatible endpoint.
- `remote` requires a named server-side provider profile and explicit egress
  confirmation for the job.

SiliconFlow defaults to `deepseek-ai/DeepSeek-V4-Flash` for extraction. Pro or
GLM retries are user actions; they are never silent fallbacks. JSON Mode is
followed by strict local schema, source-key, evidence, numeric, filler, and
prompt-injection validation. One schema repair is the maximum. Unsupported output
is held back rather than presented as ready to review.

## Reliability and recovery

Each paper is a durable work unit. Jobs record queued/running/control/terminal
state, checkpoints, provider attempts, token usage, and structured redacted
errors. Cancellation stops at a safe boundary. After process loss, orphaned
queued or running work becomes `interrupted`; Resume creates a new explicit job
from the last valid checkpoint.

The balanced UI profile exposes its hard ceilings: HTTP attempts, input/output
tokens, wall-clock duration, repair count, and concurrency. Budgets are reserved
before dispatch, so concurrent calls cannot overshoot them.

## CLI and Python

Search first so the paper set can be reviewed:

```bash
principia local --workspace ./principia-workspace search \
  --goal "When does verifier-guided inference improve LLM reasoning?" \
  --target-count 20
```

The legacy `local discover --search-id` command remains for compatibility. The
production UI uses separate acquisition and exact-document extraction so paper
ownership and model egress cannot be conflated. Its compatibility invocation is:

```bash
principia local --workspace ./principia-workspace discover \
  --search-id SEARCH_ID \
  --policy remote \
  --provider siliconflow \
  --model deepseek-ai/DeepSeek-V4-Flash \
  --base-url https://api.siliconflow.com/v1 \
  --confirm-remote-egress
```

The canonical Python surface is equivalent:

```python
from principia import Principia
from principia.providers import ModelPolicy

product = Principia.open("./principia-workspace")
search = product.local.search_papers(
    "When does verifier-guided inference improve LLM reasoning?",
    target_count=20,
)
job = product.local.acquire_and_discover(
    search["search_id"],
    policy=ModelPolicy(
        mode="remote",
        provider="siliconflow",
        model="deepseek-ai/DeepSeek-V4-Flash",
        base_url="https://api.siliconflow.com/v1",
        remote_egress_confirmed=True,
    ),
)
```

Credentials are resolved server-side from the owner-private workspace credential
file or environment. The browser sends only a provider-profile ID and never
receives saved keys or a configurable authenticated remote base URL.

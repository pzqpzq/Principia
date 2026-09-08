# Principia V1.3 Examples

The official notebooks are:

- `principia_v13_tutorial.ipynb` — the full real-LLM framework workflow.
- `principia_retrieval_tutorial.ipynb` — an online shared-retrieval walkthrough with LLM query planning and embedding reranking.

It demonstrates the full real-LLM workflow:

1. Search 50 real works from public metadata sources.
2. Extract structured features from the top-ranked works.
3. Select evidence for generation.
4. Generate a V1.3 idea.
5. Compare the generated idea against extracted prior ideas.
6. Export visible local files under `principia_project/principia_outputs/latest/`.

The retrieval tutorial queries arXiv, OpenAlex, Crossref, and Semantic Scholar,
then compares BM25 ranking with SiliconFlow embedding reranking. Set
`SILICONFLOW_API_KEY` in the environment before running it; the key is used for
the LLM planner and embedding client, not stored in the notebook.

## Resume From Existing Features

After search and extraction have completed once, a later notebook can start directly from saved features:

```python
import principia as pc

API_key = "YOUR_SILICONFLOW_API_KEY"
ws = pc.Workspace("principia_project", llm_config=pc.siliconflow_config(API_key))

features = ws.load_features()
selected_evidence = pc.select_evidence(features)
idea = ws.ideas.generate(selected_evidence, user_note="...", mode="calculus", model="siliconflow:Qwen/Qwen3.5-397B-A17B")
```

`ws.load_features()` reads persisted extraction records from SQLite and does not rerun public search or LLM extraction.

## Storage

Principia workspaces are usually small because PDFs are not retained by default. If a tutorial folder is large, check whether it contains a virtual environment such as `.venv/`; that is Python environment storage, not Principia research data.

Use:

```python
ws.storage_report()
ws.compact()
```

`ws.compact()` shrinks SQLite WAL/free pages without deleting works, features, ideas, or exports.

## Install

```bash
python -m pip install principia-ai ipykernel
python -m ipykernel install --user --name principia-v13-python --display-name "Python 3.12 (Principia V1.3)"
```

For source development from this repository:

```bash
python -m pip install -e ".[dev]"
python -m ipykernel install --user --name principia-v13-python --display-name "Python 3.12 (Principia V1.3)"
```

In VS Code, open the notebook and select `Python 3.12 (Principia V1.3)`. If the named kernel is not shown, choose the Python interpreter where `principia-ai` and `ipykernel` were installed.

## API Key

The notebook intentionally uses a placeholder:

```python
API_key = "YOUR_SILICONFLOW_API_KEY"
```

Replace it at runtime with your own SiliconFlow key. Do not commit notebooks containing real API keys or executed outputs.

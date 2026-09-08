# Principia v1.4.0 getting started

Principia v1.4.0 is a local-first product. Python serves the packaged user interface; Node is required only when building from source.

```bash
python -m pip install principia-ai==1.4.0
principia open --working-directory ./my-principia-project
```

The command binds to loopback on a random port and opens the **Principles Library**. The Library groups the same private knowledge by research question, Area label, or folder and provides edit/archive actions and direct links to Local Discovery and Principles Explorer.

A production workspace starts with no hidden private knowledge. An adjacent or explicitly selected shared `principle-packages/` library may already provide downloaded, paper-free packages. Principia immediately creates `local_data/` and `workspace/` under the selected working directory and shows their exact paths in **Local Discovery**. Connect an external folder or select a managed folder, index its documents, and select exactly which ones to extract. If you need papers, the optional literature helper searches metadata, creates a new named folder under `local_data/`, and acquires permitted content there before returning you to document selection.

The working-directory selector lives at the top of **Principles Library**. It changes
the entire active product context, not merely the destination for one literature run.
Different working directories share no database, credentials, jobs, Local collections,
private Principles, or scenarios. They deliberately share the selected
`principle-packages/` library. An empty working directory opens with no private
collections and receives newly created `local_data/` and `workspace/` children, while
already-downloaded packages remain available in their separate Library section.

The shortest successful path is:

```text
Principles Library → choose private folder → select documents
                   → extract reusable findings → review → Principles Explorer
```

Extraction needs no Area and the research focus is optional. Area labels are editable organization metadata suggested only after extraction; they never determine whether evidence checks pass. Exact folder paths are disclosed only inside the authorized Local UI.

To distribute a nonempty, paper-free library, export or import the portable showcase:

```bash
principia showcase --working-directory ./my-principia-project export ./principles-showcase
principia showcase --working-directory ./clean-project import ./principles-showcase
```

The four-file showcase contains Principle arguments, public bibliographic links, evidence hashes, and validated relations. It contains no PDFs, abstracts, quotations, normalized text, credentials, or absolute paths.

The Python entry point is equivalent:

```python
from principia import Principia

product = Principia.open(working_directory="./my-principia-project")
print(product.cloud.areas())
product.open_ui()
```

Use `principia doctor --json` for redacted runtime, migration, workspace, and installed-area diagnostics. Existing v1.3 commands and imports remain supported.

## Model policies

- `no_llm` indexes deterministically and never fabricates prose. Zero Candidates is a valid result.
- `local` accepts only a loopback OpenAI-compatible endpoint.
- `remote` requires a named provider/model and explicit egress confirmation for every job.

Remote jobs never switch models silently. Provider errors are actionable and the selected provider/model remain visible.

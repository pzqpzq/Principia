# Principia downloadable Principle packages

This directory is a paper-free, local distribution channel for Principle collections. It contains immutable `.pcp` packages, the local catalog that routes them, and cryptographic build evidence.

The packages contain unassessed Candidate Principles and public DOI, arXiv, or HTTPS paper links. They contain no PDFs, abstracts, quotations, normalized source text, credentials, or private filesystem paths. Downloading or installing a package stores it locally; the word Global describes its distribution channel, not a different data type and not a human-review decision.

From the adjacent Core checkout, open any private working directory against this
shared package library:

```bash
principia open --working-directory /path/to/my-principia --package-library /absolute/path/to/principle-packages
```

The MAS-ASD, Hilbert, and Cognitive packages are already downloaded. Principia
verifies and activates them automatically. Runtime index files are rebuilt under
`.principia/` and excluded from Git; the Library UI provides verify, pin, rollback,
and Explorer controls.

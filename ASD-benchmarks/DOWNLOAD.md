# Download Principia-100

[Overview](README.md) · [Catalog](CATALOG.md) · [Validation tools](TOOLS.md)

The full benchmark is about **4.80 GB** stored, including **4.43 GB in Git LFS**. Choose individual cases when possible. All commands below select only the benchmark, leaving the application and historical datasets out of the checkout. Install [Git](https://git-scm.com/downloads) and [Git LFS](https://git-lfs.com/) first.

The immutable version tag is `asd-benchmark-v0.1.0`. Record it, or the resolved commit, with every study. To follow later changes deliberately, use `main` instead.

## One case

This example selects case 61, a small membrane-permeation experiment. Run in a new directory:

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse \
  --branch asd-benchmark-v0.1.0 https://github.com/pzqpzq/Principia.git
cd Principia
GIT_LFS_SKIP_SMUDGE=1 git sparse-checkout set \
  ASD-benchmarks/tools ASD-benchmarks/schemas \
  ASD-benchmarks/scenarios/61_chemistry_membrane_permeation
git lfs pull --include="ASD-benchmarks/scenarios/61_chemistry_membrane_permeation/**" --exclude=""
cd ASD-benchmarks
python3 tools/replay.py --root . --mode verify --case P100-061
```

The sparse checkout also includes the collection's top-level manifests and documentation. To add another case, run from the repository root, substituting the folder name from the catalog:

```bash
GIT_LFS_SKIP_SMUDGE=1 git sparse-checkout add \
  ASD-benchmarks/scenarios/53_manufacturing_screw_friction
git lfs pull --include="ASD-benchmarks/scenarios/53_manufacturing_screw_friction/**" --exclude=""
```

If Principia is already installed using a sparse checkout, use the same `sparse-checkout add` and `git lfs pull` commands in that repository. Check the version you have selected before comparing results.

## All 100 cases

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse \
  --branch asd-benchmark-v0.1.0 https://github.com/pzqpzq/Principia.git
cd Principia
GIT_LFS_SKIP_SMUDGE=1 git sparse-checkout set ASD-benchmarks
git lfs pull --include="ASD-benchmarks/**" --exclude=""
cd ASD-benchmarks
python3 tools/validate_release.py .
python3 tools/replay.py --root . --mode verify
python3 tools/test_replay.py
```

If the repository is already cloned, start at `git sparse-checkout set ASD-benchmarks`; use `add` instead of `set` to retain an existing application checkout.

The working files occupy about 4.80 GB; Git's object stores also use disk space. Reserve **at least 12 GB** for a complete Git checkout before any archive extraction or analysis. Unpacked source payloads total about **7.31 GB** across the corpus, with every case individually below 500 MB. Peak analysis memory and derived outputs are additional. Keep archives intact and extract working copies only when needed.

## Windows PowerShell

Set the skip-smudge variable before clone and sparse-checkout commands:

```powershell
$env:GIT_LFS_SKIP_SMUDGE = '1'
# Run the git clone and git sparse-checkout commands above as single lines.
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
git lfs pull --include="ASD-benchmarks/**" --exclude=""
```

Use `python` in place of `python3` if that is how Python 3.9+ is installed. Preserve filenames and bytes; `.gitattributes` prevents automatic newline conversion.

## Verify what you downloaded

`tools/replay.py --mode verify --case P100-061` verifies one case's scientific assets. `tools/validate_release.py .` verifies the exact complete release, including curatorial files. It intentionally fails on missing files, changed bytes or extra files; store analysis outputs outside the release directory.

A file starting with `version https://git-lfs.github.com/spec/v1` is an **LFS pointer**, not scientific data. Run the relevant `git lfs pull` command and then verify again. GitHub-generated source ZIPs may contain pointers instead of payloads; the Git LFS procedure above is the supported route. LFS availability depends on the repository's hosting quota; report a failed download with its case ID and error message.

For an audit of a checkout that intentionally omits LFS payloads, use:

```bash
python3 tools/verify_git_release.py . --allow-lfs-pointers
```

This checks that each pointer's SHA-256 and byte count match the frozen manifest; it **does not verify remotely stored payload bytes**. The output reports actual files and pointer-only files separately.

## Recover from original sources

The [acquisition manifest](ACQUISITION_MANIFEST.json) records exact source URLs where available. The [replay tool](TOOLS.md) can download a missing asset from its recorded publisher URL and reject changed bytes. An older snapshot without an exact URL requires an intact frozen release copy. A current feed or a differently packaged archive is never silently accepted as the historical version.

GitHub distributes the frozen files; the scientific origin and reuse terms remain those of the cited publishers. Contact an original publisher for scientific metadata questions, and report corpus packaging issues to [Principia](https://github.com/pzqpzq/Principia/issues).

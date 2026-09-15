# Download Principia-100

[Overview](README.md) · [Catalog](CATALOG.md) · [Validation tools](TOOLS.md)

The full benchmark is about **4.80 GB** stored, including **4.43 GB in Git LFS**. Choose individual cases when possible. All commands below select only the benchmark, leaving the application and historical datasets out of the checkout. Install [Git](https://git-scm.com/downloads) and [Git LFS](https://git-lfs.com/) first.

The immutable version tag is `asd-benchmark-v0.1.1`. Record it, or the resolved commit, with every study. To follow later changes deliberately, use `main` instead.

## One case

This example selects case 61, a small membrane-permeation experiment. Run in a new directory:

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse \
  --branch asd-benchmark-v0.1.1 https://github.com/pzqpzq/Principia.git
cd Principia
git sparse-checkout set \
  ASD-benchmarks/tools ASD-benchmarks/schemas \
  ASD-benchmarks/scenarios/61_chemistry_membrane_permeation
cd ASD-benchmarks
python3 tools/replay.py --root . --mode verify --case P100-061
```

Sparse checkout automatically downloads the LFS files belonging to the selected case. The skip-smudge setting applies only to the initial clone, which keeps unrelated directories out of the download. The checkout also includes the collection's top-level manifests and documentation. To add another case, run from the repository root, substituting the folder name from the catalog:

```bash
git sparse-checkout add \
  ASD-benchmarks/scenarios/53_manufacturing_screw_friction
```

If Principia is already installed using a sparse checkout, install Git LFS and use the same `sparse-checkout add` command in that repository. Check the version you have selected before comparing results.

## All 100 cases

```bash
git lfs install
GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --filter=blob:none --sparse \
  --branch asd-benchmark-v0.1.1 https://github.com/pzqpzq/Principia.git
cd Principia
git sparse-checkout set ASD-benchmarks
cd ASD-benchmarks
python3 tools/validate_release.py .
python3 tools/replay.py --root . --mode verify
python3 tools/test_replay.py
```

If the repository is already cloned, start at `git sparse-checkout set ASD-benchmarks`; use `add` instead of `set` to retain an existing application checkout.

The working files occupy about 4.80 GB; Git's object stores also use disk space. Reserve **at least 12 GB** for a complete Git checkout before any archive extraction or analysis. Unpacked source payloads total about **7.31 GB** across the corpus, with every case individually below 500 MB. Peak analysis memory and derived outputs are additional. Keep archives intact and extract working copies only when needed.

## Windows PowerShell

Apply skip-smudge to the initial clone only, and clear it **before** selecting cases:

```powershell
git lfs install
$env:GIT_LFS_SKIP_SMUDGE = '1'
git clone --depth 1 --filter=blob:none --sparse --branch asd-benchmark-v0.1.1 https://github.com/pzqpzq/Principia.git
Remove-Item Env:GIT_LFS_SKIP_SMUDGE
cd Principia
git sparse-checkout set ASD-benchmarks/tools ASD-benchmarks/schemas ASD-benchmarks/scenarios/61_chemistry_membrane_permeation
```

Use `python` in place of `python3` if that is how Python 3.9+ is installed. Preserve filenames and bytes; `.gitattributes` prevents automatic newline conversion.

## Verify what you downloaded

`tools/replay.py --mode verify --case P100-061` verifies one case's scientific assets. `tools/validate_release.py .` verifies the exact complete release, including curatorial files. It intentionally fails on missing files, changed bytes or extra files; store analysis outputs outside the release directory.

A file starting with `version https://git-lfs.github.com/spec/v1` is an **LFS pointer**, not scientific data. If this occurs, check that Git LFS is installed and `GIT_LFS_SKIP_SMUDGE` is unset. Use a fresh directory with the commands above, then verify again. GitHub-generated source ZIPs may contain pointers instead of payloads; the selective checkout procedure above is the supported route. On some older Git versions, running `git lfs pull` in a partial clone scans unrelated repository blobs; the documented procedure avoids that scan by downloading LFS objects during checkout. LFS availability depends on the repository's hosting quota; report a failed download with its case ID and error message.

For an audit of a checkout that intentionally omits LFS payloads, use:

```bash
python3 tools/verify_git_release.py . --allow-lfs-pointers
```

This checks that each pointer's SHA-256 and byte count match the frozen manifest; it **does not verify remotely stored payload bytes**. The output reports actual files and pointer-only files separately.

## Recover from original sources

The [acquisition manifest](ACQUISITION_MANIFEST.json) records exact source URLs where available. The [replay tool](TOOLS.md) can download a missing asset from its recorded publisher URL and reject changed bytes. An older snapshot without an exact URL requires an intact frozen release copy. A current feed or a differently packaged archive is never silently accepted as the historical version.

GitHub distributes the frozen files; the scientific origin and reuse terms remain those of the cited publishers. Contact an original publisher for scientific metadata questions, and report corpus packaging issues to [Principia](https://github.com/pzqpzq/Principia/issues).

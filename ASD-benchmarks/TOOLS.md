# Reproduction and validation tools

Run from the `ASD-benchmarks/` directory after downloading the required Git LFS objects. Basic integrity/replay tools require Python 3.9+ and only the standard library. They do not run publisher analysis code.

```sh
python3 tools/validate_release.py .
python3 tools/replay.py --root . --mode verify
python3 tools/test_replay.py
```

Reconstruct missing source assets in a disposable destination from an intact release copy:

```sh
python3 tools/replay.py --root /tmp/principia-replay --mode copy --source-root . --case P100-061
```

Download the exact recorded source representation where a direct URL exists:

```sh
python3 tools/replay.py --root /tmp/principia-download --mode download --case P100-051
```

Curator profiles and older snapshots without recorded direct URLs require frozen-copy replay. Some live providers require different public network access; mutable feeds may no longer match. A changed or oversized download is rejected. Existing mismatched files are never overwritten. A missing publisher checksum is not replaced with a claim of publisher authentication; local SHA-256 still fixes exact release bytes.

For optional native-reader reinspection, create a Python 3.12 environment, install `tools/requirements-audit.txt`, and make `ffprobe` and system libarchive available. Package versions record the portable audit environment; older retained reports state their original coverage. There is no conversion or scientific data rewriting.

```sh
python3.12 -m venv /tmp/principia-audit-env
/tmp/principia-audit-env/bin/python -m pip install -r tools/requirements-audit.txt
/tmp/principia-audit-env/bin/python tools/audit_native.py --root . --output /tmp/principia-format-reports --case P100-060
```

Reader coverage includes complete CRC/stream checks for containers, complete rows for Parquet, native FCS/RDS parsing, bounded HDF5/CDF/ROOT samples and header/stream inspection for some media. MATLAB MCOS tables and vendor-specific formats retain explicit limitations. `mat_envelope.py` is a bounded read-only fallback for the Octave-exported MATLAB structures in case 60; it does not convert those files or execute MATLAB.

The full archive expansion measure counts recursively unpacked general archives while leaving native compound formats (XLSX, NPZ, MAT, etc.) as files. It measures disk payload, not peak runtime memory. Archive path checks reject traversal and links. Use disposable outputs, never the immutable corpus directory, for future analysis.

For the optional complete WFDB archive audit, use `python3.12 tools/audit_wfdb_archive.py PATH_TO_SOURCE_ZIP --output /tmp/wfdb-audit.json`. It decodes every record and QRS annotation, and removes temporary extraction afterward.

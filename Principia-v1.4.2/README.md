# Principia v1.4.2

This folder contains the product source and bundled public scientific knowledge. It includes 5 curated public demo projects with equations, study maps, and recorded evidence. Original datasets are not required to browse them. It contains no private source data or API credentials.

## Start locally

With Python 3.11 or newer, install once:

```sh
cd core-v1.4.2
python3 -m venv .venv
.venv/bin/python -m pip install '.[asd,local]'
cd ..
python3 scripts/start_local.py --port 8142 --browser
```

Start with `python3 scripts/start_local.py --port 8142`. The launcher uses a local core-v1.4.2/.venv or the shared dependency runtime on this computer. If unavailable, create the local virtual environment and install `.[asd,local]` from core-v1.4.2. The bundled frontend needs no node_modules to run.

User state lives in runtime/user-workspace/. Demos are installed once in an empty workspace; existing projects and demo deletions are respected. To explore your own data, configure API & models in the interface, add a local folder, and start discovery. No author credentials are provided or needed for offline demo viewing. To rerun a demo, obtain its public source data and connect the folder. Dependency libraries are installed separately and counted separately from this source folder. See core-v1.4.2/docs/v1.4.2/storage-policy.md for storage maintenance.

#!/usr/bin/env python3
"""Verify the publication inventory, optionally accepting explicitly recorded LFS pointers.

Pointer mode authenticates pointer metadata only. Use validate_release.py after
fetching LFS payloads to authenticate all scientific bytes.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
import pathlib
import re
from replay import safe, check

POINTER = re.compile(rb'version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n')

def pointer_matches(path, asset):
    if not path.is_file() or path.stat().st_size > 200:
        return False
    match = POINTER.fullmatch(path.read_bytes())
    return bool(match and match[1].decode() == asset['sha256'] and int(match[2]) == asset['bytes'])

def validate(root, allow_pointers=False):
    manifest = json.loads((root/'RELEASE_MANIFEST.json').read_text())
    benchmark = json.loads((root/'BENCHMARK_MANIFEST.json').read_text())
    acquisition = json.loads((root/'ACQUISITION_MANIFEST.json').read_text())
    issues = []
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    entries = manifest['files']
    expected = {a['path'] for a in entries}
    lfs_paths = set(manifest['distribution']['lfs_paths'])
    payloads = pointers = 0
    if len(expected) != len(entries):
        issues.append({'issue':'duplicate_manifest_paths'})
    for path in sorted(actual - expected - {'RELEASE_MANIFEST.json'}):
        issues.append({'path':path,'issue':'not_allowlisted'})
    for asset in entries:
        path = safe(root,asset['path'])
        if path.is_symlink():
            issues.append({'path':asset['path'],'issue':'symlink'})
            continue
        if allow_pointers and asset['path'] in lfs_paths and pointer_matches(path,asset):
            pointers += 1
            continue
        status = check(path,asset)
        if status == 'ok':
            payloads += 1
        else:
            issues.append({'path':asset['path'],'issue':status})
    ids = [c['case_id'] for c in benchmark['cases']]
    if sorted(ids) != [f'P100-{i:03}' for i in range(1,101)]:
        issues.append({'issue':'requires_exactly_P100_001_through_100'})
    by_path = {a['path']:a for a in entries}
    assets = {a['path']:a for a in acquisition['assets']}
    if len(assets) != 1685 or len(assets) != len(acquisition['assets']):
        issues.append({'issue':'scientific_asset_inventory'})
    for a in benchmark['assets']:
        if a['path'] not in assets or any(a[k] != assets[a['path']][k] for k in ['sha256','bytes']):
            issues.append({'path':a['path'],'issue':'acquisition_manifest_disagreement'})
    for a in assets.values():
        if a['path'] not in by_path or any(a[k] != by_path[a['path']][k] for k in ['sha256','bytes']):
            issues.append({'path':a['path'],'issue':'release_manifest_disagreement'})
    for c in benchmark['cases']:
        for key in ['release_folder_bytes','expanded_release_folder_equivalent_bytes']:
            if c[key] >= 500_000_000:
                issues.append({'case_id':c['case_id'],'issue':key+'_ceiling'})
        if not set(c['asset_paths']).issubset(assets):
            issues.append({'case_id':c['case_id'],'issue':'case_asset_inventory'})
    added = [c for c in benchmark['cases'] if int(c['case_id'][-3:]) >= 51]
    if sum(c['data_origin']=='measured_or_observed' for c in added) < 40:
        issues.append({'issue':'measured_addition_quota'})
    inputs = json.loads((root/'INPUT_ALLOWLIST.json').read_text())['files']
    for a in inputs:
        if a['path'] not in by_path or any(a[k] != by_path[a['path']][k] for k in ['sha256','bytes']):
            issues.append({'path':a['path'],'issue':'input_allowlist_disagreement'})
    if manifest['version'] != benchmark['version'] or not benchmark['publication_authorized']:
        issues.append({'issue':'publication_metadata'})
    return {'status':'pass' if not issues else 'fail','cases':len(ids),
            'scientific_assets':len(assets),'payload_files_sha256_verified':payloads,
            'lfs_pointer_metadata_only':pointers,
            'remote_payloads_verified_by_pointer_mode':False,
            'issues':issues}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=pathlib.Path)
    parser.add_argument('--allow-lfs-pointers',action='store_true')
    args = parser.parse_args()
    result = validate(args.root,args.allow_lfs_pointers)
    print(json.dumps(result,indent=2))
    sys.exit(result['status'] != 'pass')

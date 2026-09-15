import sys
sys.dont_write_bytecode = True
#!/usr/bin/env python3
"""Validate exact release inventory and scientific-corpus contracts without running experiments."""
import json,pathlib,argparse,sys,collections
from replay import check,safe

def validate(root):
 m=json.loads((root/'RELEASE_MANIFEST.json').read_text());issues=[]
 for a in m['files']:
  result=check(safe(root,a['path']),a)
  if result!='ok':issues.append({'path':a['path'],'issue':result})
 expected={a['path'] for a in m['files']}|{'RELEASE_MANIFEST.json'};actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
 for path in sorted(actual-expected):issues.append({'path':path,'issue':'not_allowlisted'})
 b=json.loads((root/'BENCHMARK_MANIFEST.json').read_text());cases=b['cases'];ids=[c['case_id'] for c in cases]
 if len(cases)!=100 or len(set(ids))!=100:issues.append({'issue':'requires 100 unique case ids'})
 added=[c for c in cases if int(c['case_id'][-3:])>=51]
 if len(added)!=50 or sum(c['data_origin']=='measured_or_observed' for c in added)<40:issues.append({'issue':'addition count or measured-only quota'})
 for c in cases:
  if c['installed_folder_bytes']>=500_000_000 or c['expanded_source_equivalent_bytes']>=500_000_000:issues.append({'case_id':c['case_id'],'issue':'size ceiling'})
  for path in c['asset_paths']:
   if path not in actual:issues.append({'path':path,'issue':'case asset absent'})
 return {'status':'pass' if not issues else 'fail','cases':len(cases),'assets':len(b['assets']),'release_files_checked':len(m['files']),'measured_only_additions':sum(c['data_origin']=='measured_or_observed' for c in added),'issues':issues}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);a=p.parse_args();r=validate(a.root);print(json.dumps(r,indent=2));sys.exit(r['status']!='pass')

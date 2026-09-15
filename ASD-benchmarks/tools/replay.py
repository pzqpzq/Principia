import sys
sys.dont_write_bytecode = True
#!/usr/bin/env python3
"""Verify or reconstruct frozen assets. Never replaces files that disagree with the manifest."""
import argparse,pathlib,json,hashlib,urllib.request,shutil,sys,tempfile

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def safe(root,path):
 q=pathlib.PurePosixPath(path)
 if q.is_absolute() or '..' in q.parts or '\\' in path:raise ValueError('unsafe manifest path')
 p=root/path
 if not p.resolve().is_relative_to(root.resolve()):raise ValueError('path escapes root')
 return p
def check(p,a):
 if not p.is_file():return 'missing'
 if p.stat().st_size!=a['bytes']:return 'size_mismatch'
 if sha(p)!=a['sha256']:return 'sha256_mismatch'
 return 'ok'
def replay(a,root,mode='verify',source_root=None):
 p=safe(root,a['path']);status=check(p,a)
 if status=='ok':return status
 if p.exists() or mode=='verify':return status
 p.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(dir=p.parent,prefix='.replay-',delete=False) as t:tmp=pathlib.Path(t.name)
 try:
  if mode=='copy':
   if source_root is None:raise ValueError('--source-root required')
   src=safe(source_root,a['path']);assert check(src,a)=='ok','source copy fails frozen hash';shutil.copyfile(src,tmp)
  elif mode=='download':
   url=a.get('download_url')
   if not url:return 'no_direct_url_use_frozen_release_copy'
   req=urllib.request.Request(url,headers={'Accept-Encoding':'identity','User-Agent':'Principia-100-frozen-asset-replay/1'})
   with urllib.request.urlopen(req,timeout=60) as r,tmp.open('wb') as out:
    count=0
    while True:
     b=r.read(1048576)
     if not b:break
     count+=len(b)
     if count>a['bytes']:raise ValueError('remote asset exceeds frozen size')
     out.write(b)
  result=check(tmp,a)
  if result!='ok':return 'source_drift_or_corruption:'+result
  tmp.replace(p);return 'restored'
 finally:
  if tmp.exists():tmp.unlink()
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[1]/'ACQUISITION_MANIFEST.json');p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--mode',choices=['verify','copy','download'],default='verify');p.add_argument('--source-root',type=pathlib.Path);p.add_argument('--case');a=p.parse_args();m=json.loads(a.manifest.read_text());assets=m.get('assets',m.get('files',[]));results=[]
 for x in assets:
  if a.case and x.get('case_id')!=a.case:continue
  try:s=replay(x,a.root,a.mode,a.source_root)
  except Exception as e:s=type(e).__name__+': '+str(e)
  results.append({'path':x['path'],'status':s})
 bad=[r for r in results if r['status'] not in ['ok','restored']];print(json.dumps({'checked':len(results),'passed':len(results)-len(bad),'issues':bad},indent=2));sys.exit(bool(bad))
if __name__=='__main__':main()

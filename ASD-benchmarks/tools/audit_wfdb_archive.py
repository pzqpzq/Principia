import sys
sys.dont_write_bytecode = True
"""Read every WFDB signal and annotation in a verified ZIP; temporary extraction only."""
import argparse,pathlib,tempfile,zipfile,stat,json,collections,hashlib
from concurrent.futures import ThreadPoolExecutor

def audit(archive):
 import wfdb
 with tempfile.TemporaryDirectory(prefix='principia-wfdb-') as td:
  root=pathlib.Path(td)
  with zipfile.ZipFile(archive) as z:
   assert z.testzip() is None
   assert sum(x.file_size for x in z.infolist())<500_000_000
   for x in z.infolist():
    p=pathlib.PurePosixPath(x.filename);assert not p.is_absolute() and '..' not in p.parts and not stat.S_ISLNK(x.external_attr>>16)
    if not x.is_dir():
     out=root/p;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(x))
  headers=sorted(root.rglob('*.hea'));annotations=sorted(root.rglob('*.qrs'))
  def record(p):
   r=wfdb.rdrecord(str(p.with_suffix('')),physical=False)
   assert r.d_signal.shape==(r.sig_len,r.n_sig)
   return {'samples':r.sig_len,'channels':r.n_sig,'fs':r.fs,'names':r.sig_name,'units':r.units}
  with ThreadPoolExecutor(max_workers=4) as ex:rs=list(ex.map(record,headers))
  def annot(p):
   a=wfdb.rdann(str(p.with_suffix('')),'qrs');assert len(a.sample)==len(a.symbol);return len(a.sample)
  with ThreadPoolExecutor(max_workers=4) as ex:aa=list(ex.map(annot,annotations))
  return {'status':'pass','signal_records_decoded':len(rs),'annotation_files_decoded':len(aa),'annotation_events':sum(aa),'signal_samples_per_channel_sum':sum(x['samples'] for x in rs),'signal_name_sets':sorted({tuple(x['names']) for x in rs},key=repr),'unit_sets':sorted({tuple(x['units']) for x in rs},key=repr),'sampling_rates_Hz':sorted({x['fs'] for x in rs},key=repr),'coverage':'Every digital signal array and QRS annotation decoded; no clinical interpretation or conversion. All ZIP CRCs and safe paths checked. Temporary extraction removed.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('archive',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path);a=p.parse_args();r=audit(a.archive);r['asset_sha256']=hashlib.sha256(a.archive.read_bytes()).hexdigest();r['case_id']='P100-033'
 if a.output:a.output.write_text(json.dumps(r,indent=2)+'\n')
 else:print(json.dumps(r,indent=2))

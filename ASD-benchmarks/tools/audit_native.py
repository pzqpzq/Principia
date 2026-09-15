import sys
sys.dont_write_bytecode = True
import sys,json,pathlib,hashlib,concurrent.futures,tempfile,zipfile,gzip,io
from audit_common import dump,digest,utc
from native_archives import inspect,native
from native_formats import inspect_file


def read(p):
 ext=p.suffix.lower()
 if ext=='.root':
  import uproot
  with uproot.open(p) as f:
   ts=[]
   for k in f.keys():
    t=f[k]
    if hasattr(t,'num_entries'):
     # Decode a bounded event sample; file envelope and ROOT tree metadata retained.
     t.arrays(entry_stop=1,library='np');ts.append({'name':k,'events':t.num_entries,'branches':list(t.keys())})
   return {'format':'ROOT','trees':ts,'coverage':'tree metadata and first event decode'}
 if ext=='.dcm':
  import pydicom
  d=pydicom.dcmread(p);keys=['Modality','SOPInstanceUID','SeriesInstanceUID','StudyInstanceUID','Rows','Columns','PixelSpacing','SliceThickness','ImagePositionPatient','ImageOrientationPatient','BitsAllocated','BitsStored','PhotometricInterpretation','NumberOfFrames']
  o={'format':'DICOM','tags':{k:str(getattr(d,k)) for k in keys if hasattr(d,k)},'transfer_syntax':str(d.file_meta.TransferSyntaxUID)}
  try:a=d.pixel_array;o['decoded_pixel_shape']=a.shape
  except Exception as e:o['pixel_decoder_limitation']=str(e)
  return o
 if ext=='.edf':
  import pyedflib
  with pyedflib.EdfReader(str(p)) as f:
   ds=[]
   for i in range(f.signals_in_file):
    x=f.readSignal(i);ds.append({'label':f.getLabel(i),'sample_rate':f.getSampleFrequency(i),'samples':len(x),'unit':f.getPhysicalDimension(i)})
   return {'format':'EDF','channels':ds,'start_time':str(f.getStartdatetime()),'duration_seconds':f.file_duration}
 if ext=='.nwb':
  from native_archives import hdf
  o=hdf(p.read_bytes());o['format']='NWB/HDF5';o['coverage']='HDF5 structure and sampled arrays; full NWB schema validation not run';return o
 if ext in ['.hdf5','.nc','.fits','.fit','.pha','.rsp','.rsp2','.parquet','.npz','.cdf']:return inspect_file(p)
 if ext=='.gz':
  with gzip.open(p,'rb') as f:b=f.read(500_000_001)
  assert len(b)<500_000_000
  return {'format':'GZIP','expanded_bytes':len(b),'checks':['gzip_CRC'],'inner':native(b,p.stem)}
 if ext in ['.geojson','.schema']:return {'format':'JSON','root_keys':list(json.loads(p.read_bytes()))}
 if ext=='.quakeml':
  import xml.etree.ElementTree as E
  r=E.fromstring(p.read_bytes());return {'format':'QuakeML','root':r.tag,'elements':sum(1 for _ in r.iter())}
 if ext=='.rasx':
  if zipfile.is_zipfile(p):
   with zipfile.ZipFile(p) as z:assert z.testzip() is None;return {'format':'Rigaku RASX/ZIP','member_names':z.namelist(),'coverage':'all member CRCs; vendor interpretation required'}
 return inspect(p)
if __name__=='__main__':
 import argparse
 from replay import safe,check
 p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--case');a=p.parse_args();m=json.loads((a.root/'ACQUISITION_MANIFEST.json').read_text());counts={}
 for x in m['assets']:
  if a.case and a.case!=x['case_id']:continue
  f=safe(a.root,x['path']);r={'path':x['path'],'sha256':x['sha256'],'bytes':x['bytes'],'checked_utc':utc()}
  try:
   assert check(f,x)=='ok','Frozen asset integrity failure'
   r.update(read(f));r['status']='pass'
  except Exception as e:r.update(status='failed',error=type(e).__name__+': '+str(e))
  dump(a.output/(hashlib.sha256(x['path'].encode()).hexdigest()+'.json'),r);counts[r['status']]=counts.get(r['status'],0)+1
 print(json.dumps(counts));sys.exit(bool(counts.get('failed')))

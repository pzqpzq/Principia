import sys
sys.dont_write_bytecode = True
"""Read-only format/integrity audit. Publisher code is never executed."""
import io,sys,json,pathlib,zipfile,tarfile,stat,hashlib,collections,tempfile,subprocess,concurrent.futures,re
from audit_common import dump,digest,utc
from native_formats import inspect_bytes as base_bytes, safe

def native(b,name):
 ext=pathlib.PurePosixPath(name).suffix.lower()
 if name.startswith('__MACOSX/') or pathlib.PurePosixPath(name).name.startswith('._'):return {'format':'publisher_OS_metadata'}
 if ext=='.mat':
  if b[:8]==b'\x89HDF\r\n\x1a\n' or b[512:520]==b'\x89HDF\r\n\x1a\n':return hdf(b)
  import scipy.io
  try:fs=scipy.io.whosmat(io.BytesIO(b))
  except TypeError:
   a=scipy.io.loadmat(io.BytesIO(b),verify_compressed_data_integrity=True)
   return {'format':'MATLAB','variables':[{'name':k,'shape':getattr(v,'shape',None),'type':type(v).__name__} for k,v in a.items() if not k.startswith('__')],'reader_limitation':'MCOS table object preserved; SciPy decodes opaque object/workspace, not MATLAB table semantics. Source XLSX alternative retained.','coverage':'MAT envelope, opaque table and function-workspace decoded without execution'}
  try:a=scipy.io.loadmat(io.BytesIO(b),verify_compressed_data_integrity=True)
  except TypeError as e:
   if b'written by Octave 6.2.0' not in b[:128]:raise
   from mat_envelope import inventory
   arr=inventory(b)
   return {'format':'MATLAB','variables':[{'name':k,'shape':shape,'type':typ} for k,shape,typ in fs],'numeric_element_inventory':arr,'reader_limitation':str(e),'coverage':'bounded recursive MATLAB v5 numeric element inventory; SciPy full object decoding unavailable'}
  out={'format':'MATLAB','variables':[{'name':k,'shape':shape,'type':typ} for k,shape,typ in fs]}
  details=[]
  for k,x in a.items():
   if k.startswith('__'):continue
   if getattr(x.dtype,'names',None):details.append({'name':k,'fields':list(x.dtype.names)})
  out['struct_fields']=details;return out
 if ext in ('.h5','.hdf5'):return hdf(b)
 if ext=='.fcs':
  import flowio
  f=flowio.FlowData(io.BytesIO(b));return {'format':'FCS','events':f.event_count,'channels':f.channel_count,'channel_metadata':f.channels,'text_metadata':{k:v for k,v in f.text.items() if any(x in k.lower() for x in ['date','vol','unit','sample','tube','cyt','par','tot'])}}
 if ext=='.rds':
  import rdata
  a=rdata.read_rds(io.BytesIO(b));return {'format':'RDS','object_type':type(a).__name__,'shape':list(a.shape) if hasattr(a,'shape') else None,'columns':[str(x) for x in list(a.columns)] if hasattr(a,'columns') else None,'names':list(a)[:40] if isinstance(a,dict) else None,'components':[{'name':k,'type':type(v).__name__,'shape':list(v.shape) if hasattr(v,'shape') else None,'columns':[str(x) for x in v.columns] if hasattr(v,'columns') else None} for k,v in a.items()] if isinstance(a,dict) else None}
 if ext in ('.mp4','.mov'):
  with tempfile.NamedTemporaryFile(suffix=ext) as t:
   t.write(b);t.flush();r=subprocess.run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',t.name],capture_output=True,text=True);assert r.returncode==0,r.stderr
   a=json.loads(r.stdout);a.get('format',{}).pop('filename',None);return {'format':'video','probe':a,'coverage':'container and stream headers; not every decoded frame'}
 if ext in ('.docx','.ods'):
  import xml.etree.ElementTree as ET
  with zipfile.ZipFile(io.BytesIO(b)) as z:
   assert z.testzip() is None
   root=ET.fromstring(z.read('word/document.xml' if ext=='.docx' else 'content.xml'));txt=' '.join(root.itertext());return {'format':ext[1:].upper(),'text_excerpt':txt[:6000]}
 o=base_bytes(b,name)
 if o.get('format')=='preserved_native':o['reader_limitation']='Preserved signature and bytes; specialized native interpretation not implemented in this audit.'
 if ext in ('.csv','.txt','.tsv','.dat') and b'\x00' not in b[:2048]:
  txt=b.decode('utf-8-sig',errors='replace');o['first_lines']=txt.splitlines()[:8];o['encoding_replacement_count']=txt.count('\ufffd')
 return o

def hdf(b):
 import h5py
 ds=[]
 with h5py.File(io.BytesIO(b),'r') as f:
  def visit(k,v):
   if isinstance(v,h5py.Dataset):
    if v.size:v[tuple(slice(0,1) for _ in v.shape)] if v.shape else v[()]
    ds.append({'name':k,'shape':v.shape,'dtype':str(v.dtype),'attributes':{k:str(v)[:300] for k,v in v.attrs.items()}})
  f.visititems(visit);return {'format':'HDF5','datasets':ds,'coverage':'hierarchy and first element/chunk per dataset'}

def member(name,b,depth=0):
 assert safe(name),name
 r={'name':name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 try:
  if name.lower().endswith('.zip'):
   r.update(archive_bytes(b,name,depth+1))
  else:r['structure']=native(b,name)
 except Exception as e:r['inspection_limitation']=type(e).__name__+': '+str(e)
 return r

def archive_bytes(b,name,depth=0):
 assert depth<5
 members=[]
 with zipfile.ZipFile(io.BytesIO(b)) as z:
  assert z.testzip() is None
  total=sum(x.file_size for x in z.infolist());assert total<500_000_000,(name,total)
  for x in z.infolist():
   assert safe(x.filename) and not stat.S_ISLNK(x.external_attr>>16),x.filename
   if x.is_dir():continue
   r=member(x.filename,z.read(x),depth);members.append(r)
  expanded=sum(x.get('expanded_bytes',x['bytes']) for x in members)
 return {'format':'ZIP','expanded_bytes':expanded,'members':members,'checks':['all_member_CRCs','safe_paths_no_symlinks'],'member_count':len(members)}

def inspect(p):
 b=p.read_bytes();ext=p.suffix.lower()
 if ext=='.zip':return archive_bytes(b,p.name)
 if ext in ('.tar','.tgz','.rar','.7z'):
  import libarchive
  members=[];total=0
  with libarchive.file_reader(str(p)) as a:
   for x in a:
    assert safe(x.pathname) and not x.issym and not x.islnk,x.pathname
    if x.isdir:continue
    total+=x.size;assert total<500_000_000
    bb=b''.join(x.get_blocks());assert len(bb)==x.size
    members.append(member(x.pathname,bb))
  return {'format':ext[1:].upper(),'members':members,'expanded_bytes':sum(x.get('expanded_bytes',x['bytes']) for x in members),'checks':['all_archive_members_streamed','safe_paths_no_links'],'member_count':len(members)}
 return native(b,p.name)

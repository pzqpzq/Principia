import sys
sys.dont_write_bytecode = True
"""Disposable behavioral checks for missing, truncated, corrupt and unsafe assets."""
import tempfile,pathlib,hashlib,json
from replay import replay,check,safe

def main():
 with tempfile.TemporaryDirectory() as t:
  p=pathlib.Path(t);src=p/'source';dst=p/'destination';src.mkdir();dst.mkdir();b=b'known public test fixture\n';a={'path':'scenarios/test/raw/fixture.txt','bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};f=safe(src,a['path']);f.parent.mkdir(parents=True);f.write_bytes(b)
  assert replay(a,dst)=='missing'
  assert replay(a,dst,'copy',src)=='restored'
  d=safe(dst,a['path']);d.write_bytes(b[:-1]);assert replay(a,dst)=='size_mismatch';assert replay(a,dst,'copy',src)=='size_mismatch';assert d.read_bytes()==b[:-1]
  d.write_bytes(b'X'+b[1:]);assert replay(a,dst)=='sha256_mismatch'
  d.unlink();assert replay(a,dst,'copy',src)=='restored'
  rejected=False
  try:safe(dst,'../escape')
  except ValueError:rejected=True
  assert rejected
  print(json.dumps({'status':'pass','checks':['missing detected','frozen copy reconstructed','truncation detected','existing mismatch not overwritten','same-size corruption detected','path traversal rejected']}))
if __name__=='__main__':main()

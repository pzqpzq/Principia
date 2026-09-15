import sys
sys.dont_write_bytecode = True
import datetime,hashlib,json,pathlib

def digest(p,algorithm="sha256"):
 h=hashlib.new(algorithm)
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,default=str)+"\n")

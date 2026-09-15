import sys
sys.dont_write_bytecode = True
"""Bounded MATLAB v5 element inventory, no object/code execution or source changes."""
import struct,zlib,math,collections
TYPES={1:('i1',1),2:('u1',1),3:('i2',2),4:('u2',2),5:('i4',4),6:('u4',4),7:('f4',4),9:('f8',8),12:('i8',8),13:('u8',8),16:('utf8',1),17:('utf16',2),18:('utf32',4)}
def inventory(b):
 assert b[126:128] in (b'IM',b'MI');endian='<' if b[126:128]==b'IM' else '>';out=[]
 def elements(buf):
  off=0
  while off+8<=len(buf):
   a,n=struct.unpack_from(endian+'II',buf,off)
   if a==0 and n==0:return
   if a>>16:
    typ=a&65535;size=a>>16;assert size<=4;v=buf[off+4:off+4+size];off+=8
   else:
    typ=a;size=n;assert off+8+size<=len(buf),(typ,size,len(buf)-off);v=buf[off+8:off+8+size];off+=8+((size+7)//8*8)
   yield typ,v
 def matrix(buf,path):
  el=list(elements(buf));assert len(el)>=3
  flags=struct.unpack_from(endian+'I',el[0][1])[0];cls=flags&255
  dims=struct.unpack(endian+'i'*(len(el[1][1])//4),el[1][1]);name=bytes(el[2][1]).decode('utf8',errors='replace');path=path+'/'+name if name else path
  payload=el[3:]
  if cls in (2,3):
   if cls==3:payload=payload[1:]
   size=struct.unpack_from(endian+'I',payload[0][1])[0];raw=bytes(payload[1][1]);names=[raw[k:k+size].split(b'\0')[0].decode('utf8',errors='replace') for k in range(0,len(raw),size)];sub=payload[2:]
   for i,(typ,v) in enumerate(sub):
    if typ==14:matrix(v,path+'/'+names[i%len(names)])
  elif cls==1:
   for i,(typ,v) in enumerate(payload):
    if typ==14:matrix(v,path+f'[{i}]')
  else:
   row={'path':path,'class':cls,'shape':dims,'blocks':[]}
   for typ,v in payload:
    dt,sz=TYPES.get(typ,('unknown',1));block={'type':typ,'dtype':dt,'bytes':len(v),'elements':len(v)//sz}
    if cls in range(6,16) and dt[0] in 'iuf' and len(v):
     import numpy as np
     a=np.frombuffer(v,dtype=endian+dt);block['finite_count']=int(np.isfinite(a).sum());block['minimum']=float(np.nanmin(a));block['maximum']=float(np.nanmax(a));assert a.size==math.prod(dims)
    row['blocks'].append(block)
   if cls!=4:out.append(row)
 def walk(buf):
  for typ,v in elements(buf):
   if typ==14:matrix(v,'')
   elif typ==15:walk(zlib.decompress(v))
 walk(memoryview(b)[128:]);return out
if __name__=='__main__':
 import sys,pathlib,json
 a=inventory(pathlib.Path(sys.argv[1]).read_bytes());print(json.dumps(a,indent=2)[:12000]);print('ARRAYS',len(a))

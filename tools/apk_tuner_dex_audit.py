"""Finite DEX native-method inventory; emits controlled radio identifiers only."""
from pathlib import Path
import argparse,zipfile,hashlib,json,re,struct
RADIO=re.compile(r"(?:tuner|dtv|isdb|oneseg|fullseg|mn885|pseq)",re.I)
SAFE=re.compile(r"^[A-Za-z0-9_$/.;<>\[\]-]+$")
def parse(raw):
 if len(raw)<112 or raw[:4]!=b"dex\n" or raw[7]!=0 or raw[4:7] not in (b'035',b'036',b'037',b'038',b'039',b'040',b'041'):raise ValueError('DEX format')
 def u32(a):
  if a<0 or a+4>len(raw):raise ValueError('Bounds')
  return struct.unpack_from('<I',raw,a)[0]
 def u16(a):
  if a<0 or a+2>len(raw):raise ValueError('Bounds')
  return struct.unpack_from('<H',raw,a)[0]
 if u32(32)!=len(raw) or u32(36)!=112 or u32(40)!=0x12345678:raise ValueError('DEX header')
 def table(a,width):
  count,offset=u32(a),u32(a+4)
  if count>len(raw)//width or offset+count*width>len(raw):raise ValueError('Table bounds')
  return count,offset
 def leb(a):
  v=0
  for n in range(5):
   if a>=len(raw):raise ValueError('LEB bounds')
   b=raw[a];a+=1;v|=(b&127)<<(7*n)
   if not b&128:return v,a
  raise ValueError('LEB length')
 ns,so=table(56,4);nt,to=table(64,4);nm,mo=table(88,8);nc,co=table(96,32)
 strings=[]
 for n in range(ns):
  a=u32(so+4*n);length,a=leb(a);end=raw.find(b'\0',a)
  if end<0:raise ValueError('String terminator')
  strings.append(raw[a:end].decode('utf-8',errors='replace'))
 types=[strings[u32(to+4*n)] for n in range(nt)]
 methods=[(types[u16(mo+8*n)],strings[u32(mo+8*n+4)]) for n in range(nm)]
 hits=[];native_count=0
 for n in range(nc):
  a=u32(co+32*n+24)
  if not a:continue
  counts=[]
  for _ in range(4):v,a=leb(a);counts.append(v)
  if sum(counts)>len(raw):raise ValueError('Class count')
  for count in counts[:2]:
   for _ in range(count):_,a=leb(a);_,a=leb(a)
  for count in counts[2:]:
   idx=0
   for _ in range(count):
    diff,a=leb(a);idx+=diff;access,a=leb(a);code,a=leb(a)
    if idx>=len(methods):raise ValueError('Method index')
    if access&0x100:
     native_count+=1;owner,name=methods[idx]
     if RADIO.search(owner+' '+name) and SAFE.fullmatch(owner) and SAFE.fullmatch(name):
      hits.append({'class':owner,'method':name,'access':access})
 return {'native_methods':native_count,'radio_native_declarations':hits,'method_ids':nm,'class_defs':nc}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apk-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();root=args.apk_root.resolve()
 r={'scope':'work/**/*.apk classes*.dex standard DEX declared native methods; radio identifier filter; not call graph/Java implementation/ELF code','apk_candidates':0,'dex_candidates':0,'unique_dex':0,'errors':[],'oversized':[],'hits':[]};seen={}
 for apk in sorted(root.rglob('*.apk')):
  r['apk_candidates']+=1
  try:
   with zipfile.ZipFile(apk) as z:
    for e in z.infolist():
     if not re.fullmatch(r'classes(?:[2-9]|[1-9][0-9]+)?\.dex',e.filename):continue
     r['dex_candidates']+=1
     if e.file_size>128*1024*1024:r['oversized'].append({'apk':str(apk.relative_to(root)),'entry':e.filename});continue
     data=z.read(e);sha=hashlib.sha256(data).hexdigest()
     if sha not in seen:
      try:seen[sha]=parse(data)
      except (ValueError,IndexError,struct.error) as err:seen[sha]={'parse_error':type(err).__name__}
     item={'apk':str(apk.relative_to(root)),'entry':e.filename,'sha256':sha}
     if 'parse_error' in seen[sha]:r['errors'].append({**item,**seen[sha]})
     elif seen[sha]['radio_native_declarations']:r['hits'].append({**item,**seen[sha]})
  except (OSError,zipfile.BadZipFile) as err:r['errors'].append({'apk':str(apk.relative_to(root)),'error':type(err).__name__})
 r['unique_dex']=len(seen);r['unique_native_methods']=sum(x.get('native_methods',0) for x in seen.values())
 args.output.write_text(json.dumps(r,indent=2),encoding='utf-8')
 print(json.dumps({**{k:r[k] for k in ('apk_candidates','dex_candidates','unique_dex','unique_native_methods')},'errors':len(r['errors']),'oversized':len(r['oversized']),'hit_archives':len(r['hits'])},indent=2),flush=True)
if __name__=='__main__':main()

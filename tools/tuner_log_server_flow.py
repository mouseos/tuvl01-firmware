"""Verify fixed HTV31 2.44 tuner-log control motifs; no complete disassembly."""
import argparse,hashlib,json,pathlib,struct
SOURCE_SHA='a31cd4ea9713e6674fb1966ace27950a3d2984f00949d1ed81d45967afeb172b'
def analyze(raw):
 if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('Requires exact HTV31 2.44 dtvserver source')
 if raw[:7]!=b'\x7fELF\x01\x01\x01' or struct.unpack_from('<H',raw,18)[0]!=40:raise ValueError('Not ARM32 little-endian ELF')
 phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
 segments=[]
 for n in range(phnum):
  typ,off,va,_,filesz,_,_,_=struct.unpack_from('<8I',raw,phoff+phsize*n)
  if typ==1:segments.append((off,va,filesz))
 def offset(va,width=4):
  for off,start,size in segments:
   if start<=va and va+width<=start+size:return off+va-start
  raise ValueError('VA not supplied')
 def word(va):return struct.unpack_from('<I',raw,offset(va))[0]
 def branch(va):
  a,b=struct.unpack_from('<HH',raw,offset(va))
  if a&0xf800!=0xf000 or b&0xd000!=0xd000:raise ValueError('Expected Thumb BL')
  s=(a>>10)&1;i1=1^((b>>13)&1)^s;i2=1^((b>>11)&1)^s
  imm=(s<<24)|(i1<<23)|(i2<<22)|((a&1023)<<12)|((b&2047)<<1)
  if s:imm-=1<<25
  return (va+4+imm)&0xffffffff
 mappings=[]
 for command,table,handler in ((0x1000001f,0x437a58,0x4b259),(0x10000020,0x437a74,0x4b309)):
  if word(table)!=command or word(table-4)!=handler:raise ValueError('Dispatch candidate changed')
  mappings.append({'command':f'{command:08X}','table_VA':f'{table:08X}','table_file_offset':f'{offset(table):08X}','preceding_Thumb_handler':f'{handler:08X}'})
 calls=[]
 for site,target in ((0x4b28a,0x610ac),(0x4b2a0,0x49134),(0x4b33a,0x6117c),(0x4b350,0x49134),(0x4b726,0x52cac),(0x4b7aa,0x52df8),(0x52d00,0x63b94),(0x52d14,0x40dd4),(0x52e3a,0x40dd4)):
  got=branch(site)
  if got!=target:raise ValueError('Unexpected call target')
  calls.append({'site':f'{site:08X}','target':f'{got:08X}'})
 if word(0x52dc8)!=0x10030024 or word(0x52e70)!=0x10030025:raise ValueError('Internal command changed')
 if struct.unpack_from('<H',raw,offset(0x52d0a,2))[0]!=0x2208 or struct.unpack_from('<H',raw,offset(0x52e38,2))[0]!=0x2202:raise ValueError('Payload-size instruction changed')
 return {'source_sha256':SOURCE_SHA,'scope':'Exact fixed motifs and branch targets only; handler table meaning/control flow conditional; no IQ or log-content proof','dispatch_candidates':mappings,'verified_direct_calls':calls,'internal_requests':[{'command':'10030024','payload_bytes':8},{'command':'10030025','payload_bytes':2}],'next_target':'Receiver task/dispatch of internal10030024/25 and log writer','IQ_verified':False}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--server',required=True,type=pathlib.Path);p.add_argument('--output',type=pathlib.Path);args=p.parse_args();result=json.dumps(analyze(args.server.read_bytes()),indent=2)+'\n'
 if args.output:args.output.write_text(result,encoding='utf-8')
 else:print(result,end='')
if __name__=='__main__':main()

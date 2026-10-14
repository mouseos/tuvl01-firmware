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
 result={'source_sha256':SOURCE_SHA,'scope':'Exact fixed motifs and branch targets only; handler table meaning/control flow conditional; no IQ or log-content proof','dispatch_candidates':mappings,'verified_direct_calls':calls,'internal_requests':[{'command':'10030024','payload_bytes':8},{'command':'10030025','payload_bytes':2}],'next_target':'Other builds and direct lower tuner paths; logger rows disabled in this exact receiver table','IQ_verified':False}
 # Fixed receiver motifs independently connect command normalization, table lookup,
 # acceptance bytes, and nullable function pointer. Hash pins the entire input.
 motifs={
  0x91ac0:'01f16f4c0cf57d09',  # command - 0x10030000
  0x91acc:'0c227f443f6802fb090817f80830',  # 12*index+state, byte load
  0x9c7d2:'7d442d680c2202fb045cdcf808302bb140469847', # +8 pointer, null guard
  0x91c5a:'04f16f4c0cf57d04',
  0x91d06:'0efb0426f78847451ed0', # +6 next state; compare FFFF
 }
 for va,expected in motifs.items():
  blob=bytes.fromhex(expected)
  if raw[offset(va,len(blob)):offset(va,len(blob))+len(blob)]!=blob:raise ValueError('Receiver motif changed')
 receiver_calls=[]
 for site,target in ((0x67ac8,0x67904),(0x67adc,0x92108),(0x922d4,0x91a08),(0x922e6,0x91ff4),(0x92040,0x91c18),(0x91cf0,0x9c798),(0x91ac8,0x81824)):
  if branch(site)!=target:raise ValueError('Receiver call changed')
  receiver_calls.append({'site':f'{site:08X}','target':f'{target:08X}'})
 task=word(0x678c8); callback=(word(0x678f0)+0x6788c)&0xffffffff
 if task!=0x8a101003 or callback!=0x67a91 or word(0x92338)!=task:raise ValueError('AIR task changed')
 if word(0x91bb8)!=task or word(0x91bbc)!=0x8a101002:raise ValueError('Source task classification changed')
 got_refs=[(0x91be0,0x91ad2),(0x9c858,0x9c7d6),(0x91dac,0x91d06)]
 got=[(word(literal)+pc)&0xffffffff for literal,pc in got_refs]
 if got!=[0x442c48]*3:raise ValueError('Table reference changed')
 base=word(got[0])
 if base!=0x445150:raise ValueError('Receiver table changed')
 rows=[]
 for index,expected in ((0x24,(0,0xffff0000,0)),(0x25,(0,0xffff0000,0)),(0x26,(0x01000100,0xffff0101,0x000a13a9))):
  va=base+12*index;off=offset(va,12);record=raw[off:off+12]
  if struct.unpack('<3I',record)!=expected:raise ValueError('Receiver record changed')
  rows.append({'command':f'{0x10030000+index:08X}','index':index,'VA':f'{va:08X}','file_offset':f'{off:08X}','acceptance_bytes':list(record[:6]),'next_state':f'{struct.unpack_from("<H",record,6)[0]:04X}','Thumb_handler':f'{struct.unpack_from("<I",record,8)[0]:08X}'})
 result['air_receiver']={'task_ID':f'{task:08X}','creation_callback_Thumb':f'{callback:08X}','verified_direct_calls':receiver_calls,'normalization':'command - 0x10030000','stride':12,'table_GOT_VA':f'{got[0]:08X}','table_VA':f'{base:08X}','records':rows,'interpretation':'10030024/25: six zero acceptance bytes and null handlers in this exact build. Chip IQ capability and other builds remain unknown.'}
 return result

COMMON_SHA='33a1efb1e73b981f72ee71b86798938447ff517f79d86b659acfa36f076259de'
def analyze_common(raw):
 if hashlib.sha256(raw).hexdigest()!=COMMON_SHA:raise ValueError('Requires exact HTV31 2.44 libDtv.so')
 phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
 def offset(va,width):
  for n in range(phnum):
   typ,off,start,_,size,_,_,_=struct.unpack_from('<8I',raw,phoff+phsize*n)
   if typ==1 and start<=va and va+width<=start+size:return off+va-start
  raise ValueError('Common library VA not supplied')
 count=struct.unpack_from('<H',raw,offset(0x30278,2))[0]
 if count!=15:raise ValueError('Task count changed')
 # Exported tbl_DtvSvCom_TaskList size 420, 15 records of seven words.
 row=struct.unpack_from('<7I',raw,offset(0x300a0+2*28,28))
 nameoff=offset(row[0],4)
 if raw[nameoff:nameoff+4]!=b'AIR\0' or row[1]!=0x8a101003:raise ValueError('AIR task record changed')
 return {'source_sha256':COMMON_SHA,'task_table_VA':'000300A0','task_count':count,'record_bytes':28,'AIR_index':2,'AIR_task_ID':f'{row[1]:08X}','scope':'Exact AIR name/ID association; remaining task fields not interpreted'}

OLD_SHA='015096d98fed6f27c1275e5c6f04ad5457a0abf241e5a112b64fc461e2c815cc'
def analyze_comparison(raw):
 if hashlib.sha256(raw).hexdigest()!=OLD_SHA:raise ValueError('Requires exact HTV31 1.08/1.11 dtvserver')
 phoff=struct.unpack_from('<I',raw,28)[0];phsize,phnum=struct.unpack_from('<HH',raw,42)
 def offset(va,width=4):
  for n in range(phnum):
   typ,off,start,_,size,_,_,_=struct.unpack_from('<8I',raw,phoff+phsize*n)
   if typ==1 and start<=va and va+width<=start+size:return off+va-start
  raise ValueError('Comparison VA not supplied')
 def word(va):return struct.unpack_from('<I',raw,offset(va))[0]
 for va,expected in ((0x9270e,'01f16f4e0ef57d09'),(0x9271a,'0c23444abc5803fb090814f80870')):
  motif=bytes.fromhex(expected);off=offset(va,len(motif))
  if raw[off:off+len(motif)]!=motif:raise ValueError('Comparison acceptance motif changed')
 if word(0x92804)!=0x8a101003 or word(0x92808)!=0x8a101002:raise ValueError('Comparison task IDs changed')
 gotbase=(word(0x92818)+0x92678)&0xffffffff
 got=(gotbase+word(0x92830))&0xffffffff;table=word(got)
 if got!=0x442be4 or table!=0x445150:raise ValueError('Comparison table changed')
 rows=[]
 for index,expected in ((0x24,(0,0xffff0000,0)),(0x25,(0,0xffff0000,0)),(0x26,(0x01000100,0xffff0101,0xa221d))):
  va=table+index*12;off=offset(va,12);record=raw[off:off+12]
  if struct.unpack('<3I',record)!=expected:raise ValueError('Comparison record changed')
  rows.append({'command':f'{0x10030000+index:08X}','VA':f'{va:08X}','acceptance_bytes':list(record[:6]),'word_at_plus_8':f'{struct.unpack_from("<I",record,8)[0]:08X}'})
 return {'source_sha256':OLD_SHA,'table_GOT_VA':f'{got:08X}','table_VA':f'{table:08X}','records':rows,'scope':'Independent command normalization and MAIN-origin acceptance lookup only; complete old JNI/queue/handler route not verified'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--server',required=True,type=pathlib.Path);p.add_argument('--output',type=pathlib.Path);p.add_argument('--common',type=pathlib.Path);p.add_argument('--comparison-server',type=pathlib.Path);args=p.parse_args();report=analyze(args.server.read_bytes())
 if args.common:report['common_library']=analyze_common(args.common.read_bytes())
 if args.comparison_server:report['comparison_server']=analyze_comparison(args.comparison_server.read_bytes())
 result=json.dumps(report,indent=2)+'\n'
 if args.output:args.output.write_text(result,encoding='utf-8')
 else:print(result,end='')
if __name__=='__main__':main()

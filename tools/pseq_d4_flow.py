"""Inspect supplied Main1 D4/D5 motifs; not a complete PSEQ disassembler."""
import argparse,json,pathlib
from pseq import verify,ASSET_SHA

def analyze(data,manifest,initial_value=None):
    if initial_value is not None and not 0<=initial_value<=255:
        raise ValueError('Initial value must be one byte')
    records=verify(data,manifest)
    memory={}
    for record in records:
        if record['bank']!=0x61:continue
        raw=data[record['offset']:record['offset']+record['size']]
        start=int.from_bytes(raw[:2],'big')
        for index,value in enumerate(raw[2:-1]):
            address=start+index
            if address in memory:raise ValueError('Overlapping Main1 patches')
            memory[address]=value
    def matches(pattern):
        return [address for address in sorted(memory)
                if all(memory.get(address+i)==value for i,value in enumerate(pattern))]
    def one(pattern):
        hits=matches(pattern)
        if len(hits)!=1:raise ValueError('Unexpected motif count')
        return hits[0]
    def stores(target):
        result=[]
        for address in matches(bytes([0xc0,target>>8,target&255])):
            immediate=memory.get(address-1) if memory.get(address-2)==0x10 else None
            result.append({'address':f'{address:04X}','immediate_candidate':immediate})
        return result
    def consumer_block(start,end):
        # Inventory byte motifs inside bounded supplied ranges, not decoding.
        internal=[];registers=[]
        for address in range(start,end):
            opcode=memory.get(address)
            if opcode in (0xc0,0xc4,0xc5) and memory.get(address+1)==0x0f and address+2<end:
                target=(memory[address+1]<<8)|memory[address+2]
                internal.append({'address':f'{address:04X}','opcode':f'{opcode:02X}',
                    'operand':f'{target:04X}',
                    'role_candidate':'store' if opcode==0xc0 else 'read',
                    'preceding_immediate_candidate':memory.get(address-1) if opcode==0xc0 and memory.get(address-2)==0x10 else None})
            if opcode in (0x20,0x28,0x30) and address+1<end:
                reg=memory[address+1]
                if reg in (0xd3,0xd4,0xd5):
                    registers.append({'address':f'{address:04X}','opcode':f'{opcode:02X}',
                        'register':f'{reg:02X}',
                        'role_candidate':'read' if opcode==0x30 else 'write',
                        'immediate_candidate':memory.get(address+2) if opcode==0x28 else None})
        return {'start':f'{start:04X}','end_exclusive':f'{end:04X}',
            'all_bytes_supplied':all(a in memory for a in range(start,end)),
            'internal_motifs':internal,'register_motifs':registers}
    selectors=[];value=initial_value
    for mask,bits,selection in ((0xcf,0x0c,1),(0xef,0x2c,5),(0xf7,0x34,6),
                               (0xd7,0x14,2),(0xdf,0x1c,3),(0xe7,0x24,4)):
        address=one(bytes([0x30,0xd4,0x70,mask,0x74,bits,0x20,0xd4,0x30,0xd5]))
        selectors.append({'start':f'{address:04X}','d5_read':f'{address+8:04X}',
            'mask':f'{mask:02X}','or':f'{bits:02X}',
            'selection_if_AND_OR':selection})
        if value is not None:
            value=(value&mask)|bits
            selectors[-1]['sequential_D4_if_AND_OR']=f'{value:02X}'
    # Candidates only: opcode widths/conditions are not a proven ISA.
    branches=[]
    for address in range(0x59e,0x60c):
        opcode=memory.get(address)
        if opcode in (0x80,0x82,0x90,0x92) and address+2 in memory:
            target=(memory[address+1]<<8)|memory[address+2]
            branches.append({'address':f'{address:04X}','opcode':f'{opcode:02X}',
                'target_candidate':f'{target:04X}','target_supplied':target in memory})
        if opcode in (0x81,0x91,0x99) and address+1 in memory:
            offset=memory[address+1]
            if offset<128:
                target=address+2+offset
                branches.append({'address':f'{address:04X}','opcode':f'{opcode:02X}',
                    'forward_target_candidate':f'{target:04X}','target_supplied':target in memory})
    return {'source_sha256':ASSET_SHA,'hypothetical_initial_D4':initial_value,
        'scope':'Three supplied Main1 patches only; motifs may start inside operands. No ROM or complete ISA inference.',
        'dtvset_mask_shift_store_candidate':f'{one(bytes([0x30,0,0x70,0x0c,0x48,0x48,0xc0,0x0f,8])):04X}',
        'internal_0F08_stores':stores(0x0f08),
        'internal_0F0A_stores':stores(0x0f0a),
        'internal_0F08_to_D4_candidate':f'{one(bytes([0xc5,0x0f,8,0x21,0xd4])):04X}',
        'selectors':selectors,'branch_candidates':branches,
        'D5_store_0F0E_compare_0F0A_candidate':f'{one(bytes([0x30,0xd5,0xc0,0x0f,0x0e,0xc5,0x0f,0x0a,0x69,0x99,5])):04X}',
        'internal_0F0E_stores':stores(0x0f0e),
        'internal_0F0E_read_motifs':[
            {'address':f'{a:04X}','opcode':f'{op:02X}'}
            for op in (0xc4,0xc5) for a in matches(bytes([op,0x0f,0x0e]))],
        'D5_consumer_blocks':[
            consumer_block(start,end) for start,end in
            ((0x0603,0x060b),(0x060b,0x0639),(0x0639,0x068f),(0x068f,0x06d3))],
        'D3_bit2_set_motifs':[f'{a:04X}' for a in matches(bytes([0x30,0xd3,0x74,4,0x20,0xd3]))],
        'D3_bit2_clear_motifs':[f'{a:04X}' for a in matches(bytes([0x30,0xd3,0x70,0xfb,0x20,0xd3]))],
        'D4_operand02_write28_motifs':[f'{a:04X}' for a in matches(bytes([0x28,0xd4,2]))],
        'classification':'Selected scalar/control hypothesis; neither IQ samples nor absence of IQ functionality established.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=pathlib.Path)
    parser.add_argument('--initial-value',type=lambda s:int(s,0),
                        help='Hypothetical initial D4 byte; calculated values are not measurements')
    args=parser.parse_args()
    root=pathlib.Path(__file__).resolve().parents[1]
    result=analyze((root/'firmware/mn885521-pseq.bin').read_bytes(),
                   (root/'firmware/mn885521-pseq.json').read_bytes(),args.initial_value)
    serialized=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(serialized,encoding='utf-8')
    else:print(serialized,end='')
if __name__=='__main__':main()

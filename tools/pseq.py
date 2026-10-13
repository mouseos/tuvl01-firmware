"""Validate bundled MN885521 patch records and emit the target C representation."""
import hashlib,json,pathlib

ASSET_SHA='fb67866165fedb7eceea6a4f26fc797314f2ef8f3a7d1f7bb730dc6ecc651751'
MANIFEST_SHA='279ce8c55c0c27eb53ad387cf191dd2d8a9f7a2379d92ac16f96845f4c574c77'

def verify(data,manifest):
    manifest=manifest.replace(b'\r\n',b'\n')
    if len(data)!=4341 or hashlib.sha256(data).hexdigest()!=ASSET_SHA:
        raise ValueError('MN885521 patch asset size/hash mismatch')
    if hashlib.sha256(manifest).hexdigest()!=MANIFEST_SHA:
        raise ValueError('MN885521 patch manifest hash mismatch')
    records=json.loads(manifest)['records']
    if len(records)!=30:raise ValueError('Invalid patch record count')
    end=0
    for i,r in enumerate(records):
        size=r['size']; offset=r['offset']; payload=r['payload_size']
        if r['index']!=i or r['bank']!=(0x61 if i<3 else 0x60) or offset!=end or size!=payload+3 or payload<=0 or offset+size>len(data):
            raise ValueError('Invalid patch record bounds/order')
        raw=data[offset:offset+size]
        if hashlib.sha256(raw).hexdigest()!=r['sha256'] or raw[-1]!=sum(b.bit_count() for b in raw[2:-1])%2:
            raise ValueError('Invalid patch record integrity')
        end=offset+size
    if end!=len(data):raise ValueError('Unreferenced patch data')
    return records

def header(data,records):
    lines=['/* Generated from verified manufacturer data. */',
           'static const uint8_t pseq_bytes[]={']
    for i in range(0,len(data),16):lines.append('    '+','.join(f'0x{b:02x}' for b in data[i:i+16])+',')
    lines+=['};','static const struct {unsigned offset,count; uint8_t bank;} pseq_records[]={']
    for r in records:lines.append(f"    {{{r['offset']},{r['payload_size']},0x{r['bank']:02x}}},")
    lines+=['};','']
    return '\n'.join(lines)

if __name__=='__main__':
    root=pathlib.Path(__file__).resolve().parents[1]
    data=(root/'firmware/mn885521-pseq.bin').read_bytes()
    records=verify(data,(root/'firmware/mn885521-pseq.json').read_bytes())
    (root/'build/tuner_pseq.h').write_text(header(data,records))
    print('Bundled MN885521 patches verified: 30 records, 4251 payload bytes')

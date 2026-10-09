"""Finite UART TS capture and integrity check; no SPI NOR writes."""
import argparse,pathlib,re,zlib,json
from uart import Transport

def inspect(data):
    if not data or len(data)%188:raise ValueError('Not a nonempty multiple of 188 bytes')
    pids={};last={};sync=tei=adaptation=continuity=comparisons=0
    for pos in range(0,len(data),188):
        p=data[pos:pos+188]
        if p[0]!=0x47:sync+=1;continue
        pid=((p[1]&31)<<8)|p[2];afc=(p[3]>>4)&3;cc=p[3]&15
        pids[pid]=pids.get(pid,0)+1
        if p[1]&128:tei+=1
        if not afc or (afc&2 and (p[4]>183 or (afc==3 and p[4]>182))):adaptation+=1;continue
        discontinuity=bool(afc&2 and p[4] and p[5]&128)
        if discontinuity:last.pop(pid,None)
        if afc&1 and pid!=0x1fff:
            if pid in last:
                comparisons+=1
                previous,packet=last[pid]
                if cc!=(previous+1)&15 and not (cc==previous and p==packet):continuity+=1
            last[pid]=(cc,p)
    return dict(bytes=len(data),packets=len(data)//188,sync_errors=sync,tei_errors=tei,
                adaptation_errors=adaptation,continuity_errors=continuity,continuity_comparisons=comparisons,
                pids={hex(pid):count for pid,count in sorted(pids.items())})

def validate_capture(data,packets,crc):
    if not 0<=packets<=128 or len(data)!=packets*188:raise ValueError('Capture length mismatch')
    if zlib.crc32(data)!=crc:raise ValueError('UART capture CRC mismatch')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--log',type=pathlib.Path,required=True)
    p.add_argument('--output',type=pathlib.Path,required=True)
    p.add_argument('--polling',action='store_true',help='Read finite TS capture without DMA; requires command 0x17 firmware')
    a=p.parse_args();a.log.parent.mkdir(parents=True,exist_ok=True);data=bytearray();summary=None
    with a.log.open('ab') as log:
        t=Transport(a.port,log)
        try:
            t.write(b'i');t.expect('UART application');t.write(bytes([23]) if a.polling else b'l');t.expect('TS capture start')
            def receive(line):
                nonlocal summary
                if line.startswith('TS DATA '):
                    if len(data)>=128*188 or not re.fullmatch(r'TS DATA [0-9a-f]{376}',line):raise ValueError('Invalid TS transport line')
                    data.extend(bytes.fromhex(line[8:]))
                if line.startswith('TS capture packets='):summary=line
                return line.startswith('TS capture end status=')
            end=t.wait(receive,20)
            t.write(b'i');t.expect('UART application')
            a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(data)
            if end.endswith('=failed') or summary is None:raise RuntimeError(end)
            m=re.fullmatch(r'TS capture packets=([0-9a-f]{8}) crc=([0-9a-f]{8}) empty=([0-9a-f]{8}) overrun=([0-9a-f]{8}) underrun=([0-9a-f]{8}) reserved=([0-9a-f]{8})',summary)
            if m is None:raise ValueError('Invalid capture summary')
            packets,crc,empty,over,under,reserved=map(lambda s:int(s,16),m.groups())
            validate_capture(data,packets,crc)
            report=dict(end=end,requested_reader='polling' if a.polling else 'configured',empty_polls=empty,overrun=over,underrun=under,reserved=reserved)
            report.update(inspect(data) if data else {'packets':0})
            print(json.dumps(report,indent=2))
            a.output.with_suffix(a.output.suffix+'.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        finally:t.ser.close()
if __name__=='__main__':main()

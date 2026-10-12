"""Receive real TS UDP from an already connected TUVL01 AP; UART starts/stops it."""
import argparse,hashlib,json,pathlib,re,socket,struct,time
from uart import Transport
from ts_capture import inspect
def decode(data):
    if len(data)<204 or len(data)>1332 or data[:4]!=b'TTS1' or (len(data)-16)%188:
        raise ValueError('Invalid TS datagram')
    sequence,index,flags=struct.unpack('!III',data[4:16])
    if flags&~1:raise ValueError('Unknown TS datagram flags')
    return sequence,index,flags,data[16:]
class StreamCapture:
    """Keep loss evidence independently of socket/UART timing."""
    def __init__(self,on_payload=None):
        self.data=bytearray()
        self.on_payload=on_payload
        self.stats=dict(datagrams=0,missing_datagrams=0,index_gaps=0,reordered=0,
                        fifo_resyncs=0,invalid=0,gaps=[])
        self.expected=None;self.next_index=0
    def accept(self,packet,source):
        if source!=('192.168.74.1',4202):return
        try:seq,index,flags,body=decode(packet)
        except ValueError:self.stats['invalid']+=1;return
        expected=0 if self.expected is None else self.expected
        delta=(seq-expected)&0xffffffff
        if delta>=0x80000000:self.stats['reordered']+=1;return
        self.stats['missing_datagrams']+=delta
        if index!=self.next_index:
            self.stats['index_gaps']+=1
        if delta or index!=self.next_index:
            self.stats['gaps'].append(dict(expected_sequence=expected,received_sequence=seq,
                expected_index=self.next_index,received_index=index,
                missing_datagrams=delta,packet_index_delta=(index-self.next_index)&0xffffffff))
        self.expected=(seq+1)&0xffffffff;self.next_index=(index+len(body)//188)&0xffffffff
        self.stats['fifo_resyncs']+=bool(flags&1);self.stats['datagrams']+=1
        self.data.extend(body)
        if self.on_payload is not None:self.on_payload(body)

def input_summary(line):
    if not line.startswith('TS input '):return None
    names=('source','packets','sync','tei','adaptation','comparisons','cc_jumps','cc_repeats')
    pattern='TS input '+' '.join(name+r'=([0-9a-f]{8})' for name in names)
    match=re.fullmatch(pattern,line)
    if match is None:raise ValueError('Invalid target input summary')
    return dict(zip(names,(int(value,16) for value in match.groups())))

def receive(port,output,log_path,seconds,forward_port=None,quality_watch=False):
    if not 1<=seconds<=300:raise ValueError('seconds must be 1..300')
    if forward_port is not None and not 1024<=forward_port<=65535:
        raise ValueError('forward port must be 1024..65535')
    output=pathlib.Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(log_path).parent.mkdir(parents=True,exist_ok=True)
    def forward(body):
        if forward_port is not None:
            # Send only the actual TS payload, unchanged, to the local player.
            relay.sendto(body,('127.0.0.1',forward_port))
            stats['forwarded_datagrams']+=1
    capture=StreamCapture(forward);data=capture.data;stats=capture.stats
    stats['forwarded_datagrams']=0;accept=capture.accept
    started=None
    error=None
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp, \
             socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as relay,open(log_path,'ab') as log:
            # 17 Mbps full-segment TS fills 1 MiB in about half a second; a larger buffer
            # keeps a short PC-side stall from showing up as lost datagrams.
            udp.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,16*1048576);udp.bind(('192.168.74.2',4202));udp.settimeout(.25)
            stats['socket_receive_buffer_bytes']=udp.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)
            t=Transport(port,log)
            try:
                t.write(b'i');t.expect('UART application')
                if quality_watch:
                    t.write(bytes([13]));t.expect('QUALITY watch begin status=armed')
                t.write(b'B')
                t.expect('TS stream begin status=active')
                started=time.monotonic();end=started+seconds
                while time.monotonic()<end:
                    try:accept(*udp.recvfrom(2048))
                    except socket.timeout:continue
                stats['seconds']=time.monotonic()-started
            finally:
                try:
                    t.write(b'E')
                    summary=t.wait(lambda s:s.startswith('TS stream datagrams='),10)
                    m=re.fullmatch(r'TS stream datagrams=([0-9a-f]{8}) packets=([0-9a-f]{8}) overrun=([0-9a-f]{8}) underrun=([0-9a-f]{8}) busy=([0-9a-f]{8})',summary)
                    if m is None:raise ValueError('Invalid target stream summary')
                    stats.update(zip(('target_datagrams','target_packets','target_overrun','target_underrun','target_busy'),map(lambda x:int(x,16),m.groups())))
                    def end_line(line):
                        incoming=input_summary(line)
                        if incoming is not None:stats['target_input']=incoming
                        return line.startswith('TS stream end status=')
                    stats['target_end']=t.wait(end_line,10)
                    if quality_watch:
                        t.write(bytes([14]));rows=[]
                        while True:
                            line=t.wait(lambda s:s.startswith('QUALITY watch '),15)
                            if line=='QUALITY watch end status=raw':break
                            rows.append(line)
                        stats['quality_watch_raw']=rows
                    t.write(b'i');t.expect('UART application')
                    # Target has stopped; collect the queued tail before closing UDP.
                    drain_end=time.monotonic()+2
                    while time.monotonic()<drain_end:
                        try:accept(*udp.recvfrom(2048))
                        except socket.timeout:break
                    stats['unreceived_datagrams']=stats['target_datagrams']-stats['datagrams']
                    stats['unreceived_packets']=stats['target_packets']-len(data)//188
                finally:t.ser.close()
    except Exception as e:
        error=e;stats["error"]=type(e).__name__+": "+str(e)
    output.write_bytes(data)
    stats.update(inspect(data) if data else {'bytes':0,'packets':0})
    stats['sha256']=hashlib.sha256(data).hexdigest()
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(stats,indent=2)+'\n')
    print(json.dumps({k:v for k,v in stats.items() if k!='pids'},indent=2))
    if error is not None:raise error
    if not stats['datagrams']:raise RuntimeError('No actual TS received')
    return stats
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--log',type=pathlib.Path,required=True);p.add_argument('--seconds',type=float,default=30)
    p.add_argument('--forward-port',type=int,help='Forward unchanged TS to localhost UDP (e.g. TVTest 1234)')
    a=p.parse_args();receive(a.port,a.output,a.log,a.seconds,a.forward_port)
if __name__=='__main__':main()

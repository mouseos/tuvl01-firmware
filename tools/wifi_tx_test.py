"""Finite direct UDP download diagnostic with Wi-Fi profile restoration."""
import argparse,hashlib,json,pathlib,re,socket,struct,sys,time
import wifi_connect
from uart import Transport
from collections import deque

class BenchUART:
    """Drain UART without blocking UDP; retain only bounded benchmark replies."""
    def __init__(self,transport):
        self.transport=transport;self.lines=deque()
    def pump(self):
        t=self.transport
        available=t.ser.in_waiting
        if not available:return
        data=t.ser.read(min(available,65536))
        t.log.write(data);t.log.flush();t.pending+=data
        while b'\n' in t.pending:
            raw,t.pending=t.pending.split(b'\n',1)
            if len(raw)+1>4096:raise ValueError('UART line exceeds transport limit')
            line=raw.decode('ascii',errors='backslashreplace').strip()
            if line.startswith(('UART rejected','UART timeout')):raise RuntimeError(line)
            if line.startswith('WIFI TX bench '):
                if len(self.lines)>=32:raise ValueError('Too many UART benchmark replies')
                self.lines.append(line)
        if len(t.pending)>4096:raise ValueError('UART line exceeds transport limit')
    def wait(self,predicate,timeout=5):
        self.pump()
        while self.lines:
            line=self.lines.popleft()
            if predicate(line):return line
        return self.transport.wait(predicate,timeout)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interface',required=True);p.add_argument('--restore-profile',required=True)
    p.add_argument('--uart-port',required=True);p.add_argument('--output',type=pathlib.Path,required=True)
    p.add_argument("--payload-bytes",type=int,choices=(64,256,512,1024,1332,1472),default=1332)
    p.add_argument("--burst",type=int,choices=(1,4,8),default=1)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    original=wifi_connect.data_test;results=[]
    def diagnostic(interface,result,*args,**kwargs):
        results.append(result);original(interface,result,*args,**kwargs)
        client=result['data']['lease'];server=result['data']['server']
        payload_path=a.output.with_name(a.output.stem+'-payload.bin')
        trial={'payload_file':str(payload_path),'payload_bytes':a.payload_bytes,'burst':a.burst,'received':0,'invalid':0,'reordered':0,'duplicates':0}
        result['tx_bench']=trial;packets={};last=-1;digest=hashlib.sha256()
        log_path=a.output.with_name(a.output.stem+'-uart.bin');trial['uart_log']=str(log_path)
        with log_path.open('ab') as log,socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024*1024)
            trial["socket_receive_buffer_bytes"]=udp.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)
            udp.bind((client,4204));udp.settimeout(.2);t=Transport(a.uart_port,log)
            started=False;first=last_time=None
            try:
                t.write(b'i');t.expect('UART application')
                for _ in range(6):
                    t.write(bytes([7]))
                    selected=t.wait(lambda x:x.startswith('WIFI TX bench size '))
                    if 'payload_bytes=' not in selected:raise RuntimeError(selected)
                    if int(selected.split('payload_bytes=')[1],16)==a.payload_bytes:break
                else:raise RuntimeError('Payload selection failed')
                for _ in range(3):
                    t.write(bytes([8]))
                    selected=t.wait(lambda x:x.startswith('WIFI TX bench burst '))
                    if 'packets=' not in selected:raise RuntimeError(selected)
                    if int(selected.split('packets=')[1],16)==a.burst:break
                else:raise RuntimeError('Burst selection failed')
                t.write(b'<')
                status=t.wait(lambda x:x.startswith('WIFI TX bench begin status='))
                if status!='WIFI TX bench begin status=active':raise RuntimeError(status)
                started=True;start=time.monotonic();first=last_time=None
                expected=bytes(i%251 for i in range(12,a.payload_bytes))
                bench_uart=BenchUART(t);next_uart_poll=start
                while time.monotonic()-start<11.5:
                    if time.monotonic()>=next_uart_poll:
                        bench_uart.pump();next_uart_poll=time.monotonic()+.02
                    try:data,source=udp.recvfrom(2048)
                    except socket.timeout:continue
                    now=time.monotonic()
                    if source!=(server,4204) or len(data)!=a.payload_bytes or data[:4]!=b'TWT1':
                        trial['invalid']+=1;continue
                    seq,length=struct.unpack('!II',data[4:12])
                    if seq>=20000 or length!=a.payload_bytes or data[12:]!=expected:
                        trial['invalid']+=1;continue
                    if seq in packets:trial['duplicates']+=1;continue
                    if seq<last:trial['reordered']+=1
                    last=seq;packets[seq]=data;digest.update(data)
                    if first is None:first=now
                    last_time=now
                counters=bench_uart.wait(lambda x:x.startswith('WIFI TX bench packets='),5)
                trial['target']={k:int(v,16) for k,v in re.findall(r'(\w+)=([0-9a-f]{8})',counters)}
                timing=bench_uart.wait(lambda x:x.startswith('WIFI TX bench timing counts='),5)
                trial['timing']={k:int(v,16) for k,v in re.findall(r'(\w+)=([0-9a-f]{8})',timing)}
                trial['timing']['bins']=[]
                for kind in range(2):
                    line=bench_uart.wait(lambda x:x.startswith('WIFI TX bench timing kind='),5)
                    values={k:int(v,16) for k,v in re.findall(r'(\w+)=([0-9a-f]{8})',line)}
                    if values['kind']!=kind:raise RuntimeError('Timing kind mismatch')
                    trial['timing']['bins'].append(values)
                trial['target_end']=bench_uart.wait(lambda x:x.startswith('WIFI TX bench end status='),5)
                count=trial['target']['packets']
                trial.update(received=len(packets),received_bytes=len(packets)*a.payload_bytes,
                    missing=[i for i in range(count) if i not in packets],
                    sha256_in_receive_order=digest.hexdigest(),
                    receive_span_seconds=None if first is None else last_time-first)
                if any(i>=count for i in packets):raise RuntimeError('Received beyond target count')
                if trial['target_end']!='WIFI TX bench end status=complete' or trial['target']['failed'] or trial['invalid']:
                    raise RuntimeError('Direct sender failed or invalid payload received')
            except Exception as error:
                trial['error']=type(error).__name__+': '+str(error)
                raise
            finally:
                trial.update(received=len(packets),received_bytes=len(packets)*a.payload_bytes,
                    sha256_in_receive_order=digest.hexdigest(),
                    receive_span_seconds=None if first is None else last_time-first)
                try:
                    payload_path.write_bytes(b''.join(packets.values()))
                    if started:
                        t.write(b'>');t.write(b'i');t.expect('UART application')
                finally:t.ser.close()
    wifi_connect.data_test=diagnostic;saved=sys.argv
    sys.argv=[saved[0],'--interface',a.interface,'--restore-profile',a.restore_profile,'--seconds','30','--data','--mtu']
    try:return wifi_connect.main()
    finally:
        sys.argv=saved;wifi_connect.data_test=original
        a.output.write_text(json.dumps(results[-1] if results else {'error':'No result'},indent=2),encoding='utf-8')
if __name__=='__main__':raise SystemExit(main())
